import { motion } from "framer-motion";
import { Pill, Play, Pencil, Trash2, WifiOff } from "lucide-react";
import { colorTokens } from "../data/seed";
import { useStore } from "../store/useStore";
import { haptics } from "../utils/haptics";

export default function MedicineCard({ medicine, onSpeak, onEdit, onDelete, compact = false, index = 0 }) {
  const tone = colorTokens[medicine.color] || colorTokens.mint;
  const hapticsEnabled = useStore((s) => s.hapticsEnabled);

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.2, delay: Math.min(index * 0.04, 0.3) }}
      whileHover={{ y: -2, boxShadow: "0 12px 28px -16px rgba(139,92,246,0.35)" }}
      className="flex items-center gap-4 rounded-2xl border border-line bg-navy-800/70 p-4 transition hover:border-mint/30"
    >
      <motion.span
        whileHover={{ rotate: -10, scale: 1.1 }}
        transition={{ type: "spring", stiffness: 300, damping: 15 }}
        className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${tone.soft} ${tone.border} border`}
      >
        <Pill size={18} className="text-ink" />
      </motion.span>
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-[15px] font-bold text-ink">
          {medicine.name} <span className="font-medium text-muted">{medicine.strength}</span>
        </h3>
        <p className="mt-0.5 truncate text-[13px] text-muted">{medicine.instructions || `${medicine.form} · ${medicine.time}`}</p>
        {!compact && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full border border-line px-2.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wide text-muted">
              {medicine.frequency}
            </span>
            {medicine.offline && (
              <span className="flex items-center gap-1 rounded-full border border-line px-2.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wide text-mint">
                <WifiOff size={10} /> offline ready
              </span>
            )}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={() => {
            haptics.tap(hapticsEnabled);
            onSpeak?.(`${medicine.name}, ${medicine.strength}. ${medicine.instructions}.`);
          }}
          aria-label={`Hear ${medicine.name} details`}
          className="grid h-9 w-9 place-items-center rounded-full border border-line text-ink transition hover:border-mint hover:text-mint"
        >
          <Play size={14} fill="currentColor" />
        </button>
        {onEdit && (
          <button
            onClick={() => onEdit(medicine)}
            aria-label={`Edit ${medicine.name}`}
            className="grid h-9 w-9 place-items-center rounded-full border border-line text-muted transition hover:border-lime hover:text-lime"
          >
            <Pencil size={14} />
          </button>
        )}
        {onDelete && (
          <button
            onClick={() => onDelete(medicine)}
            aria-label={`Remove ${medicine.name}`}
            className="grid h-9 w-9 place-items-center rounded-full border border-line text-muted transition hover:border-coral hover:text-coral"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </motion.article>
  );
}
