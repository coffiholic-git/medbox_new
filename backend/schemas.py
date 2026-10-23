"""
Pydantic request/response schemas — the stable contract Section 15
says should be defined first so the frontend and AI/ML modules can
build against it independently.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------- Auth (FR14)
class RegisterRequest(BaseModel):
    name: str = Field(...)
    email: str = Field(...)
    password: str = Field(..., min_length=8, max_length=72)
    role: str = Field("primary_user")  # primary_user | caregiver


class GoogleAuthRequest(BaseModel):
    """Body sent after a successful client-side Firebase Google popup.

    The frontend has already completed the Google OAuth handshake via
    Firebase; this just finds-or-creates the matching MedBox user so we
    can hand back a normal backend JWT (the only kind of session App.jsx
    accepts). uid/photoURL are accepted for forward-compatibility but the
    lookup key is email, since that's what ties a Google identity to a
    possible existing email/password account.
    """

    uid: str = Field(...)
    email: str = Field(...)
    name: str = Field("")
    photoURL: Optional[str] = Field(None)


class LoginRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(..., min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    uid: str
    displayName: str
    email: str
    role: str


class UserProfileResponse(BaseModel):
    uid: str
    email: str
    displayName: str
    role: str


# ------------------------------------------------------------ Medicines (FR8)
class MedicineBase(BaseModel):
    name: str
    strength: str = ""
    form: str = "Tablet"
    frequency: str = "daily"
    time: str = "9:00 AM"
    instructions: str = "Take with water"
    color: str = "mint"
    expiry: str = ""
    stock: int = 30
    maxStock: int = 30


class MedicineCreate(MedicineBase):
    """Direct manual add (e.g. caregiver typing in a medicine by hand).

    NOT how a camera-recognized medicine gets in — that path is gated
    by FR10 and must go through /api/recognition/confirm instead.
    """


class MedicineResponse(MedicineBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    addedAt: Optional[str] = None


class InteractionAdvisory(BaseModel):
    """FR11 — advisory only, never a block or an auto-action (Section 13)."""

    hasConflict: bool
    severity: str  # None | Low | Moderate | High
    advisoryMessage: str


class MedicineAddResponse(BaseModel):
    medicine: MedicineResponse
    advisory: InteractionAdvisory


class RefillRequest(BaseModel):
    amount: int = Field(30)


# --------------------------------------------------------------- Dose logs
class DoseLogCreate(BaseModel):
    dateKey: str = Field(...)
    medId: str = Field(...)
    status: str = Field(...)  # taken | missed | snoozed


class DoseLogResponse(BaseModel):
    id: str
    dateKey: str
    medId: str
    status: str
    loggedAt: str


# ------------------------------------------------------------------- Vitals
class VitalCreate(BaseModel):
    date: Optional[str] = None
    bpSystolic: int = Field(...)
    bpDiastolic: int = Field(...)
    glucose: int = Field(...)
    pulse: int = Field(...)


class VitalResponse(BaseModel):
    id: str
    date: str
    bpSystolic: int
    bpDiastolic: int
    glucose: int
    pulse: int


# ------------------------------------------------------- Recognition (FR2/3/10)
class ScanRequest(BaseModel):
    """image_base64 is optional so /docs is usable without a real photo —
    the OCR service falls back to a labelled simulation for the demo when
    it's absent (see services/ocr_service.py)."""

    image_base64: Optional[str] = None
    file_name: Optional[str] = "medicine_box.jpg"
    scan_mode: str = Field("both", pattern="^(medicine|expiry|both)$")


class ScanResult(BaseModel):
    recognitionId: str
    ocrTextExtracted: str
    detectedName: Optional[str]
    detectedStrength: Optional[str]
    detectedForm: Optional[str]
    instructionsFound: Optional[str]
    confidence: float
    status: str  # pending_confirmation | low_confidence
    spokenResponse: str
    # New snake_case contract; legacy camelCase fields remain for the UI.
    medicine_name: Optional[str] = None
    mfg_date: Optional[str] = None
    expiry_date: Optional[str] = None
    date_confidence: Optional[float] = None
    ocr_text: List[str] = Field(default_factory=list)
    matched_keyword: Optional[str] = None


class ConfirmRecognitionRequest(BaseModel):
    recognitionId: str
    userAction: str  # confirm | edit | reject
    finalName: Optional[str] = None
    finalStrength: Optional[str] = None
    expDate: Optional[str] = None
    # If confirming for a reminder rather than a plain library add.
    createReminder: bool = False
    reminderTime: Optional[str] = "9:00 AM"
    reminderFrequency: Optional[str] = "daily"
    stock: int = Field(30, ge=0)



