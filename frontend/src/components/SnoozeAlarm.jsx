import { useEffect, useState } from "react";
import { BellRing, Check } from "lucide-react";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";
import { useSpeech } from "../hooks/useSpeech";

// Lives beside the app shell so a snooze alarm survives route changes.
export default function SnoozeAlarm() {
  const snoozed = useStore((s) => s.snoozed);
  const medicines = useStore((s) => s.medicines);
  const clearSnooze = useStore((s) => s.clearSnooze);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const [dueMedicine, setDueMedicine] = useState(null);
  const { speak } = useSpeech();

  useEffect(() => {
    const entries = Object.entries(snoozed).filter(([, until]) => until > Date.now());
    if (!entries.length) return undefined;

    const [medId, until] = entries.reduce((earliest, entry) => entry[1] < earliest[1] ? entry : earliest);
    const timer = window.setTimeout(() => {
      const medicine = medicines.find((med) => med.id === medId);
      clearSnooze(medId);
      setDueMedicine(medicine || { name: "your medicine" });
      sound.playAlarm(soundEnabled);
      speak(`Snooze finished. It is time to take ${medicine?.name || "your medicine"}.`);
    }, Math.max(0, until - Date.now()));

    return () => window.clearTimeout(timer);
  }, [snoozed, medicines, clearSnooze, soundEnabled, speak]);

  if (!dueMedicine) return null;
  return (
    <div role="alert" className="fixed inset-x-4 top-4 z-[100] mx-auto max-w-lg rounded-2xl border border-coral bg-navy-900 p-4 shadow-2xl">
      <div className="flex items-center gap-3">
        <BellRing className="shrink-0 text-coral animate-pulse" size={24} />
        <div className="min-w-0 flex-1">
          <strong className="block text-ink">Snooze finished</strong>
          <span className="text-[13px] text-muted">Time to take {dueMedicine.name}.</span>
        </div>
        <button onClick={() => setDueMedicine(null)} className="inline-flex items-center gap-1 rounded-full bg-mint-dim px-3 py-2 text-[12px] font-bold text-navy-950">
          <Check size={14} /> Dismiss
        </button>
      </div>
    </div>
  );
}
