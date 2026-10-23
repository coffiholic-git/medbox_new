import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, Clock3, Calendar, ListFilter, Grid, BellOff, RefreshCw, AlertTriangle } from "lucide-react";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";
import { sound } from "../utils/audio";
import RadialStat from "../components/RadialStat";
import PillVisualizer from "../components/PillVisualizer";
import RefillModal from "../components/RefillModal";
import { todayKey } from "../utils/time";

function buildDays() {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - 3 + i);
    return d;
  });
}

export default function Schedule() {
  const medicines = useStore((s) => s.medicines);
  const logs = useStore((s) => s.logs);
  const snoozed = useStore((s) => s.snoozed);
  const snoozeDose = useStore((s) => s.snoozeDose);
  const logDose = useStore((s) => s.logDose);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const pushToast = useStore((s) => s.pushToast);
  const { speak } = useSpeech();

  const days = useMemo(buildDays, []);
  const [selected, setSelected] = useState(() => todayKey());
  const [viewMode, setViewMode] = useState("timeline"); // timeline | weekly | calendar
  const [refillMed, setRefillMed] = useState(null);

  const isToday = selected === todayKey();
  const selectedDate = days.find((d) => todayKey(d) === selected) || new Date();
  const scheduled = medicines.filter((m) => m.frequency !== "weekly" || selectedDate.getDay() === 0);
  const dayLogs = logs[selected] || {};

  const takenCount = scheduled.filter((m) => dayLogs[m.id] === "taken").length;
  const progress = scheduled.length ? Math.round((takenCount / scheduled.length) * 100) : 0;

  const setStatus = (med, status) => {
    logDose(med.id, status, selected);
    if (status === "taken") {
      sound.playChime(soundEnabled);
      pushToast(`${med.name} marked as taken.`, "success");
      speak(`${med.name} marked as taken.`);
    } else {
      sound.playClick(soundEnabled);
      pushToast(`${med.name} marked as missed.`);
    }
  };

  const handleSnooze = (medId, minutes) => {
    snoozeDose(medId, minutes);
    sound.playClick(soundEnabled);
    pushToast(`Dose snoozed for ${minutes} minutes.`);
  };

  return (
    <div className="pt-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="font-mono text-[11px] uppercase tracking-wide text-mint">Schedule Workstation</span>
          <h1 className="mt-1 text-[30px] font-extrabold tracking-tight text-ink">
            {isToday ? "Today's Medication Matrix" : selectedDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center rounded-full border border-line bg-navy-800/60 p-1 font-mono text-[12px]">
          <button
            onClick={() => setViewMode("timeline")}
            className={`flex items-center gap-1 rounded-full px-3 py-1.5 font-bold transition ${
              viewMode === "timeline" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
          >
            <ListFilter size={13} /> Timeline
          </button>
          <button
            onClick={() => setViewMode("weekly")}
            className={`flex items-center gap-1 rounded-full px-3 py-1.5 font-bold transition ${
              viewMode === "weekly" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
          >
            <Grid size={13} /> Weekly Grid
          </button>
        </div>
      </div>

      {/* Date Carousel Bar */}
      <div className="mt-5 flex gap-2 overflow-x-auto pb-1 scrollbar-none">
        {days.map((d) => {
          const key = todayKey(d);
          const active = key === selected;
          return (
            <motion.button
              key={key}
              onClick={() => setSelected(key)}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.94 }}
              animate={active ? { scale: [1, 1.06, 1] } : { scale: 1 }}
              transition={{ duration: 0.3 }}
              className={`flex min-w-[64px] flex-col items-center gap-1 rounded-2xl border px-3 py-2.5 transition ${
                active ? "border-mint-dim bg-mint-dim text-navy-950" : "border-line text-ink hover:border-mint/50"
              }`}
            >
              <span className="font-mono text-[10px] uppercase tracking-wide opacity-80">
                {d.toLocaleDateString(undefined, { weekday: "short" })}
              </span>
              <span className="text-[16px] font-extrabold">{d.getDate()}</span>
            </motion.button>
          );
        })}
      </div>

      {/* Progress Header */}
      <div className="mt-6 flex items-center gap-5 rounded-2xl p-5" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(24px)", boxShadow: "var(--glass-shadow)" }}>
        <RadialStat value={progress} size={58} stroke={6} color="var(--color-mint)" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between text-[13px] font-bold text-ink">
            <span>{takenCount} of {scheduled.length} doses logged</span>
            <span className="font-mono text-mint">{progress}% Complete</span>
          </div>
          <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-navy-700">
            <motion.div
              className="h-full rounded-full bg-mint"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            />
          </div>
        </div>
      </div>

      {/* TIMELINE VIEW */}
      {viewMode === "timeline" && (
        <div className="mt-5 space-y-3">
          {scheduled.length === 0 && (
            <p className="rounded-2xl border border-line bg-navy-800/40 p-6 text-center text-muted">
              Nothing scheduled for this day.
            </p>
          )}
          <AnimatePresence mode="popLayout">
            {scheduled.map((m, i) => {
              const status = dayLogs[m.id];
              const isSnoozed = snoozed[m.id] && snoozed[m.id] > Date.now();
              const isLowStock = m.stock !== undefined && m.stock <= 5;

              return (
                <motion.div
                  key={m.id}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.25 }}
                  whileHover={{ y: -2, borderColor: "rgba(139,92,246,0.3)" }}
                  className={`flex flex-col gap-3 rounded-2xl p-4 transition-colors sm:flex-row sm:items-center sm:justify-between ${
                    status === "taken"
                      ? "border-[rgba(125,211,252,0.25)] bg-[rgba(125,211,252,0.05)]"
                      : status === "missed"
                      ? "border-[rgba(244,114,182,0.25)] bg-[rgba(244,114,182,0.05)]"
                      : ""
                  }`}
                  style={!status ? { background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" } : { border: "1px solid", backdropFilter: "blur(20px)" }}
                >
                  <div className="flex items-center gap-3.5">
                    <PillVisualizer form={m.form} color={m.color} size="md" />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-[15px] font-bold text-ink">
                          {m.name} <span className="font-medium text-muted">{m.strength}</span>
                        </h3>
                        {isSnoozed && (
                          <span className="rounded-full bg-coral/20 px-2 py-0.5 font-mono text-[9px] text-coral border border-coral/30">
                            Snoozed 15m
                          </span>
                        )}
                        {isLowStock && (
                          <button
                            onClick={() => setRefillMed(m)}
                            className="flex items-center gap-1 rounded-full bg-coral/20 px-2 py-0.5 font-mono text-[9px] text-coral border border-coral/30 hover:bg-coral hover:text-navy-950"
                          >
                            <AlertTriangle size={10} /> {m.stock} left (Refill)
                          </button>
                        )}
                      </div>
                      <p className="text-[13px] text-muted">{m.instructions} · {m.time}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
                    <motion.button
                      whileTap={{ scale: 0.92 }}
                      onClick={() => handleSnooze(m.id, 15)}
                      title="Snooze dose"
                      className="flex items-center gap-1 rounded-full border border-line px-3 py-2 text-[11.5px] font-bold text-muted hover:border-mint hover:text-mint"
                    >
                      <BellOff size={12} /> Snooze
                    </motion.button>

                    <motion.button
                      whileTap={{ scale: 0.92 }}
                      onClick={() => setStatus(m, "taken")}
                      aria-pressed={status === "taken"}
                      className={`flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-[12.5px] font-bold transition ${
                        status === "taken" ? "border-mint-dim bg-mint-dim text-navy-950" : "border-line text-ink hover:border-mint hover:text-mint"
                      }`}
                    >
                      <Check size={13} /> Taken
                    </motion.button>
                    <motion.button
                      whileTap={{ scale: 0.92 }}
                      onClick={() => setStatus(m, "missed")}
                      aria-pressed={status === "missed"}
                      className={`flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-[12.5px] font-bold transition ${
                        status === "missed" ? "border-coral bg-coral text-navy-950" : "border-line text-ink hover:border-coral hover:text-coral"
                      }`}
                    >
                      <X size={13} /> Missed
                    </motion.button>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* WEEKLY MATRIX GRID VIEW */}
      {viewMode === "weekly" && (
        <div className="mt-5 rounded-2xl p-5 overflow-x-auto" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(24px)" }}>
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-line text-muted font-mono text-[11px] uppercase">
                <th className="pb-3">Medication</th>
                {days.map((d) => (
                  <th key={todayKey(d)} className="pb-3 text-center">
                    {d.toLocaleDateString(undefined, { weekday: "short" })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40">
              {medicines.map((m) => (
                <tr key={m.id}>
                  <td className="py-3.5 font-bold text-ink">
                    {m.name} <span className="block text-[11px] font-normal text-muted">{m.time}</span>
                  </td>
                  {days.map((d) => {
                    const key = todayKey(d);
                    const st = logs[key]?.[m.id];
                    return (
                      <td key={key} className="py-3.5 text-center">
                        {st === "taken" ? (
                          <span className="inline-grid h-7 w-7 place-items-center rounded-full bg-mint/20 text-mint">
                            <Check size={14} />
                          </span>
                        ) : st === "missed" ? (
                          <span className="inline-grid h-7 w-7 place-items-center rounded-full bg-coral/20 text-coral">
                            <X size={14} />
                          </span>
                        ) : (
                          <span className="inline-block h-2 w-2 rounded-full bg-line" />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <RefillModal open={!!refillMed} onClose={() => setRefillMed(null)} medicine={refillMed} />
    </div>
  );
}
