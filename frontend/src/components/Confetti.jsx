import { AnimatePresence, motion } from "framer-motion";

const COLORS = ["var(--color-mint)", "var(--color-lime)", "var(--color-coral)"];

function makeParticles(count) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4;
    const distance = 46 + Math.random() * 34;
    return {
      id: i,
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance,
      color: COLORS[i % COLORS.length],
      size: 5 + Math.random() * 4,
    };
  });
}

/**
 * Renders a short burst of particles from the center whenever `fire`
 * changes to a new truthy value. Pass an incrementing key/timestamp.
 */
export default function Confetti({ fire }) {
  const particles = fire ? makeParticles(14) : [];

  return (
    <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center">
      <AnimatePresence>
        {fire &&
          particles.map((p) => (
            <motion.span
              key={`${fire}-${p.id}`}
              className="absolute rounded-full"
              style={{ width: p.size, height: p.size, background: p.color }}
              initial={{ x: 0, y: 0, opacity: 1, scale: 0.6 }}
              animate={{ x: p.x, y: p.y, opacity: 0, scale: 1 }}
              transition={{ duration: 0.75, ease: "easeOut" }}
            />
          ))}
      </AnimatePresence>
    </div>
  );
}
