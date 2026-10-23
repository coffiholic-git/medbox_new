"""
SQLAlchemy ORM models.

Schema follows Section 15 ("users, medicines, reminders,
recognition_history, caregiver_links") plus the two small tables
(dose_logs, vitals) the shipped frontend also needs, and an
alert_log table backing the caregiver "missed dose" alerts in 7.8.
"""
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

_id_counter = 0


def gen_id(prefix: str) -> str:
    global _id_counter
    _id_counter += 1
    return f"{prefix}-{time.time_ns():020d}-{_id_counter:06d}-{uuid.uuid4().hex[:6]}"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: gen_id("u"))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    # FR14 — primary_user (the blind/visually-impaired end user) or caregiver.
    role = Column(String, default="primary_user", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    medicines = relationship("Medicine", back_populates="owner", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="owner", cascade="all, delete-orphan")


class Medicine(Base):
    """A confirmed entry in the user's medicine library (7.5)."""

    __tablename__ = "medicines"

    id = Column(String, primary_key=True, default=lambda: gen_id("m"))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    name = Column(String, nullable=False)
    strength = Column(String, default="")
    form = Column(String, default="Tablet")
    frequency = Column(String, default="daily")
    time = Column(String, default="9:00 AM")
    instructions = Column(String, default="Take with water")
    color = Column(String, default="mint")
    expiry = Column(String, default="")
    stock = Column(Integer, default=30)
    max_stock = Column(Integer, default=30)
    added_at = Column(String, default=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # FR10 — a medicine can only ever be created through the confirmation
    # endpoint (see routers/recognition.py); this column exists so that
    # invariant is checkable, not just implied by which endpoint was hit.
    confirmed_via_recognition_id = Column(String, nullable=True)

    owner = relationship("User", back_populates="medicines")
    reminders = relationship("Reminder", back_populates="medicine", cascade="all, delete-orphan")
    dose_logs = relationship("DoseLog", back_populates="medicine", cascade="all, delete-orphan")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=lambda: gen_id("rem"))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    med_id = Column(String, ForeignKey("medicines.id"), nullable=False)

    med_name = Column(String, nullable=False)
    dosage = Column(String, default="")
    quantity = Column(String, default="1 tablet")
    time = Column(String, nullable=False, default="9:00 AM")
    frequency = Column(String, default="daily")
    is_active = Column(Boolean, default=True)

    # 7.4 missed-dose follow-up bookkeeping.
    last_fired_at = Column(DateTime, nullable=True)
    acknowledged = Column(Boolean, default=True)
    missed_follow_up_sent = Column(Boolean, default=False)

    owner = relationship("User", back_populates="reminders")
    medicine = relationship("Medicine", back_populates="reminders")


class RecognitionHistory(Base):
    """Every scan attempt, confirmed or not — 7.6's audit trail."""

    __tablename__ = "recognition_history"

    id = Column(String, primary_key=True, default=lambda: gen_id("rec"))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    ocr_text = Column(Text, nullable=True)
    detected_name = Column(String, nullable=True)
    detected_strength = Column(String, nullable=True)
    detected_form = Column(String, nullable=True)
    detected_exp = Column(String, nullable=True)
    date_confidence = Column(Float, default=0.0)
    instructions_found = Column(String, nullable=True)
    confidence = Column(Float, default=0.0)
    engine_agreement = Column(Boolean, default=False)

    # pending_confirmation | confirmed | rejected | low_confidence
    status = Column(String, default="pending_confirmation")
    final_medicine_id = Column(String, ForeignKey("medicines.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DoseLog(Base):
    __tablename__ = "dose_logs"

    id = Column(String, primary_key=True, default=lambda: gen_id("log"))
    date_key = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    med_id = Column(String, ForeignKey("medicines.id"), nullable=False)
    status = Column(String, nullable=False)  # taken | missed | snoozed
    logged_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    medicine = relationship("Medicine", back_populates="dose_logs")


class Vital(Base):
    __tablename__ = "vitals"

    id = Column(String, primary_key=True, default=lambda: gen_id("vit"))
    date = Column(String, nullable=False)
    bp_systolic = Column(Integer, nullable=False)
    bp_diastolic = Column(Integer, nullable=False)
    glucose = Column(Integer, nullable=False)
    pulse = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaregiverLink(Base):
    """Which caregiver accounts may see which primary user (7.8)."""

    __tablename__ = "caregiver_links"

    id = Column(String, primary_key=True, default=lambda: gen_id("link"))
    primary_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    caregiver_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentChatLog(Base):
    """Server-side durability for AI-assistant conversations.

    The agent endpoint (routers/agent.py) is still stateless *within a
    request* — the frontend keeps sending its own running transcript so a
    single call's reasoning never depends on this table being populated —
    but every turn is now also written here (best-effort) so a signed-in
    user's conversation survives a refresh, a new device, or a support/
    caregiver audit request. Demo/anonymous traffic (REQUIRE_AUTH=0, no
    token) is stored under the shared "demo-primary" user id like every
    other endpoint in this app.
    """

    __tablename__ = "agent_chat_logs"

    id = Column(String, primary_key=True, default=lambda: gen_id("chat"))
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    # JSON-encoded list of AgentAction dicts the assistant emitted this turn
    # (empty/None for user turns and assistant turns with no side effects).
    actions_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class CaregiverAlert(Base):
    """Missed-dose / manual alerts surfaced on the caregiver dashboard."""

    __tablename__ = "caregiver_alerts"

    id = Column(String, primary_key=True, default=lambda: gen_id("alert"))
    patient_name = Column(String, default="")
    caregiver_name = Column(String, default="")
    med_id = Column(String, nullable=True)
    message = Column(String, nullable=False)
    kind = Column(String, default="manual")  # manual | missed_dose
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
