import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, TrendingUp, Flame, Users, Send, Download, Heart, Activity, Droplet, UserCheck, MessageSquare, RefreshCw, Plus } from "lucide-react";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";
import AdherenceChart from "../components/AdherenceChart";
import RadialStat from "../components/RadialStat";
import { useCountUp } from "../hooks/useCountUp";
import { todayKey } from "../utils/time";
import { fetchCaregiverChatLogAPI } from "../utils/api";
import AddCaregiverModal from "../components/AddCaregiverModal";

// Turns one AgentAction (backend/schemas.py) into a short human-readable
// tag, so a caregiver skimming the transcript can see at a glance what the
// assistant actually did, not just what it said.
function describeAgentAction(action, medicines) {
  const medName = (medId) => medicines.find((m) => m.id === medId)?.name || medId;
  switch (action.type) {
    case "navigate":
      return `Opened ${action.target}`;
    case "mark_taken":
      return `Marked ${medName(action.medId)} as taken`;
    case "snooze":
      return `Snoozed ${medName(action.medId)} ${action.minutes ?? 15}m`;
    case "refill_medicine":
      return `Refilled ${medName(action.medId)} +${action.amount ?? 30}`;
    case "log_vital":
      return `Logged vitals: ${Object.entries(action.vitals || {})
        .map(([k, v]) => `${k}=${v}`)
        .join(", ")}`;
    default:
      return action.type;
  }
}

