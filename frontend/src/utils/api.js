/**
 * MedBox API utility — all calls to the FastAPI backend (http://localhost:8000).
 *
 * Convention:
 *  - Every function returns the parsed JSON on success, or `null` on any
 *    network / HTTP error. Callers are responsible for null-checking.
 *  - Auth token is stored in localStorage under "medbox_token" and is
 *    attached automatically via getAuthHeaders().
 *  - The Vite dev proxy forwards /api/* to http://localhost:8000 so we use
 *    a relative base URL — no CORS issues in dev.
 */

const API_BASE = "/api";
const TOKEN_KEY = "medbox_token";

// ── Token helpers ──────────────────────────────────────────────────────────────

export function saveToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** Returns Authorization header object, or empty object for demo/Google users. */
function getAuthHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── Generic fetch helpers ──────────────────────────────────────────────────────

async function get(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { ...getAuthHeaders() },
    });
    if (res.ok) return await res.json();
    console.warn(`GET ${path} → ${res.status}`);
  } catch (err) {
    console.warn(`GET ${path} network error:`, err.message);
  }
  return null;
}

async function post(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(body),
    });
    if (res.ok) return await res.json();
    // Parse error detail so callers can show specific messages
    let detail = "";
    try {
      const errBody = await res.json();
      // FastAPI returns { detail: "..." } or { detail: [{msg: "..."}] }
      if (typeof errBody.detail === "string") {
        detail = errBody.detail;
      } else if (Array.isArray(errBody.detail)) {
        detail = errBody.detail.map((e) => e.msg || JSON.stringify(e)).join("; ");
      } else {
        detail = JSON.stringify(errBody);
      }
    } catch {
      detail = await res.text().catch(() => "Unknown error");
    }
    console.warn(`POST ${path} → ${res.status}:`, detail);
    return { _error: true, _status: res.status, _detail: detail };
  } catch (err) {
    console.warn(`POST ${path} network error:`, err.message);
    return { _error: true, _status: 0, _detail: "Could not reach the server. Is the backend running?" };
  }
}

async function patch(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(body),
    });
    if (res.ok) return await res.json();
    console.warn(`PATCH ${path} → ${res.status}`);
  } catch (err) {
    console.warn(`PATCH ${path} network error:`, err.message);
  }
  return null;
}

async function del(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: { ...getAuthHeaders() },
    });
    if (res.ok) return await res.json();
    console.warn(`DELETE ${path} → ${res.status}`);
  } catch (err) {
    console.warn(`DELETE ${path} network error:`, err.message);
  }
  return null;
}

// ── Auth (FR14) ────────────────────────────────────────────────────────────────

/**
 * Register a new user.
 * @returns {access_token, uid, displayName, email, role} | null
 */
export async function registerAPI(name, email, password, role = "primary_user") {
  return post("/auth/register", { name, email, password, role });
}

/**
 * Log in an existing user.
 * @returns {access_token, uid, displayName, email, role} | null
 */
export async function loginAPI(email, password) {
  return post("/auth/login", { email, password });
}

/**
 * Exchange a completed Firebase Google sign-in for a MedBox JWT.
 * @param {{uid:string, email:string, displayName?:string, photoURL?:string}} googleProfile
 * @returns {access_token, uid, displayName, email, role} | {_error:true,...}
 */
export async function googleAuthAPI(googleProfile) {
  return post("/auth/google", {
    uid: googleProfile.uid,
    email: googleProfile.email,
    name: googleProfile.displayName || "",
    photoURL: googleProfile.photoURL || null,
  });
}

// ── Medicines (FR8) ────────────────────────────────────────────────────────────

export async function fetchMedicinesAPI() {
  return get("/medicines");
}

/**
 * @returns {medicine, advisory} | null
 */
export async function addMedicineAPI(medData) {
  return post("/medicines", medData);
}

export async function refillMedicineAPI(medId, amount) {
  return patch(`/medicines/${medId}/refill`, { amount });
}

export async function deleteMedicineAPI(medId) {
  return del(`/medicines/${medId}`);
}

// ── Dose Logs (FR8) ────────────────────────────────────────────────────────────

export async function fetchLogsAPI(dateKey) {
  const qs = dateKey ? `?date_key=${dateKey}` : "";
  return get(`/logs${qs}`);
}

