import { useState } from "react";
import { Activity, Heart, Droplet, Plus, TrendingUp } from "lucide-react";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";
import Modal from "./Modal";

export default function VitalsTracker() {
  const vitalsLogs = useStore((s) => s.vitalsLogs);
  const addVitalLog = useStore((s) => s.addVitalLog);
  const pushToast = useStore((s) => s.pushToast);
  const soundEnabled = useStore((s) => s.soundEnabled);

  const [modalOpen, setModalOpen] = useState(false);
  const [systolic, setSystolic] = useState("120");
  const [diastolic, setDiastolic] = useState("80");
  const [glucose, setGlucose] = useState("98");
  const [pulse, setPulse] = useState("72");

  const latest = vitalsLogs[vitalsLogs.length - 1] || { bpSystolic: 120, bpDiastolic: 80, glucose: 98, pulse: 72 };

  const handleSave = (e) => {
    e.preventDefault();
    addVitalLog({
      bpSystolic: Number(systolic),
      bpDiastolic: Number(diastolic),
      glucose: Number(glucose),
      pulse: Number(pulse),
    });
    sound.playChime(soundEnabled);
    pushToast("Health vitals recorded successfully.", "success");
    setModalOpen(false);
  };

  return (
    <div className="rounded-2xl border border-line bg-navy-800/60 p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={18} className="text-mint" />
          <span className="font-mono text-[11px] uppercase tracking-wide text-mint">Health Vitals</span>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1 text-[12px] font-bold text-mint hover:underline"
        >
          <Plus size={14} /> Log Vitals
        </button>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-xl border border-line bg-navy-900/60 p-3">
          <div className="flex items-center justify-center gap-1 text-[11px] font-mono text-muted">
            <Heart size={12} className="text-coral" /> BP
          </div>
          <p className="mt-1 text-[16px] font-extrabold text-ink">
            {latest.bpSystolic}/{latest.bpDiastolic}
          </p>
          <small className="text-[10px] text-lime">Optimal</small>
        </div>

        <div className="rounded-xl border border-line bg-navy-900/60 p-3">
          <div className="flex items-center justify-center gap-1 text-[11px] font-mono text-muted">
            <Droplet size={12} className="text-mint" /> Glucose
          </div>
          <p className="mt-1 text-[16px] font-extrabold text-ink">{latest.glucose} <span className="text-[10px] font-normal text-muted">mg/dL</span></p>
          <small className="text-[10px] text-lime">Fasting</small>
        </div>

        <div className="rounded-xl border border-line bg-navy-900/60 p-3">
          <div className="flex items-center justify-center gap-1 text-[11px] font-mono text-muted">
            <Activity size={12} className="text-lime" /> Pulse
          </div>
          <p className="mt-1 text-[16px] font-extrabold text-ink">{latest.pulse} <span className="text-[10px] font-normal text-muted">bpm</span></p>
          <small className="text-[10px] text-lime">Resting</small>
        </div>
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} labelledBy="vitalsTitle">
        <form onSubmit={handleSave} className="space-y-4">
          <h2 id="vitalsTitle" className="text-[20px] font-extrabold text-ink">
            Log Health Vitals
          </h2>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[12px] font-mono text-muted">BP Systolic</label>
              <input
                type="number"
                value={systolic}
                onChange={(e) => setSystolic(e.target.value)}
                className="input mt-1"
                required
              />
            </div>
            <div>
              <label className="block text-[12px] font-mono text-muted">BP Diastolic</label>
              <input
                type="number"
                value={diastolic}
                onChange={(e) => setDiastolic(e.target.value)}
                className="input mt-1"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[12px] font-mono text-muted">Blood Glucose (mg/dL)</label>
              <input
                type="number"
                value={glucose}
                onChange={(e) => setGlucose(e.target.value)}
                className="input mt-1"
                required
              />
            </div>
            <div>
              <label className="block text-[12px] font-mono text-muted">Pulse (BPM)</label>
              <input
                type="number"
                value={pulse}
                onChange={(e) => setPulse(e.target.value)}
                className="input mt-1"
                required
              />
            </div>
          </div>

          <div className="pt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="rounded-full border border-line px-5 py-2.5 text-[13px] font-bold text-ink"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-full bg-mint-dim px-6 py-2.5 text-[13px] font-bold text-navy-950 hover:bg-mint"
            >
              Save Vitals
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
