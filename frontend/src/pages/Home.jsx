import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ScanLine,
  CalendarClock,
  Library as LibraryIcon,
  ShieldCheck,
  ArrowUpRight,
  ArrowRight,
  TrendingUp,
  Flame,
  AlertTriangle,
  Clock,
  RefreshCw,
  Activity,
  Check,
  Radio,
  Pill,
  Plus
} from "lucide-react";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";
import { useAgentAssistant } from "../hooks/useAgentAssistant";
import { useCountUp } from "../hooks/useCountUp";
import { sound } from "../utils/audio";
import AgentOrb from "../components/AgentOrb";
import DoseRing from "../components/DoseRing";
import MedicineCard from "../components/MedicineCard";
import RadialStat from "../components/RadialStat";
import Sparkline from "../components/Sparkline";
import Confetti from "../components/Confetti";
import VitalsTracker from "../components/VitalsTracker";
import RefillModal from "../components/RefillModal";
import AddMedicineModal from "../components/AddMedicineModal";
import PillVisualizer from "../components/PillVisualizer";
import { nextOccurrence, formatCountdown, todayKey } from "../utils/time";

const actionShortcuts = [
  { to: "/scan", icon: ScanLine, title: "Scan Medicine", desc: "Camera / Image OCR", color: "mint" },
  { to: "/schedule", icon: CalendarClock, title: "Schedule Matrix", desc: "Timelines & Snooze", color: "lime" },
  { to: "/safety", icon: ShieldCheck, title: "Safety Checker", desc: "Drug Interactions", color: "coral" },
];

function getGreeting(name) {
  const hour = new Date().getHours();
  if (hour < 12) return `Good morning, ${name}`;
  if (hour < 18) return `Good afternoon, ${name}`;
  return `Good evening, ${name}`;
}

