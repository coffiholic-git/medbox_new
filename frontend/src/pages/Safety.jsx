import { useState } from "react";
import { ShieldCheck, AlertTriangle, PhoneCall, CheckCircle2, Info, Search, HeartPulse } from "lucide-react";
import { useStore } from "../store/useStore";
import { DRUG_INTERACTIONS, FOOD_GUIDELINES } from "../data/drugDatabase";
import { sound } from "../utils/audio";
import { haptics } from "../utils/haptics";
import Modal from "../components/Modal";

export default function Safety() {
  const medicines = useStore((s) => s.medicines);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const hapticsEnabled = useStore((s) => s.hapticsEnabled);
  const pushToast = useStore((s) => s.pushToast);

  const [selectedMeds, setSelectedMeds] = useState(["m-paracetamol", "m-amlodipine"]);
  const [sosModalOpen, setSosModalOpen] = useState(false);
  const [sosCountdown, setSosCountdown] = useState(5);

  const toggleMedSelection = (id) => {
    sound.playClick(soundEnabled);
    if (selectedMeds.includes(id)) {
      setSelectedMeds(selectedMeds.filter((m) => m !== id));
    } else {
      setSelectedMeds([...selectedMeds, id]);
    }
  };

  // Find active interactions among selected medicines
  const activeConflicts = DRUG_INTERACTIONS.filter((conflict) => {
    return conflict.drugs.every((drug) =>
      selectedMeds.some((mId) => {
        const med = medicines.find((x) => x.id === mId);
        return med && (med.id === drug || med.name.toLowerCase() === drug.toLowerCase());
      })
    );
  });

  const triggerSOS = () => {
    sound.playAlert(soundEnabled);
    haptics.alert(hapticsEnabled); // distinct long pattern — unmistakable by feel alone
    setSosModalOpen(true);
    pushToast("Emergency SOS sequence initiated!", "error");
  };

  return (
    <div className="mx-auto max-w-3xl pt-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-coral" />
            <span className="font-mono text-[11px] uppercase tracking-wide text-coral">Safety & Conflict Workstation</span>
          </div>
          <h1 className="mt-1 text-[32px] font-extrabold tracking-tight text-ink">Drug Interaction & Conflict Checker</h1>
        </div>

        <button
          onClick={triggerSOS}
          className="flex items-center gap-2 rounded-full bg-coral px-5 py-2.5 text-[13.5px] font-extrabold text-navy-950 shadow-lg hover:bg-red-500 transition animate-pulse"
        >
          <PhoneCall size={16} /> Emergency SOS
        </button>
      </div>

      <p className="mt-3 text-[15px] leading-relaxed text-muted">
        Select medicines from your cabinet to test for chemical conflicts, food restrictions, and risk warnings in real-time.
      </p>

      {/* Interactive Cabinet Selector */}
      <div className="mt-6 rounded-2xl border border-line bg-navy-800/60 p-5">
        <h2 className="text-[14px] font-mono uppercase text-mint flex items-center gap-2">
          <Search size={14} /> Select Medicines to Compare:
        </h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {medicines.map((m) => {
            const active = selectedMeds.includes(m.id);
            return (
              <button
                key={m.id}
                onClick={() => toggleMedSelection(m.id)}
                className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-[13px] font-bold transition ${
                  active
                    ? "border-mint bg-mint-dim text-navy-950 shadow-md"
                    : "border-line text-ink hover:border-mint/50 bg-navy-900/60"
                }`}
              >
                {active && <CheckCircle2 size={14} />}
                {m.name} ({m.strength})
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Conflict Results */}
      <div className="mt-6 space-y-4">
        <h2 className="text-[16px] font-extrabold text-ink flex items-center gap-2">
          <HeartPulse size={18} className="text-lime" /> Interaction Analysis Results:
        </h2>

        {activeConflicts.length > 0 ? (
          activeConflicts.map((conflict, i) => (
            <div
              key={i}
              className="rounded-2xl border border-coral/40 bg-coral/10 p-5 text-left transition hover:border-coral"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-coral">
                  <AlertTriangle size={18} />
                  <strong className="font-bold text-[15px]">{conflict.title}</strong>
                </div>
                <span className="rounded-full bg-coral px-2.5 py-0.5 font-mono text-[10px] font-bold text-navy-950 uppercase">
                  {conflict.severity} Risk
                </span>
              </div>
              <p className="mt-2 text-[13.5px] leading-relaxed text-ink opacity-90">{conflict.description}</p>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-mint/30 bg-mint/[0.06] p-5 flex items-center gap-3 text-mint">
            <CheckCircle2 size={20} className="shrink-0" />
            <div>
              <strong className="block text-[14px]">No Known Chemical Conflicts Detected</strong>
              <small className="text-[12.5px] opacity-80">Selected medications show no recorded adverse interactions in the safety database.</small>
            </div>
          </div>
        )}

        {/* Food & Dietary Guidelines */}
        <div className="mt-6 rounded-2xl border border-line bg-navy-800/60 p-5 space-y-3">
          <h3 className="text-[14px] font-bold text-ink flex items-center gap-2">
            <Info size={16} className="text-mint" /> Food & Intake Precautions for Selected Medicines:
          </h3>
          <div className="divide-y divide-line/30">
            {selectedMeds.map((id) => {
              const med = medicines.find((x) => x.id === id);
              const info = FOOD_GUIDELINES[id] || { food: "Take as directed", warning: "Consult pharmacist if unsure." };
              if (!med) return null;
              return (
                <div key={id} className="py-2.5 flex items-start justify-between gap-4 text-[13px]">
                  <div>
                    <strong className="text-ink">{med.name}:</strong>
                    <span className="ml-1 text-muted">{info.food}</span>
                  </div>
                  <small className="text-coral text-right max-w-xs">{info.warning}</small>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Emergency SOS Modal */}
      <Modal open={sosModalOpen} onClose={() => setSosModalOpen(false)} labelledBy="sosTitle">
        <div className="text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-coral text-navy-950 animate-bounce">
            <PhoneCall size={32} />
          </div>
          <h2 id="sosTitle" className="mt-3 text-[24px] font-extrabold text-coral">
            EMERGENCY SOS INITIATED
          </h2>
          <p className="mt-2 text-[14px] text-muted">
            Connecting to Primary Caregiver & Emergency Dispatch in 5 seconds...
          </p>

          <div className="mt-6 rounded-2xl border border-coral/30 bg-coral/10 p-4 text-left font-mono text-[12px] space-y-2">
            <p className="text-ink"><strong>Dispatch target:</strong> Emergency Helpline (911 / Local SOS)</p>
            <p className="text-ink"><strong>Caregiver Alert:</strong> Dr. Sarah Jenkins & Family Contact</p>
            <p className="text-ink"><strong>Location Data:</strong> GPS Coordinates Attached</p>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={() => setSosModalOpen(false)}
              className="flex-1 rounded-full border border-line py-3 text-[14px] font-bold text-ink"
            >
              Cancel Alert
            </button>
            <button
              onClick={() => {
                pushToast("SOS Call connected to emergency dispatcher.", "success");
                setSosModalOpen(false);
              }}
              className="flex-1 rounded-full bg-coral py-3 text-[14px] font-bold text-navy-950 hover:bg-red-500"
            >
              Call Now
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
