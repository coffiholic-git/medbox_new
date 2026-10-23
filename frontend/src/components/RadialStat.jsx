import { motion } from "framer-motion";
import { useCountUp } from "../hooks/useCountUp";

/**
 * A small animated radial "gauge" — a ring that fills to `value` percent,
 * with a count-up number in the center. Used for at-a-glance stats.
 */
export default function RadialStat({
  value = 0,
  size = 72,
  stroke = 7,
  color = "var(--color-mint)",
  trackColor = "var(--color-line)",
  label,
  suffix = "%",
  icon: Icon,
  showValue = true,
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  const animated = useCountUp(clamped);

  return (
    <div className="flex items-center gap-3">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={trackColor} strokeWidth={stroke} />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference * (1 - clamped / 100) }}
            transition={{ duration: 0.9, ease: "easeOut" }}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        {(Icon || showValue) && (
          <div className="absolute inset-0 grid place-items-center">
            {Icon ? (
              <Icon size={size * 0.28} style={{ color }} />
            ) : (
              <span className="font-mono text-[13px] font-bold text-ink">
                {Math.round(animated)}
                <span className="text-[10px] text-muted">{suffix}</span>
              </span>
            )}
          </div>
        )}
      </div>
      {label && <span className="text-[12.5px] font-bold text-muted">{label}</span>}
    </div>
  );
}
