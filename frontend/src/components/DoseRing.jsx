import { useEffect, useState } from "react";
import { nextOccurrence } from "../utils/time";

const WINDOW_MS = 12 * 60 * 60 * 1000; // ring represents a 12h cycle

export default function DoseRing({ timeLabel, size = 96 }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const target = nextOccurrence(timeLabel).getTime();
  const remaining = Math.max(0, target - now);
  const elapsedFraction = Math.min(1, 1 - remaining / WINDOW_MS);

  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - elapsedFraction);

  const urgent = remaining < 60 * 60 * 1000;
  const soon = remaining < 3 * 60 * 60 * 1000;
  const stroke = urgent ? "var(--color-coral)" : soon ? "var(--color-lime)" : "var(--color-mint)";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0" aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-line)" strokeWidth="6" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={stroke}
        strokeWidth="6"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 0.6s ease, stroke 0.6s ease" }}
      />
    </svg>
  );
}
