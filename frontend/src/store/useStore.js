import { create } from "zustand";
import { persist } from "zustand/middleware";
import { initialMedicines } from "../data/seed";
import { todayKey } from "../utils/time";
import {
  logDoseAPI,
  refillMedicineAPI,
  addVitalAPI,
  addMedicineAPI,
  deleteMedicineAPI,
  fetchMedicinesAPI,
  fetchVitalsAPI,
  fetchLogsAPI,
  fetchAgentHistoryAPI,
  clearAgentHistoryAPI,
  saveToken,
  clearToken,
} from "../utils/api";
import { haptics } from "../utils/haptics";

let idCounter = 0;
const uid = (prefix) => `${prefix}-${Date.now()}-${idCounter++}`;

// Backfill a few days of adherence history so the caregiver dashboard and
// streak counters have something meaningful to show on first load.
function seedLogs() {
  const logs = {};
  for (let offset = 6; offset >= 1; offset--) {
    const d = new Date();
    d.setDate(d.getDate() - offset);
    const key = todayKey(d);
    logs[key] = {};
    initialMedicines.forEach((med) => {
      if (med.frequency === "weekly" && d.getDay() !== 0) return;
      // Mostly taken, with a couple of realistic misses.
      const missed = (offset === 4 && med.id === "m-amlodipine") || (offset === 2 && med.id === "m-paracetamol");
      logs[key][med.id] = missed ? "missed" : "taken";
    });
  }
  return logs;
}

function seedVitals() {
  const out = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    out.push({
      date: d.toLocaleDateString(undefined, { weekday: "short" }),
      bpSystolic: 120 + Math.floor(Math.sin(i) * 6),
      bpDiastolic: 80 + Math.floor(Math.cos(i) * 4),
      glucose: 95 + Math.floor(Math.sin(i * 2) * 8),
      pulse: 72 + Math.floor(Math.cos(i * 1.5) * 5),
    });
  }
  return out;
}

/**
 * Convert an array of DoseLog records from the backend into the nested
 * { [dateKey]: { [medId]: status } } shape that the frontend expects.
 */
function logsArrayToMap(logsArray) {
  if (!Array.isArray(logsArray)) return {};
  const map = {};
  logsArray.forEach(({ dateKey, medId, status }) => {
    if (!map[dateKey]) map[dateKey] = {};
    map[dateKey][medId] = status;
  });
  return map;
}

