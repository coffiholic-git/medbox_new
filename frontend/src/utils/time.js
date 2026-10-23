// Time helpers for schedules, countdowns and adherence math.

export function minutesFromLabel(label) {
  // "8:00 PM" -> minutes since midnight
  const m = label.match(/(\d+):(\d+)\s*(AM|PM)/i);
  if (!m) return 0;
  let [, h, min, ampm] = m;
  h = parseInt(h, 10);
  min = parseInt(min, 10);
  if (/pm/i.test(ampm) && h !== 12) h += 12;
  if (/am/i.test(ampm) && h === 12) h = 0;
  return h * 60 + min;
}

export function nextOccurrence(timeLabel) {
  const now = new Date();
  const target = new Date(now);
  const mins = minutesFromLabel(timeLabel);
  target.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
  if (target <= now) target.setDate(target.getDate() + 1);
  return target;
}

export function formatCountdown(ms) {
  if (ms <= 0) return "Due now";
  const totalMinutes = Math.floor(ms / 60000);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h <= 0) return `In ${m} minute${m === 1 ? "" : "s"}`;
  return `In ${h} hour${h === 1 ? "" : "s"}, ${m} minute${m === 1 ? "" : "s"}`;
}

export function todayKey(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

export function dayLabel(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function last7Days() {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d;
  });
}

/**
 * Parses diverse expiry date formats:
 * - "Nov 2027", "FEB 2030"
 * - "11/2027", "11/27", "12-2026"
 * - "2027-11"
 * Returns a Date set to the end of the specified month, or null if unparseable.
 */
export function parseExpiryDate(expiryStr) {
  if (!expiryStr) return null;
  const str = String(expiryStr).trim();
  const monthMap = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11
  };
  // Format: "Nov 2027", "FEB 2030", "November 2028"
  const m1 = str.match(/^([a-z]{3,9})[\s./-]+(\d{2,4})$/i);
  if (m1) {
    const month = monthMap[m1[1].slice(0, 3).toLowerCase()];
    let year = parseInt(m1[2], 10);
    if (year < 100) year += 2000;
    if (month !== undefined) {
      return new Date(year, month + 1, 0, 23, 59, 59);
    }
  }
  // Format: "MM/YYYY", "MM/YY", "MM-YY", "MM.YYYY"
  const m2 = str.match(/^(\d{1,2})[\s./-]+(\d{2,4})$/);
  if (m2) {
    const month = parseInt(m2[1], 10) - 1;
    let year = parseInt(m2[2], 10);
    if (year < 100) year += 2000;
    if (month >= 0 && month <= 11) {
      return new Date(year, month + 1, 0, 23, 59, 59);
    }
  }
  // Format: "YYYY-MM"
  const m3 = str.match(/^(\d{4})[\s./-]+(\d{1,2})$/);
  if (m3) {
    const year = parseInt(m3[1], 10);
    const month = parseInt(m3[2], 10) - 1;
    if (month >= 0 && month <= 11) {
      return new Date(year, month + 1, 0, 23, 59, 59);
    }
  }
  const parsed = new Date(str);
  return isNaN(parsed.getTime()) ? null : parsed;
}

export function isMedicineExpired(expiryStr) {
  const d = parseExpiryDate(expiryStr);
  if (!d) return false;
  return d.getTime() < Date.now();
}

export function isMedicineExpiringSoon(expiryStr, days = 60) {
  const d = parseExpiryDate(expiryStr);
  if (!d) return false;
  const diff = d.getTime() - Date.now();
  return diff > 0 && diff < days * 24 * 60 * 60 * 1000;
}