function formatChatTimestamp(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default function Caregiver() {
  const patientName = useStore((s) => s.patientName || "Maya");
  const medicines = useStore((s) => s.medicines);
  const logs = useStore((s) => s.logs);
  const vitalsLogs = useStore((s) => s.vitalsLogs);
  const adherenceForRange = useStore((s) => s.adherenceForRange);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const pushToast = useStore((s) => s.pushToast);
  const caregivers = useStore((s) => s.caregivers);
  const removeCaregiver = useStore((s) => s.removeCaregiver);

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editingCaregiver, setEditingCaregiver] = useState(null);

  const [timeRange, setTimeRange] = useState(7); // 7, 14, 30 days

  // AI-assistant conversation log — the only section on this page backed by
  // a live backend call (GET /api/caregiver/chat-log) rather than the local
  // demo store, since agent_chat_logs only exists server-side.
  const [chatLog, setChatLog] = useState(null); // null = not loaded yet
  const [chatLogStatus, setChatLogStatus] = useState("idle"); // idle | loading | error | ready

  const loadChatLog = async () => {
    setChatLogStatus("loading");
    const rows = await fetchCaregiverChatLogAPI(30);
    if (rows) {
      setChatLog(rows);
      setChatLogStatus("ready");
    } else {
      setChatLogStatus("error");
    }
  };

  useEffect(() => {
    loadChatLog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rangeData = useMemo(() => adherenceForRange(timeRange), [adherenceForRange, logs, timeRange]);
  const avgRate = Math.round(rangeData.reduce((sum, d) => sum + d.rate, 0) / rangeData.length) || 0;

  const streak = useMemo(() => {
    let count = 0;
    for (let i = rangeData.length - 1; i >= 0; i--) {
      if (rangeData[i].rate === 100 && rangeData[i].scheduled > 0) count++;
      else break;
    }
    return count;
  }, [rangeData]);

  const latestVital = vitalsLogs[vitalsLogs.length - 1] || { bpSystolic: 120, bpDiastolic: 80, glucose: 98, pulse: 72 };

  const missedRecently = useMemo(() => {
    const out = [];
    Object.entries(logs)
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))
      .forEach(([date, dayLogs]) => {
        Object.entries(dayLogs).forEach(([medId, status]) => {
          if (status === "missed") {
            const med = medicines.find((m) => m.id === medId);
            if (med) out.push({ date, med });
          }
        });
      });
    return out.slice(0, 5);
  }, [logs, medicines]);

  const handleSendAlert = () => {
    sound.playClick(soundEnabled);
    pushToast(`Instant WhatsApp & SMS adherence summary sent to Dr. Sarah Jenkins (Caregiver for ${patientName})!`, "success");
  };

  const handleExportReport = () => {
    sound.playClick(soundEnabled);
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify({ patientName, caregiver: "Dr. Sarah Jenkins", logs, vitalsLogs, rangeData }, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `medbox-caregiver-report-${patientName.toLowerCase()}-${todayKey()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    pushToast("Caregiver health report downloaded.", "success");
  };

  return (
    <div className="pt-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Users size={16} className="text-mint" />
            <span className="font-mono text-[11px] uppercase tracking-wide text-mint">Designated Caregiver Portal</span>
          </div>
          <h1 className="mt-1 text-[30px] font-extrabold tracking-tight text-ink">
            {patientName}'s Health & Adherence Station
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSendAlert}
            className="flex items-center gap-1.5 rounded-full border border-line bg-navy-800 px-4 py-2 text-[12.5px] font-bold text-ink hover:border-mint hover:text-mint transition"
          >
            <Send size={13} /> SMS Caregiver Alert
          </button>
          <button
            onClick={handleExportReport}
            className="flex items-center gap-1.5 rounded-full bg-mint-dim px-4 py-2 text-[12.5px] font-bold text-navy-950 hover:bg-mint transition"
          >
            <Download size={13} /> Download Report
          </button>
        </div>
      </div>

      {/* Caregivers Section */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[17px] font-extrabold text-ink">Assigned Caregivers & Physicians</h2>
          <button
            onClick={() => {
              setEditingCaregiver(null);
              setAddModalOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-full border border-line bg-navy-900/60 px-3 py-1.5 text-[11.5px] font-bold text-muted hover:text-ink hover:border-mint transition"
          >
            <Plus size={12} /> Add Caregiver
          </button>
        </div>

        {caregivers?.length === 0 ? (
          <p className="text-[13.5px] text-muted">No caregivers added yet. Please add a primary caregiver.</p>
        ) : (
          caregivers.map((cg) => (
            <div key={cg.id} className="rounded-[24px] border border-mint/40 bg-mint/10 p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-mint text-navy-950 font-black text-[18px]">
                  {cg.name.substring(0, 2).toUpperCase()}
                </div>
                <div>
                  <span className="font-mono text-[10.5px] uppercase text-mint">{cg.relationship || "Caregiver"}</span>
                  <h2 className="text-[18px] font-extrabold text-ink">
                    {cg.name} {cg.qualification && `, ${cg.qualification}`}
                  </h2>
                  <p className="text-[12.5px] text-muted">Assigned to: {cg.assignedPatient || patientName}</p>
                  {(cg.phone || cg.email) && (
                    <p className="text-[12px] text-muted mt-0.5">
                      {cg.phone} {cg.phone && cg.email && " • "} {cg.email}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 font-mono text-[11.5px]">
                <button
                  onClick={() => {
                    setEditingCaregiver(cg);
                    setAddModalOpen(true);
                  }}
                  className="rounded-full bg-navy-900/80 px-3 py-1.5 border border-line text-mint hover:bg-mint hover:text-navy-950 transition flex items-center gap-1.5"
                >
                  Edit
                </button>
                <button
                  onClick={() => removeCaregiver(cg.id)}
                  className="rounded-full bg-navy-900/80 px-3 py-1.5 border border-line text-coral hover:bg-coral hover:text-navy-950 transition flex items-center gap-1.5"
                >
                  Remove
                </button>
                <span className="rounded-full bg-navy-900/80 px-3 py-1.5 border border-line text-mint items-center gap-1.5 hidden md:flex">
                  <span className="h-2 w-2 rounded-full bg-lime animate-pulse" /> Active
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      <AddCaregiverModal open={addModalOpen} onClose={() => setAddModalOpen(false)} caregiver={editingCaregiver} />

      {/* Adherence & Health Vitals Overview Cards */}
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard icon={TrendingUp} label={`${timeRange}-day adherence`} value={avgRate} suffix="%" tone="mint" ring={avgRate} />
        <StatCard icon={Flame} label="Perfect streak" value={streak} suffix={streak === 1 ? " day" : " days"} tone="lime" ring={Math.min(100, (streak / 7) * 100)} />

        {/* Real-time Health Vitals Indicators */}
        <div className="rounded-2xl border border-line bg-navy-800/60 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-muted text-[11px] font-mono">
            <span>BLOOD PRESSURE</span>
            <Heart size={13} className="text-coral" />
          </div>
          <p className="mt-2 text-[22px] font-extrabold text-ink">
            {latestVital.bpSystolic}/{latestVital.bpDiastolic}
          </p>
          <span className="text-[10.5px] text-lime font-mono">Optimal Range</span>
        </div>

        <div className="rounded-2xl border border-line bg-navy-800/60 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-muted text-[11px] font-mono">
            <span>BLOOD GLUCOSE</span>
            <Droplet size={13} className="text-mint" />
          </div>
          <p className="mt-2 text-[22px] font-extrabold text-ink">
            {latestVital.glucose} <span className="text-[11px] font-normal text-muted">mg/dL</span>
          </p>
          <span className="text-[10.5px] text-lime font-mono">Fasting Normal</span>
        </div>
      </div>

      {/* Adherence Trend Chart */}
      <div className="rounded-[26px] border border-line bg-navy-800/60 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-[17px] font-extrabold text-ink">Adherence Trends for {patientName}</h2>
            <p className="text-[12.5px] text-muted">Filter historical compliance data window</p>
          </div>

          <div className="flex items-center gap-1 rounded-full border border-line bg-navy-900/60 p-1 font-mono text-[11px]">
            {[7, 14, 30].map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`rounded-full px-3 py-1 font-bold transition ${
                  timeRange === r ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
                }`}
              >
                {r} Days
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <AdherenceChart data={rangeData} />
        </div>
      </div>

      {/* Missed Doses & Cabinet Inventory */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-[26px] border border-line bg-navy-800/60 p-6">
          <h2 className="text-[17px] font-extrabold text-ink">Recently missed doses</h2>
          {missedRecently.length === 0 ? (
            <p className="mt-3 text-[14px] text-muted">No missed doses recently — great consistency.</p>
          ) : (
            <ul className="mt-3 space-y-2.5">
              {missedRecently.map((item, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ x: 2 }}
                  className="flex items-center justify-between rounded-xl border border-coral/25 bg-coral/[0.06] px-4 py-3"
                >
                  <div>
                    <p className="text-[13.5px] font-bold text-ink">{item.med.name} {item.med.strength}</p>
                    <p className="text-[12px] text-muted">{item.date === todayKey() ? "Today" : item.date}</p>
                  </div>
                  <AlertTriangle size={15} className="text-coral" />
                </motion.li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-[26px] border border-line bg-navy-800/60 p-6">
          <h2 className="text-[17px] font-extrabold text-ink">Active Cabinet Inventory</h2>
          <ul className="mt-3 divide-y divide-line">
            {medicines.map((m, i) => (
              <motion.li
                key={m.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                whileHover={{ x: 2 }}
                className="flex items-center justify-between py-3"
              >
                <div>
                  <p className="text-[13.5px] font-bold text-ink">{m.name} {m.strength}</p>
                  <p className="text-[12px] text-muted">{m.instructions}</p>
                </div>
                <div className="text-right font-mono text-[11px]">
                  <span className="block text-mint font-bold">{m.stock ?? 30} units left</span>
                  <span className="text-muted opacity-80">{m.frequency}</span>
                </div>
              </motion.li>
            ))}
          </ul>
        </div>
      </div>

      {/* AI Assistant Conversation Log — read-only audit trail of what the
          patient asked MedBox's voice assistant and what it did in response. */}
      <div className="rounded-[26px] border border-line bg-navy-800/60 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <MessageSquare size={16} className="text-mint" />
            <h2 className="text-[17px] font-extrabold text-ink">AI assistant conversations</h2>
          </div>
          <button
            onClick={() => {
              sound.playClick(soundEnabled);
              loadChatLog();
            }}
            disabled={chatLogStatus === "loading"}
            className="flex items-center gap-1.5 rounded-full border border-line bg-navy-900/60 px-3 py-1.5 text-[11.5px] font-bold text-muted hover:text-ink hover:border-mint transition disabled:opacity-50"
          >
            <RefreshCw size={12} className={chatLogStatus === "loading" ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
        <p className="mt-1 text-[12.5px] text-muted">
          What {patientName} has asked the MedBox voice assistant, and any actions it took.
        </p>

        <div className="mt-4">
          {chatLogStatus === "loading" && !chatLog && (
            <p className="text-[13.5px] text-muted">Loading conversation history…</p>
          )}
          {chatLogStatus === "error" && (
            <p className="text-[13.5px] text-muted">
              Couldn't reach the assistant log right now — this needs the MedBox backend running.
            </p>
          )}
          {chatLogStatus === "ready" && chatLog?.length === 0 && (
            <p className="text-[13.5px] text-muted">No assistant conversations yet.</p>
          )}
          {chatLog && chatLog.length > 0 && (
            <ul className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
              {chatLog.map((msg, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i, 10) * 0.03 }}
                  className={`rounded-xl border px-4 py-2.5 ${
                    msg.role === "assistant" ? "border-mint/25 bg-mint/[0.05]" : "border-line bg-navy-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-[10.5px] uppercase tracking-wide text-muted">
                      {msg.role === "assistant" ? "MedBox Assistant" : patientName}
                    </span>
                    <span className="font-mono text-[10.5px] text-muted opacity-70">
                      {formatChatTimestamp(msg.createdAt)}
                    </span>
                  </div>
                  <p className="mt-1 text-[13.5px] text-ink">{msg.content}</p>
                  {msg.actions?.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {msg.actions.map((action, j) => (
                        <span
                          key={j}
                          className="rounded-full bg-mint-dim/20 px-2.5 py-0.5 font-mono text-[10.5px] font-bold text-mint"
                        >
                          {describeAgentAction(action, medicines)}
                        </span>
                      ))}
                    </div>
                  )}
                </motion.li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

const toneClasses = {
  mint: "border-mint/30 bg-mint/[0.07] text-mint",
  lime: "border-lime/30 bg-lime/[0.07] text-lime",
  coral: "border-coral/30 bg-coral/[0.07] text-coral",
};

const toneColors = {
  mint: "var(--color-mint)",
  lime: "var(--color-lime)",
  coral: "var(--color-coral)",
};

function StatCard({ icon: Icon, label, value, suffix = "", tone, ring, ringColor }) {
  const animatedValue = useCountUp(value);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className={`rounded-2xl border p-5 ${toneClasses[tone]}`}
    >
      <div className="flex items-start justify-between">
        <Icon size={18} />
        {typeof ring === "number" && (
          <RadialStat value={ring} size={40} stroke={4} color={ringColor || toneColors[tone]} showValue={false} />
        )}
      </div>
      <p className="mt-3 text-[26px] font-extrabold text-ink">
        {Math.round(animatedValue)}
        <span className="text-[15px]">{suffix}</span>
      </p>
      <p className="text-[12.5px] font-bold text-muted">{label}</p>
    </motion.div>
  );
}