class ConfirmRecognitionResponse(BaseModel):
    success: bool
    addedToLibrary: bool
    spokenResponse: str
    medicine: Optional[MedicineResponse] = None
    advisory: Optional[InteractionAdvisory] = None


# -------------------------------------------------------------- Reminders (FR7)
class ReminderCreate(BaseModel):
    """medId must reference a medicine already confirmed into the
    library (see routers/reminders.py) — this is how FR10's
    confirmation gate extends to reminders without duplicating a
    separate confirmed=true flag for a step that's already gated
    upstream at medicine-creation time."""

    medId: str
    medName: str
    dosage: str = ""
    quantity: str = "1 tablet"
    time: str = "9:00 AM"
    frequency: str = "daily"
    isActive: bool = True


class ReminderResponse(BaseModel):
    id: str
    medId: str
    medName: str
    dosage: str
    quantity: str
    time: str
    frequency: str
    isActive: bool


class ReminderAckRequest(BaseModel):
    status: str = "taken"  # taken | snoozed | missed


# ------------------------------------------------------------- Caregiver (FR12)
class CaregiverDashboardResponse(BaseModel):
    patientName: str
    primaryCaregiver: str
    adherenceRate7d: float
    streakDays: int
    activeMedicinesCount: int
    recentMissedDoses: List[dict]


class ScheduleEditRequest(BaseModel):
    medId: str
    newTime: str = "9:00 AM"
    newFrequency: str = "daily"


class CaregiverAlertRequest(BaseModel):
    patientName: str = "Maya Lin"
    caregiverName: str = "Caregiver"
    medId: Optional[str] = None
    message: Optional[str] = None


class CaregiverAlertResponse(BaseModel):
    success: bool
    status: str
    dispatchedAt: str


# ---------------------------------------------------------------- AI Agent (conversational)

class AgentMessage(BaseModel):
    """One turn of prior conversation, sent back on every request since the
    backend is stateless — the frontend is the source of truth for history."""

    role: str  # "user" | "assistant"
    content: str


class AgentMedicineContext(BaseModel):
    """Slim view of a medicine, only what the assistant needs to reason
    about and speak — not the full MedicineResponse shape."""

    id: str
    name: str
    strength: str = ""
    form: str = ""
    frequency: str = "daily"
    time: str = "9:00 AM"
    instructions: str = ""
    stock: Optional[int] = None
    maxStock: Optional[int] = None


class AgentContext(BaseModel):
    """Snapshot of the user's current app state, supplied by the frontend
    on every call. The agent is stateless server-side (Section 9's data
    layer stays the single source of truth on the client for demo/local
    users who never sync to the backend DB — see store/useStore.js)."""

    patientName: str = "there"
    nowIso: Optional[str] = None
    medicines: List[AgentMedicineContext] = []
    nextDoseMedId: Optional[str] = None
    lowStockMedIds: List[str] = []
    todaysLog: dict = {}  # { medId: "taken" | "missed" | "snoozed" }


class AgentChatRequest(BaseModel):
    message: str
    history: List[AgentMessage] = []
    context: AgentContext


class AgentAction(BaseModel):
    """A side-effect the frontend should carry out after speaking the
    reply. The agent still never touches the database directly and never
    invents a write path of its own — every action here maps 1:1 onto a
    store function (store/useStore.js) that a manual tap in the UI already
    calls: navigate, logDose, snoozeDose, refillStock, addVitalLog. It
    still cannot add or delete a medicine (see routers/agent.py docstring
    for why that one stays out of scope)."""

    type: str  # "navigate" | "mark_taken" | "snooze" | "refill_medicine" | "log_vital" | "add_medicine" | "call_caregiver"
    target: Optional[str] = None      # for "navigate": one of the app routes
    medId: Optional[str] = None       # for "mark_taken" / "snooze" / "refill_medicine"
    minutes: Optional[int] = None     # for "snooze"
    amount: Optional[int] = None      # for "refill_medicine": pills added
    vitals: Optional[dict] = None     # for "log_vital": {bpSystolic, bpDiastolic, glucose, pulse}
    medicine: Optional[dict] = None   # for "add_medicine": {name, strength, form, frequency, time, instructions, stock, expiry}
    caregiverName: Optional[str] = None # for "call_caregiver"


class AgentChatResponse(BaseModel):
    reply: str
    actions: List[AgentAction] = []
    modelUsed: Optional[str] = None


class AgentHistoryMessage(BaseModel):
    role: str
    content: str
    actions: List[AgentAction] = []
    createdAt: str
