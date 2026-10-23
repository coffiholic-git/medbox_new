"""6.8 Caregiver Dashboard + FR12. Reuses the same underlying data as
the primary voice interface, gated behind a caregiver role (demo mode
allows this without a login — see backend/security.py)."""
import json
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import (
    AgentAction,
    AgentHistoryMessage,
    CaregiverAlertRequest,
    CaregiverAlertResponse,
    CaregiverDashboardResponse,
    ScheduleEditRequest,
)
from backend.security import CurrentUser, DEMO_USER, require_role
from backend.services.notifications import ws_manager

router = APIRouter(prefix="/api/caregiver", tags=["Caregiver Dashboard (FR12)"])


@router.get("/dashboard", response_model=CaregiverDashboardResponse)
def get_caregiver_dashboard(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("caregiver")),
):
    medicines = db.query(models.Medicine).all()
    active_count = len(medicines)

    today = datetime.now()
    window_start = today - timedelta(days=6)
    window_keys = {(window_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

    logs = db.query(models.DoseLog).filter(models.DoseLog.date_key.in_(window_keys)).all()
    taken = sum(1 for l in logs if l.status == "taken")
    adherence = round((taken / len(logs)) * 100, 1) if logs else 100.0

    # Streak — consecutive days (walking back from today) with zero "missed" logs.
    streak = 0
    for i in range(0, 60):
        key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day_logs = [l for l in logs if l.date_key == key] if i < 7 else db.query(models.DoseLog).filter(models.DoseLog.date_key == key).all()
        if not day_logs:
            break
        if any(l.status == "missed" for l in day_logs):
            break
        streak += 1

    missed = (
        db.query(models.DoseLog)
        .filter(models.DoseLog.status == "missed")
        .order_by(models.DoseLog.logged_at.desc())
        .limit(5)
        .all()
    )
    med_names = {m.id: m.name for m in medicines}
    recent_missed = [
        {"date": l.date_key, "medName": med_names.get(l.med_id, l.med_id), "reason": "Missed dose"} for l in missed
    ]

    return CaregiverDashboardResponse(
        patientName="Maya Lin",
        primaryCaregiver=current_user.display_name or "Caregiver",
        adherenceRate7d=adherence,
        streakDays=streak,
        activeMedicinesCount=active_count,
        recentMissedDoses=recent_missed,
    )


@router.get("/chat-log", response_model=List[AgentHistoryMessage])
def get_patient_chat_log(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("caregiver")),
):
    """Read-only view of the patient's AI-assistant conversation
    (agent_chat_logs, written by routers/agent.py's `_persist_turn`) for
    the caregiver audit trail mentioned in that router's docstring.

    This is single-patient demo scope, same as `get_caregiver_dashboard`
    above (which also queries every Medicine/DoseLog row with no
    per-patient filter): rather than a real multi-patient link table, we
    read the shared "demo-primary" user id that every unauthenticated
    primary-user request is stored under (see security.DEMO_USER and
    models.AgentChatLog's docstring). A production multi-patient
    deployment would instead filter by a caregiver->patient assignment.
    """
    rows = (
        db.query(models.AgentChatLog)
        .filter(models.AgentChatLog.user_id == DEMO_USER.uid)
        .order_by(models.AgentChatLog.created_at.desc(), models.AgentChatLog.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    rows.reverse()
    out = []
    for row in rows:
        actions = []
        if row.actions_json:
            try:
                actions = [AgentAction(**a) for a in json.loads(row.actions_json)]
            except (json.JSONDecodeError, TypeError):
                actions = []
        out.append(
            AgentHistoryMessage(
                role=row.role,
                content=row.content,
                actions=actions,
                createdAt=row.created_at.isoformat(),
            )
        )
    return out


@router.post("/edit-schedule")
def edit_patient_schedule(
    payload: ScheduleEditRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("caregiver")),
):
    med = db.query(models.Medicine).filter(models.Medicine.id == payload.medId).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found.")

    med.time = payload.newTime
    med.frequency = payload.newFrequency
    db.commit()

    for rem in db.query(models.Reminder).filter(models.Reminder.med_id == payload.medId).all():
        rem.time = payload.newTime
        rem.frequency = payload.newFrequency
    db.commit()

    return {
        "success": True,
        "message": f"{current_user.display_name or 'Caregiver'} updated schedule for {med.name} to {payload.newTime} ({payload.newFrequency}).",
        "updatedAt": datetime.now().isoformat(),
    }


@router.post("/send-alert", response_model=CaregiverAlertResponse)
async def send_caregiver_alert(payload: CaregiverAlertRequest, db: Session = Depends(get_db)):
    """Called by src/utils/api.js's sendCaregiverAlertAPI — a manual
    "notify my caregiver" action from the primary interface, distinct
    from the automatic missed-dose alerts the scheduler raises."""
    alert = models.CaregiverAlert(
        patient_name=payload.patientName,
        caregiver_name=payload.caregiverName,
        med_id=payload.medId,
        message=payload.message or f"{payload.patientName} would like to check in with {payload.caregiverName}.",
        kind="manual",
    )
    db.add(alert)
    db.commit()

    await ws_manager.broadcast(
        {"type": "CAREGIVER_ALERT", "message": alert.message, "patientName": alert.patient_name}
    )

    return CaregiverAlertResponse(success=True, status="dispatched", dispatchedAt=datetime.now().isoformat())
