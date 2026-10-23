import { useState, useRef, useCallback } from "react";
import ReactCrop, { centerCrop, makeAspectCrop } from "react-image-crop";
import "react-image-crop/dist/ReactCrop.css";
import { Crop, Check, X, RotateCcw } from "lucide-react";

/**
 * CropModal
 * ---------
 * Shows a full-screen overlay with react-image-crop, letting the user
 * drag a selection over the uploaded medicine image before it is sent
 * to the OCR backend.
 *
 * Props:
 *   open        - boolean, controls visibility
 *   imageSrc    - object-URL of the raw uploaded file
 *   onConfirm   - (croppedDataUrl: string) => void
 *   onCancel    - () => void
 */
export default function CropModal({ open, imageSrc, onConfirm, onCancel }) {
  const imgRef = useRef(null);
  const [crop, setCrop] = useState(null);
  const [completedCrop, setCompletedCrop] = useState(null);

  const onImageLoad = useCallback((e) => {
    const { width, height } = e.currentTarget;
    const initial = { unit: "%", x: 0, y: 0, width: 100, height: 100 };
    setCrop(initial);
    setCompletedCrop(initial);
  }, []);

  const resetCrop = useCallback(() => {
    const initial = { unit: "%", x: 0, y: 0, width: 100, height: 100 };
    setCrop(initial);
    setCompletedCrop(initial);
  }, []);

  const handleConfirm = useCallback(() => {
    if (!completedCrop || !imgRef.current) {
      onConfirm(imageSrc);
      return;
    }
    const image = imgRef.current;
    const scaleX = image.naturalWidth / image.width;
    const scaleY = image.naturalHeight / image.height;

    // ReactCrop can return crop in percentages (especially on load/reset)
    // or pixels (when dragged). Convert to actual image pixels.
    let pixelCrop;
    if (completedCrop.unit === "%") {
      pixelCrop = {
        x: (completedCrop.x / 100) * image.naturalWidth,
        y: (completedCrop.y / 100) * image.naturalHeight,
        width: (completedCrop.width / 100) * image.naturalWidth,
        height: (completedCrop.height / 100) * image.naturalHeight,
      };
    } else {
      pixelCrop = {
        x: completedCrop.x * scaleX,
        y: completedCrop.y * scaleY,
        width: completedCrop.width * scaleX,
        height: completedCrop.height * scaleY,
      };
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(pixelCrop.width);
    canvas.height = Math.round(pixelCrop.height);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(
      image,
      pixelCrop.x,
      pixelCrop.y,
      pixelCrop.width,
      pixelCrop.height,
      0,
      0,
      canvas.width,
      canvas.height,
    );
    onConfirm(canvas.toDataURL("image/jpeg", 0.92));
  }, [completedCrop, imageSrc, onConfirm]);

  if (!open || !imageSrc) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Crop image"
    >
      <div className="flex w-full max-w-2xl flex-col gap-4 rounded-[28px] border border-line bg-navy-900 p-5 shadow-2xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-ink">
            <Crop size={18} className="text-mint" />
            <span className="text-[15px] font-bold">Crop Medicine Image</span>
          </div>
          <button
            id="crop-cancel-btn"
            onClick={onCancel}
            className="rounded-full p-1.5 text-muted hover:bg-navy-800 hover:text-coral transition"
            aria-label="Cancel crop"
          >
            <X size={18} />
          </button>
        </div>

        <p className="text-[12.5px] text-muted leading-relaxed">
          Drag the selection to focus on the label area. A tighter crop gives the
          OCR engine a clearer view of the text.
        </p>

        <div className="flex justify-center overflow-auto rounded-2xl bg-black/40 border border-line p-2">
          <ReactCrop
            crop={crop}
            onChange={(c) => setCrop(c)}
            onComplete={(c) => setCompletedCrop(c)}
            minWidth={30}
            minHeight={30}
            ruleOfThirds
          >
            <img
              ref={imgRef}
              src={imageSrc}
              alt="Medicine image to crop"
              onLoad={onImageLoad}
              style={{ maxHeight: "55vh", objectFit: "contain" }}
            />
          </ReactCrop>
        </div>

        <div className="flex items-center gap-2 justify-end">
          <button
            id="crop-reset-btn"
            onClick={resetCrop}
            className="flex items-center gap-1.5 rounded-full border border-line px-4 py-2 text-[13px] font-semibold text-muted hover:border-mint hover:text-mint transition"
          >
            <RotateCcw size={13} /> Reset
          </button>
          <button
            id="crop-skip-btn"
            onClick={() => onConfirm(imageSrc)}
            className="flex items-center gap-1.5 rounded-full border border-line px-4 py-2 text-[13px] font-semibold text-muted hover:border-mint hover:text-ink transition"
          >
            Skip Crop
          </button>
          <button
            id="crop-confirm-btn"
            onClick={handleConfirm}
            className="flex items-center gap-1.5 rounded-full bg-mint-dim px-5 py-2 text-[13px] font-bold text-navy-950 hover:bg-mint transition shadow"
          >
            <Check size={14} /> Apply Crop
          </button>
        </div>
      </div>
    </div>
  );
}
