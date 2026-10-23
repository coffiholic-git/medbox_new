// Vibration-based feedback (navigator.vibrate). Sighted users get an
// animation; screen-reader users get spoken/announced text; this is the
// third channel — a confirmation you can feel without looking or even
// listening, which matters most on a phone in a pocket or a noisy room.
// Silently does nothing on browsers/devices without the Vibration API
// (iOS Safari, desktop) — always safe to call.

const PATTERNS = {
  tap: 10,
  success: [12, 40, 18],
  error: [30, 60, 30, 60, 30],
  warning: [20, 50, 20],
  alert: [40, 80, 40, 80, 40, 80, 60], // SOS / emergency — long, unmistakable
};

function supported() {
  return typeof navigator !== "undefined" && typeof navigator.vibrate === "function";
}

/**
 * @param {keyof PATTERNS | number | number[]} pattern - a named pattern, or
 *   a raw vibrate() pattern (ms, or [vibrate, pause, vibrate, ...]).
 * @param {boolean} enabled - gate on the user's haptics preference.
 */
export function vibrate(pattern = "tap", enabled = true) {
  if (!enabled || !supported()) return;
  try {
    navigator.vibrate(typeof pattern === "string" ? PATTERNS[pattern] || PATTERNS.tap : pattern);
  } catch {
    // Vibration API can throw in some embedded/iframe contexts — never
    // let a haptic cue break the actual action it's confirming.
  }
}

export const haptics = {
  tap: (enabled) => vibrate("tap", enabled),
  success: (enabled) => vibrate("success", enabled),
  error: (enabled) => vibrate("error", enabled),
  warning: (enabled) => vibrate("warning", enabled),
  alert: (enabled) => vibrate("alert", enabled),
};