export async function logDoseAPI(dateKey, medId, status) {
  return post("/logs", { dateKey, medId, status });
}

// ── Vitals ─────────────────────────────────────────────────────────────────────

export async function fetchVitalsAPI() {
  return get("/vitals");
}

export async function addVitalAPI(vitalData) {
  return post("/vitals", vitalData);
}

// ── Reminders (FR7) ────────────────────────────────────────────────────────────

export async function fetchRemindersAPI() {
  return get("/reminders");
}

export async function createReminderAPI(payload) {
  return post("/reminders", payload);
}

export async function deleteReminderAPI(reminderId) {
  return del(`/reminders/${reminderId}`);
}

// ── Recognition / OCR Scan (FR2/3/10) ─────────────────────────────────────────

/**
 * Send a base64-encoded image (or null for a simulated scan) to the backend.
 * @returns ScanResult | null
 */
export async function scanMedicineAPI(imageBase64 = null, fileName = "scan.jpg", scanMode = "both") {
  return post("/recognition/scan", {
    image_base64: imageBase64,
    file_name: fileName,
    scan_mode: scanMode,
  });
}

/**
 * Confirm (or reject) a pending recognition result.
 * @returns ConfirmRecognitionResponse | null
 */
export async function confirmRecognitionAPI({
  recognitionId,
  userAction = "confirm",
  finalName,
  finalStrength,
  expDate,
  createReminder = false,
  reminderTime = "9:00 AM",
  reminderFrequency = "daily",
  stock = 30,
}) {
  return post("/recognition/confirm", {
    recognitionId,
    userAction,
    finalName,
    finalStrength,
    expDate,
    createReminder,
    reminderTime,
    reminderFrequency,
    stock,
  });
}

// ── AI Conversational Agent ─────────────────────────────────────────────────────

/**
 * Talk to the MedBox AI voice assistant (backend/routers/agent.py).
 * Stateless on the server — pass the running transcript back every call.
 * @param {string} message - what the user just said/typed.
 * @param {{role:string, content:string}[]} history - prior turns, oldest first.
 * @param {object} context - AgentContext snapshot (see buildAgentContext in Home.jsx).
 * @returns {{reply:string, actions:object[], modelUsed?:string}} | null
 */
export async function agentChatAPI(message, history, context) {
  // Custom (not the generic post() helper) so a 503/502 from the backend
  // — e.g. ANTHROPIC_API_KEY not set — surfaces its `detail` message to
  // speak/display, instead of silently collapsing to null like other
  // API calls do.
  try {
    const res = await fetch(`${API_BASE}/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ message, history, context }),
    });
    const body = await res.json().catch(() => null);
    if (res.ok) return body;
    return { reply: body?.detail || "The AI assistant hit a problem. Please try again.", actions: [], error: true };
  } catch (err) {
    return {
      reply: "I couldn't reach the AI assistant. Check that the MedBox backend server is running.",
      actions: [],
      error: true,
    };
  }
}

/**
 * Fetch the signed-in user's persisted assistant transcript (see the new
 * agent_chat_logs table in backend/models.py). Used to restore the visible
 * chat on refresh/new device — the live /chat call itself still reasons
 * only over the `history` array the frontend sends, not this.
 * @returns {{role, content, actions, createdAt}[]} | null
 */
export async function fetchAgentHistoryAPI(limit = 50) {
  return get(`/agent/history?limit=${limit}`);
}

/** Clear the signed-in user's persisted assistant transcript. */
export async function clearAgentHistoryAPI() {
  return del("/agent/history");
}

// ── Caregiver (FR12) ───────────────────────────────────────────────────────────

export async function sendCaregiverAlertAPI(patientName, caregiverName) {
  return post("/caregiver/send-alert", { patientName, caregiverName });
}

/**
 * Read-only feed of the patient's AI-assistant conversation
 * (backend/routers/caregiver.py's /chat-log, backed by the agent_chat_logs
 * table). Returns the same shape as fetchAgentHistoryAPI: an array of
 * {role, content, actions, createdAt}, oldest first — or null on any
 * network/auth error, same convention as every other function here.
 */
export async function fetchCaregiverChatLogAPI(limit = 30) {
  return get(`/caregiver/chat-log?limit=${limit}`);
}