function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export default function Home() {
  const patientName = useStore((s) => s.patientName);
  const medicines = useStore((s) => s.medicines);
  const snoozed = useStore((s) => s.snoozed);
  const snoozeDose = useStore((s) => s.snoozeDose);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const pushToast = useStore((s) => s.pushToast);
  const logDose = useStore((s) => s.logDose);
  const logs = useStore((s) => s.logs);
  const adherenceForRange = useStore((s) => s.adherenceForRange);
  const navigate = useNavigate();
  const now = useNow();

  const [feedback, setFeedback] = useState('Voice ready — tap and ask anything, e.g. "What do I take now?"');
  const [celebrate, setCelebrate] = useState(0);
  const [refillMed, setRefillMed] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  // Shared with the global AgentAssistant drawer (components/AgentAssistant.jsx)
  // — same transcript and backend call, so this mic button and that panel
  // are two views onto one conversation instead of separate ones.
  const { agentBusy, sendMessage } = useAgentAssistant();

  const lowStockMeds = useMemo(() => {
    return medicines.filter((m) => (m.stock !== undefined ? m.stock <= 5 : false));
  }, [medicines]);

  const weekData = useMemo(() => adherenceForRange(7), [adherenceForRange, logs]);
  const weekRates = weekData.map((d) => d.rate);
  const avgRate = Math.round(weekRates.reduce((a, b) => a + b, 0) / weekRates.length) || 0;
  const streak = useMemo(() => {
    let count = 0;
    for (let i = weekData.length - 1; i >= 0; i--) {
      if (weekData[i].rate === 100 && weekData[i].scheduled > 0) count++;
      else break;
    }
    return count;
  }, [weekData]);
  const animatedStreak = useCountUp(streak);

  // Builds the AgentContext snapshot and executes returned actions via
  // hooks/useAgentAssistant.js (shared with the global chat drawer so both
  // surfaces stay in sync on one transcript).
  const handleCommand = async (transcript) => {
    sound.playBeep(soundEnabled);
    setFeedback(`Heard: "${transcript}" — thinking…`);
    const reply = await sendMessage(transcript, navigate);
    if (!reply) {
      const message = "The AI assistant did not respond. Please try again.";
      setFeedback(message);
      speak(message);
      return;
    }
    setFeedback(reply);
    speak(reply);
  };

  const { listen, speak, listening, supported } = useSpeech({
    onResult: handleCommand,
    onError: (message) => setFeedback(message),
  });

  const nextDose = useMemo(() => {
    const withTimes = medicines.map((m) => ({ m, at: nextOccurrence(m.time) }));
    withTimes.sort((a, b) => a.at - b.at);
    return withTimes[0];
  }, [medicines, now]);

  const isSnoozed = nextDose && snoozed[nextDose.m.id] && snoozed[nextDose.m.id] > Date.now();

  const onListen = () => {
    sound.playClick(soundEnabled);
    if (!supported) {
      const message = "Voice commands need Chrome or Edge with microphone permission enabled.";
      setFeedback(message);
      speak(message);
      return;
    }
    setFeedback("Listening…");
    listen();
  };

  const markTaken = () => {
    if (!nextDose) return;
    logDose(nextDose.m.id, "taken");
    sound.playChime(soundEnabled);
    pushToast(`${nextDose.m.name} marked as taken.`, "success");
    speak(`${nextDose.m.name} has been marked as taken. Excellent!`);
    setCelebrate(Date.now());
  };

  const handleSnooze = () => {
    if (!nextDose) return;
    snoozeDose(nextDose.m.id, 15);
    sound.playClick(soundEnabled);
    pushToast(`${nextDose.m.name} snoozed for 15 minutes.`);
  };

  return (
    <div className="space-y-5 pt-2">
      {/* Low Stock Alert Ticker */}
      {lowStockMeds.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-coral/40 bg-coral/10 px-4 py-2.5 text-[13px] text-ink"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-coral shrink-0" />
            <span>
              Pill Inventory Alert: <strong>{lowStockMeds.map((m) => m.name).join(", ")}</strong> stock is low ({lowStockMeds[0].stock} left).
            </span>
          </div>
          <button
            onClick={() => setRefillMed(lowStockMeds[0])}
            className="flex items-center gap-1 rounded-full bg-coral px-3.5 py-1 text-[11.5px] font-bold text-navy-950 hover:opacity-90"
          >
            <RefreshCw size={12} /> Refill Now
          </button>
        </motion.div>
      )}

      {/* Sleek Top Header Command Bar */}
      <section className="flex flex-col gap-4 rounded-[24px] p-5 backdrop-blur-sm md:flex-row md:items-center md:justify-between" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border-vivid)", boxShadow: "var(--glass-shadow)" }}>
        <div>
          <div className="inline-flex items-center gap-2 rounded-full px-2.5 py-1 font-mono text-[10.5px] text-mint" style={{ background: "rgba(125,211,252,0.07)", border: "1px solid rgba(125,211,252,0.2)" }}>
            <Radio size={12} className="text-lime animate-pulse" />
            LIVE MEDICAL WORKSTATION
          </div>
          <h1 className="mt-1 text-[26px] font-extrabold tracking-tight text-ink sm:text-[32px]">
            {getGreeting(patientName)}.
          </h1>
          <p className="text-[13.5px] text-muted">
            Overview of upcoming doses, compliance streak, and health vitals.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Add Medicine Button on Dashboard */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setAddModalOpen(true)}
            id="dashboard-add-medicine-btn"
            className="flex items-center gap-2 rounded-2xl bg-mint px-4 py-2.5 text-[13.5px] font-extrabold text-navy-950 shadow-[0_0_20px_rgba(45,212,191,0.25)] transition hover:brightness-105"
          >
            <Plus size={17} strokeWidth={2.5} />
            <span>Add Medicine</span>
          </motion.button>

          {/* Compact Voice Assistant Control */}
          <div className="flex items-center gap-3 rounded-2xl px-4 py-2.5" style={{ background: "var(--glass-bg-deep)", border: "1px solid var(--glass-border)", boxShadow: "inset 0 1px 0 rgba(125,211,252,0.05)" }}>
            <button
              onClick={onListen}
              aria-label="Activate AI voice assistant"
              className="grid h-11 w-11 shrink-0 place-items-center rounded-xl"
            >
              <AgentOrb size={40} state={listening ? "listening" : agentBusy ? "thinking" : "idle"} />
            </button>
            <div className="min-w-0 pr-2" aria-live="polite">
              <span className="block text-[11px] font-mono uppercase text-mint">
                AI Voice Assistant{agentBusy ? " — thinking…" : ""}
              </span>
              <span className="block truncate text-[12.5px] text-muted">{feedback}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Workstation Dashboard Grid (Above the fold!) */}
      <section className="grid gap-4 md:grid-cols-3">
        {/* Next Dose Card */}
        <article className="relative overflow-hidden rounded-[24px] p-5 flex flex-col justify-between" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(24px)", boxShadow: "var(--glass-shadow)" }}>
          <Confetti fire={celebrate} />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10.5px] uppercase tracking-wide text-mint">Up Next</span>
              <Link to="/schedule" className="flex items-center gap-1 text-[12px] font-bold text-muted hover:text-mint">
                Schedule <ArrowRight size={13} />
              </Link>
            </div>

            {nextDose ? (
              <div className="mt-4 flex items-center gap-4">
                <DoseRing timeLabel={nextDose.m.time} size={64} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <h3 className="text-[16px] font-bold text-ink">
                      {nextDose.m.name}
                    </h3>
                    <span className="font-medium text-[12px] text-muted">{nextDose.m.strength}</span>
                  </div>
                  <p className="mt-0.5 text-[12.5px] text-muted">{nextDose.m.instructions}</p>
                  <p className="mt-1.5 font-mono text-[11.5px] text-lime">
                    {isSnoozed ? "Snoozed 15m" : formatCountdown(nextDose.at - now)} · Stock: {nextDose.m.stock ?? 30}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-[13px] text-muted">No medicines scheduled for today.</p>
            )}
          </div>

          {nextDose && (
            <div className="mt-4 flex items-center gap-2">
              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.97 }}
                onClick={markTaken}
                className="flex-1 rounded-xl bg-mint-dim py-2.5 text-[13px] font-bold text-navy-950 transition hover:bg-mint"
              >
                Mark Taken
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleSnooze}
                className="rounded-xl border border-line px-3 py-2.5 text-[12.5px] font-bold text-ink hover:border-coral hover:text-coral"
              >
                <Clock size={14} className="inline mr-1" /> Snooze
              </motion.button>
            </div>
          )}
        </article>

        {/* Adherence & Streak Card */}
        <article className="rounded-[24px] p-5 flex flex-col justify-between" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border-violet)", backdropFilter: "blur(24px)", boxShadow: "var(--glass-shadow)" }}>
          <div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10.5px] uppercase tracking-wide text-lime">Adherence Trend</span>
              <span className="flex items-center gap-1 font-mono text-[11px] text-lime">
                <Flame size={13} /> {Math.round(animatedStreak)}-day streak
              </span>
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <RadialStat value={avgRate} size={54} stroke={5} color="var(--color-mint)" />
              <div className="flex-1">
                <p className="text-[13px] font-bold text-ink">7-Day Compliance Rate</p>
                <p className="text-[12px] text-muted">Consistent daily intake habits</p>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-xl p-2.5 flex items-center justify-between" style={{ background: "var(--glass-bg-deep)", border: "1px solid var(--glass-border)" }}>
            <span className="font-mono text-[10.5px] text-muted">Weekly Rate Graph</span>
            <Sparkline data={weekRates} width={100} height={24} color="var(--color-lime)" />
          </div>
        </article>

        {/* Vitals Summary Card */}
        <VitalsTracker />
      </section>

      {/* Instant Actions Bar */}
      <section className="grid gap-3 sm:grid-cols-3">
        {actionShortcuts.map(({ to, icon: Icon, title, desc, color }, i) => (
          <Link
            key={to}
            to={to}
            className="group flex items-center gap-3 rounded-2xl p-3.5 transition-all hover:scale-[1.02]"
            style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)", boxShadow: "var(--glass-shadow-sm)" }}
          >
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-${color}/30 bg-${color}/10 text-${color}`}>
              <Icon size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <strong className="block text-[14px] font-bold text-ink">{title}</strong>
              <small className="block text-[12px] text-muted">{desc}</small>
            </span>
            <ArrowUpRight size={15} className="text-muted group-hover:text-mint transition" />
          </Link>
        ))}
      </section>

      {/* Active Medicine Cabinet Grid */}
      <section className="pt-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Pill size={16} className="text-mint" />
            <h2 className="text-[18px] font-extrabold text-ink">Active Cabinet Inventory</h2>
          </div>
          <div className="flex items-center gap-2.5">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setAddModalOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-mint/40 bg-mint/10 px-3.5 py-1.5 text-[12px] font-bold text-mint hover:bg-mint hover:text-navy-950 transition"
            >
              <Plus size={14} strokeWidth={2.5} /> Add Medicine
            </motion.button>
            <Link to="/library" className="flex items-center gap-1 text-[13px] font-bold text-muted hover:text-mint">
              Manage All ({medicines.length}) <ArrowRight size={14} />
            </Link>
          </div>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {medicines.slice(0, 3).map((m) => (
            <motion.div key={m.id} layout>
              <MedicineCard medicine={m} onSpeak={speak} compact />
            </motion.div>
          ))}
        </div>
      </section>

      <RefillModal open={!!refillMed} onClose={() => setRefillMed(null)} medicine={refillMed} />
      <AddMedicineModal open={addModalOpen} onClose={() => setAddModalOpen(false)} />
    </div>
  );
}
