import Modal from "./Modal";
import { useStore } from "../store/useStore";
import { Check } from "lucide-react";

const sizes = [
  { id: "base", label: "Standard" },
  { id: "lg", label: "Large" },
  { id: "xl", label: "Extra large" },
];

export default function SettingsSheet({ open, onClose }) {
  const textSize = useStore((s) => s.textSize);
  const setTextSize = useStore((s) => s.setTextSize);
  const highContrast = useStore((s) => s.highContrast);
  const toggleHighContrast = useStore((s) => s.toggleHighContrast);
  const reduceMotion = useStore((s) => s.reduceMotion);
  const toggleReduceMotion = useStore((s) => s.toggleReduceMotion);
  const hapticsEnabled = useStore((s) => s.hapticsEnabled);
  const toggleHaptics = useStore((s) => s.toggleHaptics);

  return (
    <Modal open={open} onClose={onClose} title="Make it comfortable" labelledBy="settingsTitle" width="max-w-md">
      <p className="text-[14px] leading-relaxed text-muted">
        These settings apply everywhere in MedBox, right away.
      </p>

      <div className="mt-6">
        <h3 className="font-mono text-[11px] uppercase tracking-wide text-muted">Text size</h3>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {sizes.map((s) => (
            <button
              key={s.id}
              onClick={() => setTextSize(s.id)}
              aria-pressed={textSize === s.id}
              className={`rounded-xl border px-3 py-3 text-[13px] font-bold transition ${
                textSize === s.id ? "border-mint-dim bg-mint-dim text-navy-950" : "border-line text-ink hover:border-mint/60"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 space-y-3">
        <ToggleRow
          label="High contrast"
          description="Pure black background with brighter text."
          checked={highContrast}
          onChange={toggleHighContrast}
        />
        <ToggleRow
          label="Reduce motion"
          description="Turn off ripples, transitions and animated charts."
          checked={reduceMotion}
          onChange={toggleReduceMotion}
        />
        <ToggleRow
          label="Vibration feedback"
          description="Feel a pulse for confirmations, alerts and SOS — helpful without looking at the screen."
          checked={hapticsEnabled}
          onChange={toggleHaptics}
        />
      </div>
    </Modal>
  );
}

function ToggleRow({ label, description, checked, onChange }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-line bg-navy-900/60 px-4 py-3.5">
      <div>
        <p className="text-[14px] font-bold text-ink">{label}</p>
        <p className="text-[12.5px] text-muted">{description}</p>
      </div>
      <button
        onClick={onChange}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className={`relative h-7 w-12 shrink-0 rounded-full transition ${checked ? "bg-mint-dim" : "bg-navy-700"}`}
      >
        <span
          className={`absolute top-0.5 grid h-6 w-6 place-items-center rounded-full bg-navy-950 transition-transform ${
            checked ? "translate-x-[22px]" : "translate-x-0.5"
          }`}
        >
          {checked && <Check size={13} className="text-mint" />}
        </span>
      </button>
    </div>
  );
}
