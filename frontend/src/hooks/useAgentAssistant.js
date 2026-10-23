import { useCallback } from "react";
import { useStore } from "../store/useStore";
import { agentChatAPI } from "../utils/api";
import { sound } from "../utils/audio";
import { todayKey } from "../utils/time";

/**
 * Central place for "talk to the MedBox AI assistant" logic, shared by:
 *   - Home.jsx's big voice-orb command bar
 *   - components/AgentAssistant.jsx, the global chat drawer mounted in
 *     Layout.jsx so the assistant (voice AND typed text, with a visible
 *     transcript) is reachable from Scan, Schedule, Safety, and Library —
 *     not just the Home screen.
 *
 * Both call the same `sendMessage`, so the transcript in `agentHistory`
 * (zustand store) stays a single shared conversation no matter which UI
 * surface the person used to talk to it.
 */
export function useAgentAssistant() {
  const patientName = useStore((s) => s.patientName);
  const medicines = useStore((s) => s.medicines);
  const logs = useStore((s) => s.logs);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const agentHistory = useStore((s) => s.agentHistory);
  const agentBusy = useStore((s) => s.agentBusy);
  const setAgentBusy = useStore((s) => s.setAgentBusy);
  const appendAgentTurn = useStore((s) => s.appendAgentTurn);
  const logDose = useStore((s) => s.logDose);
  const snoozeDose = useStore((s) => s.snoozeDose);
  const refillStock = useStore((s) => s.refillStock);
  const addVitalLog = useStore((s) => s.addVitalLog);
  const addMedicine = useStore((s) => s.addMedicine);
  const pushToast = useStore((s) => s.pushToast);
  const caregivers = useStore((s) => s.caregivers);

  const lowStockMeds = medicines.filter((m) => (m.stock !== undefined ? m.stock <= 5 : false));

  const buildAgentContext = useCallback(() => {
    const todayLog = logs[todayKey()] || {};
    const withTimes = medicines.map((m) => ({ id: m.id, time: m.time }));
    return {
      patientName,
      nowIso: new Date().toISOString(),
      medicines: medicines.map((m) => ({
        id: m.id,
        name: m.name,
        strength: m.strength || "",
        form: m.form || "",
        frequency: m.frequency || "daily",
        time: m.time || "9:00 AM",
        instructions: m.instructions || "",
        stock: m.stock,
        maxStock: m.maxStock,
      })),
      nextDoseMedId: withTimes[0]?.id ?? null,
      lowStockMedIds: lowStockMeds.map((m) => m.id),
      todaysLog: todayLog,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientName, medicines, logs]);

  /** Runs whatever the agent asked for. Every branch reuses the exact same
   * store function a manual tap on the UI already calls (see
   * backend/routers/agent.py's docstring for why that matters). */
  const runAgentActions = useCallback(
    (actions = [], navigate) => {
      actions.forEach((action) => {
        if (action.type === "navigate" && action.target) {
          navigate?.(action.target);
        } else if (action.type === "mark_taken" && action.medId) {
          const med = medicines.find((m) => m.id === action.medId);
          logDose(action.medId, "taken");
          sound.playChime(soundEnabled);
          if (med) pushToast(`${med.name} marked as taken.`, "success");
        } else if (action.type === "snooze" && action.medId) {
          snoozeDose(action.medId, action.minutes || 15);
          sound.playClick(soundEnabled);
        } else if (action.type === "refill_medicine" && action.medId) {
          const med = medicines.find((m) => m.id === action.medId);
          refillStock(action.medId, action.amount || 30);
          sound.playChime(soundEnabled);
          if (med) pushToast(`${med.name} refilled by ${action.amount || 30}.`, "success");
        } else if (action.type === "log_vital" && action.vitals) {
          const v = action.vitals;
          addVitalLog({
            bpSystolic: v.bpSystolic ?? 0,
            bpDiastolic: v.bpDiastolic ?? 0,
            glucose: v.glucose ?? 0,
            pulse: v.pulse ?? 0,
          });
          sound.playChime(soundEnabled);
          pushToast("Vitals reading logged.", "success");
        } else if (action.type === "add_medicine" && action.medicine) {
          const m = action.medicine;
          const payload = {
            name: m.name,
            strength: m.strength || "500 mg",
            form: m.form || "Tablet",
            frequency: m.frequency || "daily",
            time: m.time || "9:00 AM",
            instructions: m.instructions || `${m.form || "Tablet"} · ${m.time || "9:00 AM"}`,
            stock: Number(m.stock) || 30,
            maxStock: Number(m.maxStock) || 30,
            expiry: m.expiry || "",
            color: "mint",
          };
          addMedicine(payload).then((advisory) => {
            sound.playChime(soundEnabled);
            if (advisory?.hasConflict) {
              pushToast(`${payload.name} added. ⚠️ Advisory: ${advisory.advisoryMessage}`, "error");
            } else {
              pushToast(`${payload.name} was added to your pill cabinet.`, "success");
            }
          });
        } else if (action.type === "call_caregiver") {
          sound.playChime(soundEnabled);
          const primary = caregivers?.[0];
          if (primary && primary.phone) {
            pushToast(`Calling ${primary.name}...`, "success");
            window.location.href = `tel:${primary.phone}`;
          } else {
            pushToast("Calling your primary caregiver now...", "success");
          }
        }
      });
    },
    [medicines, logDose, snoozeDose, refillStock, addVitalLog, addMedicine, pushToast, soundEnabled, caregivers]
  );

  /** Send one message to the assistant. `navigate` is react-router's
   * useNavigate() from the calling component (kept out of this hook since
   * it must come from a component under <Routes>). Returns the reply text
   * (or an error message) so the caller can decide whether to speak it. */
  const sendMessage = useCallback(
    async (transcript, navigate) => {
      if (!transcript?.trim()) return null;
      setAgentBusy(true);
      const result = await agentChatAPI(transcript, agentHistory, buildAgentContext());
      setAgentBusy(false);

      if (!result) {
        return "The AI assistant did not respond. Please try again.";
      }

      if (!result.error) {
        appendAgentTurn(transcript, result.reply);
        runAgentActions(result.actions, navigate);
        return result.reply;
      }

      // Offline / fallback parser for "add medicine" commands when backend/Groq is unavailable
      const addMatch = transcript.match(/(?:add|schedule|prescribe)\s+(?:medicine\s+|medication\s+|pill\s+)?([a-zA-Z0-9\s]+?)(?:\s+(\d+\s*(?:mg|ml|mcg|iu|g)))?(?:\s+(daily|weekly|as needed))?(?:\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?$/i);
      if (addMatch) {
        const rawName = addMatch[1].trim();
        const strength = addMatch[2]?.trim() || "500 mg";
        const frequency = (addMatch[3]?.toLowerCase() === "weekly" ? "weekly" : addMatch[3]?.toLowerCase() === "as needed" ? "asNeeded" : "daily");
        const time = addMatch[4]?.trim() || "9:00 AM";

        const payload = {
          name: rawName.charAt(0).toUpperCase() + rawName.slice(1),
          strength,
          form: "Tablet",
          frequency,
          time,
          instructions: `1 tablet · ${time}`,
          stock: 30,
          maxStock: 30,
          expiry: "",
          color: "mint",
        };

        addMedicine(payload).then((advisory) => {
          sound.playChime(soundEnabled);
          if (advisory?.hasConflict) {
            pushToast(`${payload.name} added. ⚠️ Advisory: ${advisory.advisoryMessage}`, "error");
          } else {
            pushToast(`${payload.name} was added to your pill cabinet.`, "success");
          }
        });

        const reply = `I've added ${payload.name} ${payload.strength} (${payload.frequency} at ${payload.time}) to your pill cabinet.`;
        appendAgentTurn(transcript, reply);
        return reply;
      }

      return result.reply;
    },
    [agentHistory, buildAgentContext, appendAgentTurn, runAgentActions, setAgentBusy, addMedicine, soundEnabled, pushToast]
  );

  return { agentHistory, agentBusy, sendMessage };
}
