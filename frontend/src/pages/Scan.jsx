import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { ScanLine, RotateCcw, Check, Camera, Upload, Eye, Package, Calendar, AlertCircle, Crop, Pill, ShieldAlert, Clock } from "lucide-react";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";
import { sound } from "../utils/audio";
import { scanDatabase, colorTokens } from "../data/seed";
import PillVisualizer from "../components/PillVisualizer";
import Modal from "../components/Modal";
import CropModal from "../components/CropModal";
import { scanMedicineAPI, confirmRecognitionAPI } from "../utils/api";
import { isMedicineExpired, isMedicineExpiringSoon, parseExpiryDate } from "../utils/time";

const STAGES = { idle: "idle", scanning: "scanning", result: "result" };

export default function Scan() {
  const addMedicine = useStore((s) => s.addMedicine);
  const syncFromBackend = useStore((s) => s.syncFromBackend);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const pushToast = useStore((s) => s.pushToast);
  const { speak } = useSpeech();

  const [mode, setMode] = useState("camera"); // camera | upload | simulate
  const [selectedScanMode, setSelectedScanMode] = useState("both");
  const [stage, setStage] = useState(STAGES.idle);
  const [match, setMatch] = useState(null);
  const [recognitionId, setRecognitionId] = useState(null); // backend scan ID for confirm call
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [initialStock, setInitialStock] = useState(30);
  const [expDateInput, setExpDateInput] = useState("");
  const [uploadedImage, setUploadedImage] = useState(null);
  const [uploadedImageBase64, setUploadedImageBase64] = useState(null);
  const [uploadedSharpness, setUploadedSharpness] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState("scan.jpg");
  const [cropOpen, setCropOpen] = useState(false);
  const [rawUploadedImage, setRawUploadedImage] = useState(null); // pre-crop object URL
  const [cameraStream, setCameraStream] = useState(null);

  // Below this Laplacian-variance score a frame is judged too blurry for OCR
  // to read reliably. Heuristic threshold, tuned for label/bottle photos —
  // not an exact science, but enough to catch obviously out-of-focus shots.
  const SHARPNESS_MIN = 35;

  const videoRef = useRef(null);
  const fileInputRef = useRef(null);

  // Handle device webcam initialization
  useEffect(() => {
    if (mode === "camera" && stage === STAGES.idle) {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices
          .getUserMedia({
            video: {
              facingMode: "environment",
              // Default getUserMedia streams are often as low as 640x480,
              // which isn't enough detail for OCR to read text spread
              // across a wide label. Ask for a much higher-res feed; the
              // browser will fall back to the closest it can supply.
              width: { ideal: 1920 },
              height: { ideal: 1440 },
            },
          })
          .then((stream) => {
            setCameraStream(stream);
            if (videoRef.current) videoRef.current.srcObject = stream;
          })
          .catch((err) => {
            console.warn("Camera access fallback:", err);
          });
      }
    } else {
      if (cameraStream) {
        cameraStream.getTracks().forEach((t) => t.stop());
        setCameraStream(null);
      }
    }
    return () => {
      if (cameraStream) {
        cameraStream.getTracks().forEach((t) => t.stop());
      }
    };
  }, [mode]);

  /**
   * Estimate how in-focus an image is via the variance of its Laplacian
   * (edge response). Sharp, text-heavy photos have lots of high-contrast
   * edges → high variance; blurry photos smear those edges → low variance.
   * This is the same principle OpenCV's cv2.Laplacian().var() blur-check
   * uses, done directly on canvas pixel data so it costs nothing server-side.
   */
  const computeSharpnessScore = (canvas) => {
    try {
      const { width, height } = canvas;
      const { data } = canvas.getContext("2d").getImageData(0, 0, width, height);

      const gray = new Float32Array(width * height);
      for (let i = 0, p = 0; i < data.length; i += 4, p++) {
        gray[p] = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
      }

      // Sample on a stride rather than every pixel so this stays cheap even
      // on a 1920x1440 capture — a few hundred pixels per axis is plenty to
      // estimate overall focus.
      const stride = Math.max(1, Math.floor(Math.min(width, height) / 300));
      let sum = 0;
      let sumSq = 0;
      let n = 0;
      for (let y = 1; y < height - 1; y += stride) {
        for (let x = 1; x < width - 1; x += stride) {
          const idx = y * width + x;
          const lap = 4 * gray[idx] - gray[idx - 1] - gray[idx + 1] - gray[idx - width] - gray[idx + width];
          sum += lap;
          sumSq += lap * lap;
          n++;
        }
      }
      if (n === 0) return null;
      const mean = sum / n;
      return sumSq / n - mean * mean; // variance
    } catch {
      return null; // e.g. tainted canvas — skip the gate rather than block scanning.
    }
  };

  /**
   * Capture a base64 snapshot from the live camera feed (if active), along
   * with a sharpness score for the same frame. Returns null if the camera
   * isn't streaming (upload / simulate modes).
   */
  const captureBase64 = () => {
    if (!videoRef.current || !cameraStream) return null;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current.videoWidth || 640;
      canvas.height = videoRef.current.videoHeight || 480;
      canvas.getContext("2d").drawImage(videoRef.current, 0, 0);
      const sharpness = computeSharpnessScore(canvas);
      // Strip the data:image/... prefix to get raw base64.
      const base64 = canvas.toDataURL("image/jpeg", 0.92).split(",")[1];
      return { base64, sharpness };
    } catch {
      return null;
    }
  };

  const runScan = async () => {
    sound.playBeep(soundEnabled);
    setStage(STAGES.scanning);

    // Try the real backend first.
    let imageBase64 = null;
    let sharpness = null;
    if (mode === "upload") {
      imageBase64 = uploadedImageBase64;
      sharpness = uploadedSharpness;
    } else {
      const captured = captureBase64();
      imageBase64 = captured?.base64 ?? null;
      sharpness = captured?.sharpness ?? null;
    }

    if (!imageBase64) {
      setStage(STAGES.idle);
      const message = mode === "upload"
        ? "Your image is still loading. Please wait a moment, then scan again."
        : "Camera image unavailable. Allow camera permission or upload a clear medicine-label image.";
      pushToast(message, "error");
      speak(message);
      return;
    }

    // Reject visibly out-of-focus frames before wasting a backend call —
    // a blurry photo of a label is unreadable no matter how good the OCR is.
    if (sharpness !== null && sharpness < SHARPNESS_MIN) {
      setStage(STAGES.idle);
      const message = mode === "upload"
        ? "This image looks blurry, so the text may not read clearly. Try a sharper, well-lit photo."
        : "This looks a little blurry. Hold the camera steady, make sure the label is in focus, then scan again.";
      pushToast(message, "error");
      speak(message);
      return;
    }

    const result = await scanMedicineAPI(imageBase64, uploadedFileName, selectedScanMode);

    if (result && !result._error) {
      // ── Backend returned a real scan result ──────────────────────────────
      console.info("OCR stage 7 Scan.jsx response:", {
        expiry_date: result.expiry_date,
        date_confidence: result.date_confidence,
        mfg_date: result.mfg_date,
      });
      setRecognitionId(result.recognitionId || null);
      const isLowConf = result.status === "low_confidence" || (result.confidence ?? 0) < 80;
      const found = {
        name: result.detectedName || "Unidentified Medicine",
        strength: result.detectedStrength || "",
        form: result.detectedForm || "Tablet",
        note: result.instructionsFound || result.spokenResponse || (isLowConf ? "Please verify medicine details and expiry date below." : ""),
        confidence: Math.round((result.confidence ?? 0) <= 1 ? (result.confidence ?? 0) * 100 : result.confidence),
        color: "mint",
        expiry: selectedScanMode === "medicine" ? "" : (result.expiry_date || ""),
        // date_confidence from the API is 0–1 (backend divides by 100 in _scan_contract_fields).
        dateConfidence: result.date_confidence != null ? Math.round(result.date_confidence * 100) : null,
        dateNeedsRescan: result.date_confidence == null || result.date_confidence < 0.5 || isLowConf,
      };
      setMatch(found);

      // Always pre-fill detected EXP date so the user can see and verify it directly
      setExpDateInput(selectedScanMode === "medicine" ? "" : (found.expiry || ""));
      setInitialStock(30);
      setStage(STAGES.result);
      setConfirmOpen(true);
      sound.playChime(soundEnabled);
      if (isLowConf) {
        pushToast("Low confidence read — please verify details and expiry date below.", "warning");
        speak("Low confidence read. Please verify medicine name and expiration date before saving.");
      } else {
        speak(result.spokenResponse || `I identified ${found.name}. Please confirm details before saving.`);
      }
    } else {
      // Backend error or unreachable — show manual confirmation modal with empty defaults
      console.warn("Backend recognition error or unreachable:", result?._detail);
      setRecognitionId(null);
      const found = {
        name: "Unidentified Medicine",
        strength: "",
        form: "Tablet",
        note: "Could not process image on server. Please enter medicine details and expiry date manually.",
        confidence: 0,
        color: "coral",
        expiry: "",
        dateConfidence: 0,
        dateNeedsRescan: true,
      };
      setMatch(found);
      setExpDateInput("");
      setInitialStock(30);
      setStage(STAGES.result);
      setConfirmOpen(true);
      pushToast("Could not read image automatically. Please enter details manually.", "error");
      speak("Could not read image automatically. Please enter details manually.");
    }
  };

  useEffect(() => {
    console.info("OCR stage 8 rendered expiry input:", expDateInput);
  }, [expDateInput]);

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    // Stash the raw object URL so CropModal can show it before we commit.
    setRawUploadedImage(url);
    // Sent filename always reflects the re-encoded format below, so the
    // backend never receives a suffix (.avif, .heic, .webp, ...) that
    // OpenCV's imread can't decode — see comment in reencodeToJpeg.
    setUploadedFileName("scan.jpg");
    // Open the crop dialog — the image preview + base64 will be set
    // only after the user confirms or skips the crop.
    setCropOpen(true);
    // Reset input so re-uploading the same file triggers onChange again.
    e.target.value = "";
  };

  /**
   * Called by CropModal when the user clicks "Apply Crop" or "Skip Crop".
   * dataUrl is either the full image data-URL (skip) or a cropped one.
   */
  const handleCropConfirm = (dataUrl) => {
    setCropOpen(false);
    setUploadedImage(dataUrl); // show in the viewfinder
    // Re-encode the (possibly cropped) data-URL through canvas so we get
    // proper JPEG base64 and a fresh sharpness score.
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || img.width;
        canvas.height = img.naturalHeight || img.height;
        canvas.getContext("2d").drawImage(img, 0, 0);
        const base64 = canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
        const sharpness = computeSharpnessScore(canvas);
        setUploadedImageBase64(base64 || null);
        setUploadedSharpness(sharpness);
      } catch {
        // Tainted canvas or decode failure — skip blur gate.
        setUploadedImageBase64(dataUrl.split(",")[1] || null);
        setUploadedSharpness(null);
      }
    };
    img.onerror = () => {
      setUploadedImageBase64(null);
      setUploadedSharpness(null);
    };
    img.src = dataUrl;
  };

  const handleCropCancel = () => {
    setCropOpen(false);
    // Discard the file — user hit X without confirming.
    setRawUploadedImage(null);
    setUploadedImage(null);
    setUploadedImageBase64(null);
    setUploadedSharpness(null);
  };



  const rescan = () => {
    setConfirmOpen(false);
    setMatch(null);
    setRecognitionId(null);
    setExpDateInput("");
    setStage(STAGES.idle);
    setUploadedImage(null);
    setUploadedImageBase64(null);
    setUploadedSharpness(null);
    setUploadedFileName("scan.jpg");
    setRawUploadedImage(null);
    setCropOpen(false);
  };

  const confirmSave = async () => {
    if (!match) return;

    if (recognitionId) {
      // ── Real backend confirm path ──────────────────────────────────────────
      const result = await confirmRecognitionAPI({
        recognitionId,
        userAction: "confirm",
        finalName: match.name,
        finalStrength: match.strength,
        expDate: expDateInput || match.expiry,
        stock: Number(initialStock),
      });

      if (result?.addedToLibrary && result?.medicine) {
        // Confirmation already persisted the medicine. Refresh local state
        // rather than calling addMedicine(), which would create a duplicate.
        await syncFromBackend();
      } else {
        // A server-recognized medicine must only be added after the server
        // accepts its confirmation; never bypass that safety gate locally.
        pushToast("Could not save the confirmed scan. Please try again.", "error");
        return;
      }
    } else {
      // ── Local simulation fallback path ────────────────────────────────────
      addMedicine({
        name: match.name,
        strength: match.strength,
        form: match.form,
        frequency: "daily",
        time: "9:00 AM",
        instructions: match.note || `${match.form} · 1 daily after meal`,
        color: match.color,
        expiry: expDateInput || match.expiry,
        stock: Number(initialStock),
        maxStock: Number(initialStock),
      });
    }

    sound.playChime(soundEnabled);
    setConfirmOpen(false);
    setStage(STAGES.idle);
    setMatch(null);
    setRecognitionId(null);
    setUploadedImage(null);
    pushToast(`${match.name} ${match.strength} saved to medicine cabinet.`, "success");
    speak(`${match.name} saved to your medicine cabinet.`);
  };

  const tone = match ? colorTokens[match.color] : null;

  return (
    <div className="mx-auto max-w-2xl pt-6 text-center">
      <span className="font-mono text-[11px] uppercase tracking-wide text-mint">AI Vision Scanner</span>
      <h1 className="mt-2 text-[32px] font-extrabold tracking-tight text-ink">Smart Pill & Label Identification</h1>
      <p className="mt-2 text-[15px] text-muted">
        Position the pill bottle or prescription package in front of the lens to identify details.
      </p>

      <div className="mx-auto mt-5 grid max-w-xl grid-cols-2 gap-2 text-left">
        {[{ id: "medicine", label: "Medicine Name", icon: Pill }, { id: "expiry", label: "Expiry Date", icon: Calendar }].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSelectedScanMode(id)}
            className={`rounded-2xl border p-3 transition ${selectedScanMode === id ? "border-mint bg-mint/15 text-mint" : "border-line bg-navy-900/50 text-muted hover:border-mint/50"}`}
          >
            <Icon size={18} />
            <span className="mt-2 block text-[12px] font-bold">{label}</span>
          </button>
        ))}
      </div>

      {/* Mode Switcher */}
      <div className="mx-auto mt-6 flex max-w-xs items-center justify-center rounded-full border border-line bg-navy-800/60 p-1">
        <button
          onClick={() => { setMode("camera"); rescan(); }}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-full py-1.5 text-[12px] font-bold transition ${mode === "camera" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
        >
          <Camera size={14} /> Live Cam
        </button>
        <button
          onClick={() => { setMode("upload"); fileInputRef.current?.click(); }}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-full py-1.5 text-[12px] font-bold transition ${mode === "upload" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
        >
          <Upload size={14} /> Upload Image
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileUpload}
        className="hidden"
      />

      {/* Scanner Viewfinder Box */}
      <div className="relative mx-auto mt-6 grid aspect-[4/3] w-full max-w-xl place-items-center overflow-hidden rounded-[32px] border border-line bg-navy-900/90 shadow-2xl">
        {mode === "camera" && cameraStream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : uploadedImage ? (
          <>
            <img src={uploadedImage} alt="Uploaded pill package" className="absolute inset-0 h-full w-full object-cover" />
            {/* Re-crop button */}
            <button
              id="recrop-btn"
              onClick={() => { setRawUploadedImage(uploadedImage); setCropOpen(true); }}
              className="absolute top-3 right-3 z-30 flex items-center gap-1.5 rounded-full bg-black/60 border border-line px-3 py-1.5 text-[12px] font-bold text-white backdrop-blur-sm hover:bg-mint-dim hover:text-navy-950 transition"
              aria-label="Re-crop image"
            >
              <Crop size={13} /> Re-crop
            </button>
          </>

        ) : (
          <div className="flex flex-col items-center gap-3 text-muted z-10">
            <ScanLine size={36} className="text-mint animate-pulse" />
            <p className="max-w-[220px] text-[13px] leading-relaxed">
              Center pill package or label
              <br />
              inside the frame
            </p>
          </div>
        )}

        {/* Dynamic Simulated AI Bounding Boxes */}
        {stage === STAGES.scanning && (
          <div className="pointer-events-none absolute inset-4 border border-lime/60 rounded-2xl animate-pulse flex flex-col justify-between p-2 z-20">
            <span className="self-start rounded bg-lime/20 px-1.5 py-0.5 font-mono text-[9px] text-lime">OCR MATCHING... 94%</span>
            <span className="self-end rounded bg-mint/20 px-1.5 py-0.5 font-mono text-[9px] text-mint">TEXT: "500MG"</span>
          </div>
        )}

        {/* Viewfinder Target Reticle */}
        <div className="pointer-events-none absolute inset-3 rounded-[24px] border-2 border-dashed border-mint/30 z-20" />
        <div className="pointer-events-none absolute left-3 top-3 h-8 w-8 rounded-tl-2xl border-l-2 border-t-2 border-mint z-20" />
        <div className="pointer-events-none absolute right-3 top-3 h-8 w-8 rounded-tr-2xl border-r-2 border-t-2 border-mint z-20" />
        <div className="pointer-events-none absolute bottom-3 left-3 h-8 w-8 rounded-bl-2xl border-b-2 border-l-2 border-mint z-20" />
        <div className="pointer-events-none absolute bottom-3 right-3 h-8 w-8 rounded-br-2xl border-b-2 border-r-2 border-mint z-20" />

        {stage === STAGES.scanning && (
          <motion.div
            initial={{ top: "0%" }}
            animate={{ top: "100%" }}
            transition={{ duration: 2.0, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}
            className="absolute h-1 w-full bg-lime shadow-[0_0_24px_var(--color-lime)] z-30"
          />
        )}
      </div>

      <button
        onClick={runScan}
        disabled={stage === STAGES.scanning}
        className="mt-6 inline-flex items-center gap-2 rounded-full bg-mint-dim px-8 py-3.5 text-[14.5px] font-bold text-navy-950 transition hover:bg-mint disabled:opacity-60 shadow-lg"
      >
        {stage === STAGES.scanning ? "Analyzing OCR & Vision…" : "Run Vision Scan"} <Eye size={16} />
      </button>

      {/* Confirmation Modal */}
      <Modal open={confirmOpen} onClose={rescan} labelledBy="confirmTitle" width="max-w-md">
        {match && (
          <div className="text-left">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <PillVisualizer form={match.form} color={match.color} size="md" />
                <div>
                  <h2 id="confirmTitle" className="text-[20px] font-extrabold text-ink">
                    {match.name}
                  </h2>
                  <p className="text-[13px] text-muted">{match.strength} · {match.form}</p>
                </div>
              </div>
              <span className="rounded-full bg-mint/20 px-2.5 py-1 font-mono text-[11px] text-mint border border-mint/30">
                {match.confidence}% match
              </span>
            </div>

            <div className="mt-4 rounded-2xl border border-line bg-navy-800/60 p-4 space-y-3">
              {/* Date Detection & Confidence Section */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-mono text-muted uppercase flex items-center gap-1">
                    <Calendar size={13} className="text-mint" /> Expiration Date (EXP)
                  </label>
                </div>

                {/* No date detected at all → prompt to enter manually */}
                {!expDateInput && (
                  <div className="mt-1.5 flex items-start gap-1.5 text-[11.5px] text-coral bg-coral/10 p-2 rounded-lg border border-coral/20">
                    <AlertCircle size={13} className="shrink-0 mt-0.5" />
                    <span>
                      Expiration date could not be read from the image — field left blank.
                      Please enter the EXP date from the package manually.
                    </span>
                  </div>
                )}

                <div className="mt-2">
                  <label className="text-[10px] font-mono text-muted uppercase">EXP Date</label>
                  <input
                    type="text"
                    placeholder="e.g. 12/2026"
                    value={expDateInput}
                    onChange={(e) => setExpDateInput(e.target.value)}
                    className={`mt-0.5 w-full rounded-xl border px-3 py-2 font-mono text-[13px] text-ink focus:outline-none bg-navy-900 ${
                      !expDateInput
                        ? "border-coral/60 focus:border-mint"
                        : isMedicineExpired(expDateInput)
                        ? "border-coral focus:border-coral"
                        : isMedicineExpiringSoon(expDateInput, 90)
                        ? "border-amber-400/70 focus:border-amber-400"
                        : "border-line focus:border-mint"
                    }`}
                  />
                </div>

                {/* ── Expiry status banners ── */}
                {expDateInput && isMedicineExpired(expDateInput) && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-2 flex items-start gap-2 rounded-xl border border-coral/40 bg-coral/10 p-3"
                  >
                    <ShieldAlert size={16} className="shrink-0 mt-0.5 text-coral" />
                    <div>
                      <p className="text-[12.5px] font-extrabold text-coral uppercase tracking-wide">⚠ This medicine has expired!</p>
                      <p className="mt-0.5 text-[11.5px] text-coral/80">
                        The expiry date <span className="font-bold">{expDateInput}</span> has already passed.
                        Do not take expired medication — it may be unsafe or ineffective.
                        Please discard it properly and obtain a fresh supply.
                      </p>
                    </div>
                  </motion.div>
                )}

                {expDateInput && !isMedicineExpired(expDateInput) && isMedicineExpiringSoon(expDateInput, 90) && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-2 flex items-start gap-2 rounded-xl border border-amber-400/40 bg-amber-400/10 p-3"
                  >
                    <Clock size={15} className="shrink-0 mt-0.5 text-amber-400" />
                    <div>
                      <p className="text-[12.5px] font-bold text-amber-400">Expiring Soon</p>
                      <p className="mt-0.5 text-[11.5px] text-amber-400/80">
                        This medicine expires on <span className="font-bold">{expDateInput}</span> — within the next 90 days.
                        Consider obtaining a refill soon.
                      </p>
                    </div>
                  </motion.div>
                )}
              </div>

              <div>
                <label className="block text-[11px] font-mono text-muted uppercase">Initial Pill Inventory Stock</label>
                <div className="mt-1 flex items-center gap-2">
                  <Package size={16} className="text-mint" />
                  <input
                    type="number"
                    min="1"
                    max="120"
                    value={initialStock}
                    onChange={(e) => setInitialStock(e.target.value)}
                    className="w-full rounded-xl border border-line bg-navy-900 px-3 py-1.5 font-mono text-ink focus:border-mint focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-mono text-muted uppercase">Safety Note / Dosage Guidance</label>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted bg-navy-900/60 p-2.5 rounded-xl border border-line">
                  {match.note}
                </p>
              </div>
            </div>


            <div className="mt-6 flex flex-col gap-2.5 sm:flex-row">
              <button
                onClick={rescan}
                className="flex flex-1 items-center justify-center gap-2 rounded-full border border-line py-3 text-[13.5px] font-bold text-ink transition hover:border-coral hover:text-coral"
              >
                <RotateCcw size={14} /> Rescan
              </button>
              <button
                onClick={confirmSave}
                className={`flex-1 rounded-full py-3 text-[13.5px] font-bold transition ${
                  expDateInput && isMedicineExpired(expDateInput)
                    ? "bg-coral/90 text-white hover:bg-coral"
                    : "bg-mint-dim text-navy-950 hover:bg-mint"
                }`}
              >
                {expDateInput && isMedicineExpired(expDateInput) ? "Save Anyway (Expired)" : "Save to Cabinet"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Crop Modal — shown immediately after an image is picked */}
      <CropModal
        open={cropOpen}
        imageSrc={rawUploadedImage}
        onConfirm={handleCropConfirm}
        onCancel={handleCropCancel}
      />
    </div>
  );
}