export const useStore = create(
  persist(
    (set, get) => ({
      patientName: "Maya",
      selectedPatient: "maya",
      activeTheme: "midnight", // midnight | emerald | light
      soundEnabled: true,
      hapticsEnabled: true,
      user: null, // Authenticated user profile or null
      token: null, // JWT access_token from FastAPI (null for demo/Google users)
      medicines: initialMedicines,
      logs: seedLogs(),
      snoozed: {}, // { medId: untilTimestamp }
      vitalsLogs: seedVitals(),
      caregiverMode: false,
      textSize: "base", // base | lg | xl
      highContrast: false,
      reduceMotion: false,
      toasts: [],
      backendConnected: false, // true once syncFromBackend() succeeds
      caregivers: [], // User-configurable caregivers list

      // ── AI Assistant (shared across Home's mic + the global AgentAssistant
      // drawer, so every screen shows the same running transcript) ──────────
      agentOpen: false,
      agentBusy: false,
      agentHistory: [], // [{ role: "user"|"assistant", content }]
      agentHydrated: false, // true once we've pulled persisted history once

      // ── Auth ────────────────────────────────────────────────────────────────

      /**
       * Call this after a successful login/register.
       * @param {object} userProfile - { uid, email, displayName, photoURL?, role?, provider? }
       * @param {string|null} token - JWT access_token (null for Google/demo users)
       */
      setUser: (userProfile, token = null) => {
        // Persist token to localStorage so getAuthHeaders() can read it on
        // the next page load before the zustand store is hydrated.
        saveToken(token);
        set({
          user: userProfile,
          token,
          patientName: userProfile?.displayName?.split(" ")[0] || "Maya",
        });
      },

      logoutUser: () => {
        clearToken();
        set({ user: null, token: null, backendConnected: false, agentHistory: [], agentHydrated: false, agentOpen: false });
      },

      // ── Backend Sync ────────────────────────────────────────────────────────

      /**
       * Fetch medicines, vitals, and dose-logs from the FastAPI backend and
       * replace the corresponding local state. Called automatically after a
       * real email/password login or register. Safe to call at any time —
       * falls back gracefully if the backend is unavailable.
       */
      syncFromBackend: async () => {
        const [medsRaw, vitalsRaw, logsRaw] = await Promise.all([
          fetchMedicinesAPI(),
          fetchVitalsAPI(),
          fetchLogsAPI(),
        ]);

        const updates = { backendConnected: false };

        if (Array.isArray(medsRaw) && medsRaw.length > 0) {
          // Map backend snake_case → frontend camelCase where needed.
          updates.medicines = medsRaw.map((m) => ({
            ...m,
            maxStock: m.maxStock ?? m.max_stock ?? 30,
            addedAt: m.addedAt ?? m.added_at ?? todayKey(),
          }));
          updates.backendConnected = true;
        } else if (Array.isArray(medsRaw)) {
          // Backend returned an empty array — mark connected but keep local
          // seeded medicines so the dashboard never appears blank.
          updates.backendConnected = true;
        }

        if (Array.isArray(vitalsRaw) && vitalsRaw.length > 0) {
          updates.vitalsLogs = vitalsRaw;
          updates.backendConnected = true;
        }

        if (Array.isArray(logsRaw) && logsRaw.length > 0) {
          const serverLogMap = logsArrayToMap(logsRaw);
          updates.logs = serverLogMap;
          updates.backendConnected = true;
        }

        set(updates);
      },

      // ── Settings ────────────────────────────────────────────────────────────

      setSelectedPatient: (patientId) => {
        const nameMap = { maya: "Maya", robert: "Robert", elena: "Elena" };
        set({ selectedPatient: patientId, patientName: nameMap[patientId] || "Maya" });
      },
      setTheme: (theme) => set({ activeTheme: theme }),
      toggleSound: () => set((state) => ({ soundEnabled: !state.soundEnabled })),
      toggleHaptics: () => set((state) => ({ hapticsEnabled: !state.hapticsEnabled })),

      // ── Medicines ───────────────────────────────────────────────────────────

      /**
       * Add a medicine locally AND to the backend.
       * If the backend returns a real ID we swap the local temp ID for the
       * permanent one, keeping everything in sync.
       */
      addMedicine: async (med) => {
        // Generate a temporary local ID immediately so the UI is responsive.
        const tempId = uid("m");
        const localMed = {
          id: tempId,
          addedAt: todayKey(),
          offline: true,
          stock: med.stock || 30,
          maxStock: med.maxStock || 30,
          ...med,
        };

        // Optimistic local insert.
        set((state) => ({ medicines: [localMed, ...state.medicines] }));

        // Best-effort backend sync.
        const result = await addMedicineAPI({
          name: med.name,
          strength: med.strength || "",
          form: med.form || "Tablet",
          frequency: med.frequency || "daily",
          time: med.time || "9:00 AM",
          instructions: med.instructions || "Take with water",
          color: med.color || "mint",
          expiry: med.expiry || "",
          stock: med.stock || 30,
          maxStock: med.maxStock || 30,
        });

        if (result?.medicine) {
          // Replace the temp-ID record with the backend-assigned one.
          const backendMed = {
            ...result.medicine,
            maxStock: result.medicine.maxStock ?? result.medicine.max_stock ?? 30,
          };
          set((state) => ({
            medicines: state.medicines.map((m) =>
              m.id === tempId ? { ...backendMed, offline: false } : m
            ),
          }));
          await get().syncFromBackend();
          return result.advisory; // Expose advisory (drug-interaction info) to caller
        }

        return null;
      },

      removeMedicine: async (id) => {
        // Optimistic local remove.
        set((state) => ({ medicines: state.medicines.filter((m) => m.id !== id) }));
        // Best-effort backend delete.
        const result = await deleteMedicineAPI(id);
        if (result) await get().syncFromBackend();
      },

      updateMedicine: (id, patch) =>
        set((state) => ({
          medicines: state.medicines.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),

      refillStock: async (medId, amount = 30) => {
        const result = await refillMedicineAPI(medId, amount);
        set((state) => ({
          medicines: state.medicines.map((m) =>
            m.id === medId ? { ...m, stock: (m.stock || 0) + amount, maxStock: Math.max(m.maxStock || 30, (m.stock || 0) + amount) } : m
          ),
        }));
        if (result) await get().syncFromBackend();
      },

      // ── Dose Management ─────────────────────────────────────────────────────

      snoozeDose: (medId, minutes = 15) =>
        set((state) => ({
          snoozed: {
            ...state.snoozed,
            [medId]: Date.now() + minutes * 60 * 1000,
          },
        })),

      clearSnooze: (medId) =>
        set((state) => {
          const next = { ...state.snoozed };
          delete next[medId];
          return { snoozed: next };
        }),

      logDose: async (medId, status = "taken", dateKey = todayKey()) => {
        const result = await logDoseAPI(dateKey, medId, status);
        set((state) => {
          const day = state.logs[dateKey] || {};
          const updatedMeds = state.medicines.map((m) =>
            m.id === medId && status === "taken" ? { ...m, stock: Math.max(0, (m.stock || 1) - 1) } : m
          );
          return {
            medicines: updatedMeds,
            logs: {
              ...state.logs,
              [dateKey]: {
                ...day,
                [medId]: status,
              },
            },
          };
        });
        if (result) await get().syncFromBackend();
      },

      // ── Vitals ──────────────────────────────────────────────────────────────

      addVitalLog: async (vital) => {
        const result = await addVitalAPI(vital);
        set((state) => ({
          vitalsLogs: [
            ...state.vitalsLogs.slice(1),
            {
              date: new Date().toLocaleDateString(undefined, { weekday: "short" }),
              ...vital,
            },
          ],
        }));
        if (result) await get().syncFromBackend();
      },

      // ── AI Assistant ────────────────────────────────────────────────────────

      openAgent: () => set({ agentOpen: true }),
      closeAgent: () => set({ agentOpen: false }),
      toggleAgent: () => set((state) => ({ agentOpen: !state.agentOpen })),
      setAgentBusy: (busy) => set({ agentBusy: busy }),

      /** Append a completed user/assistant turn, trimming to the last ~16
       * messages (8 turns) so requests to the backend stay small. */
      appendAgentTurn: (userText, assistantText) =>
        set((state) => ({
          agentHistory: [
            ...state.agentHistory,
            { role: "user", content: userText },
            { role: "assistant", content: assistantText },
          ].slice(-16),
        })),

      /** Pull the signed-in user's persisted transcript once (e.g. right
       * after login or on first drawer open) so a refresh/new device shows
       * the same conversation instead of starting blank. */
      hydrateAgentHistory: async () => {
        if (get().agentHydrated) return;
        const rows = await fetchAgentHistoryAPI();
        set({ agentHydrated: true });
        if (Array.isArray(rows) && rows.length) {
          set({ agentHistory: rows.map((r) => ({ role: r.role, content: r.content })).slice(-16) });
        }
      },

      clearAgentHistory: async () => {
        set({ agentHistory: [] });
        await clearAgentHistoryAPI();
      },

      // ── Caregivers ──────────────────────────────────────────────────────────
      addCaregiver: (caregiver) =>
        set((state) => ({
          caregivers: [
            ...(state.caregivers || []),
            { id: uid("cg"), ...caregiver },
          ],
        })),

      updateCaregiver: (id, patch) =>
        set((state) => ({
          caregivers: (state.caregivers || []).map((cg) =>
            cg.id === id ? { ...cg, ...patch } : cg
          ),
        })),

      removeCaregiver: (id) =>
        set((state) => ({
          caregivers: (state.caregivers || []).filter((cg) => cg.id !== id),
        })),

      // ── UI Preferences ──────────────────────────────────────────────────────

      toggleCaregiverMode: () => set((state) => ({ caregiverMode: !state.caregiverMode })),
      setTextSize: (size) => set({ textSize: size }),
      toggleHighContrast: () => set((state) => ({ highContrast: !state.highContrast })),
      toggleReduceMotion: () => set((state) => ({ reduceMotion: !state.reduceMotion })),

      // ── Toasts ──────────────────────────────────────────────────────────────
      // Deduped (no stacking the same message from a double-click/retry) and
      // capped so a burst of errors can't bury the whole screen. Also fires
      // a matching haptic pulse — a toast is easy to miss without looking at
      // the screen, so every one gets a tactile echo too.
      pushToast: (message, tone = "default") => {
        const pattern = tone === "success" ? "success" : tone === "error" ? "error" : "tap";
        haptics[pattern]?.(get().hapticsEnabled);
        set((state) => {
          const withoutDupes = state.toasts.filter((t) => t.message !== message);
          const next = [...withoutDupes, { id: uid("t"), message, tone }];
          return { toasts: next.slice(-3) };
        });
      },
      dismissToast: (id) =>
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

      // ── Derived helpers ─────────────────────────────────────────────────────

      adherenceForRange: (days) => {
        const { logs, medicines } = get();
        const out = [];
        for (let i = days - 1; i >= 0; i--) {
          const d = new Date();
          d.setDate(d.getDate() - i);
          const key = todayKey(d);
          const dayLogs = logs[key] || {};
          const scheduled = medicines.filter((m) => m.frequency !== "weekly" || d.getDay() === 0);
          const taken = scheduled.filter((m) => dayLogs[m.id] === "taken").length;
          out.push({
            date: key,
            label: d.toLocaleDateString(undefined, { weekday: "short" }),
            taken,
            scheduled: scheduled.length,
            rate: scheduled.length ? Math.round((taken / scheduled.length) * 100) : 100,
          });
        }
        return out;
      },
    }),
    {
      name: "medbox-storage",
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        patientName: state.patientName,
        selectedPatient: state.selectedPatient,
        activeTheme: state.activeTheme,
        soundEnabled: state.soundEnabled,
        hapticsEnabled: state.hapticsEnabled,
        medicines: state.medicines,
        logs: state.logs,
        snoozed: state.snoozed,
        vitalsLogs: state.vitalsLogs,
        caregiverMode: state.caregiverMode,
        textSize: state.textSize,
        highContrast: state.highContrast,
        reduceMotion: state.reduceMotion,
        caregivers: state.caregivers,
      }),
    }
  )
);
