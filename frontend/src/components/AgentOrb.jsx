/**
 * Animated iridescent "AI orb" — replaces the plain mic-icon look for the
 * MedBox assistant with a soft, glassy, continuously-drifting blob (see
 * index.css's ".orb" rules for the actual animation).
 *
 * Pure CSS (no images/canvas/WebGL), so it's cheap to render anywhere the
 * assistant needs a face: the floating launcher, the chat header, and the
 * "thinking" indicator all reuse this one component at different sizes.
 *
 * @param {number} size - diameter in px.
 * @param {"idle"|"listening"|"thinking"} state - controls animation speed/glow.
 * @param {string} className - extra classes for positioning/margins.
 */
export default function AgentOrb({ size = 56, state = "idle", className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={`orb orb-${state} ${className}`}
      style={{ width: size, height: size }}
    >
      <span className="orb-blob orb-blob-1" />
      <span className="orb-blob orb-blob-2" />
      <span className="orb-blob orb-blob-3" />
      <span className="orb-blob orb-blob-4" />
      <span className="orb-sheen" />
      <span className="orb-rim" />
    </span>
  );
}
