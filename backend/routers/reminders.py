"""
6.4 Medication Reminders + FR7. Reminders are structured DB records;
delivery is push-over-WebSocket (backend/scheduler.py), not polling.
"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import ReminderAckRequest, ReminderCreate, ReminderResponse
from backend.services.notifications import ws_manager

router = APIRouter(prefix="/api/reminders", tags=["Reminders (FR7) & Realtime Push"])


def _to_response(rem: models.Reminder) -> ReminderResponse:
    return ReminderResponse(
        id=rem.id,
        medId=rem.med_id,
        medName=rem.med_name,
        dosage=rem.dosage,
        quantity=rem.quantity,
        time=rem.time,
        frequency=rem.frequency,
        isActive=rem.is_active,
    )


@router.get("", response_model=List[ReminderResponse])
def get_reminders(db: Session = Depends(get_db)):
    return [_to_response(r) for r in db.query(models.Reminder).all()]


@router.post("", response_model=ReminderResponse)
async def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)):
    # FR10's gate extends here: you can only set a reminder for a medicine
    # that's already confirmed into the library (manually or via /recognition/confirm).
    med = db.query(models.Medicine).filter(models.Medicine.id == payload.medId).first()
    if not med:
        raise HTTPException(
            status_code=400,
            detail="No confirmed medicine with that id — add or confirm the medicine first.",
        )

    rem = models.Reminder(
        med_id=payload.medId,
        med_name=payload.medName or med.name,
        dosage=payload.dosage or med.strength,
        quantity=payload.quantity,
        time=payload.time,
        frequency=payload.frequency,
        is_active=payload.isActive,
    )
    db.add(rem)
    db.commit()
    db.refresh(rem)

    await ws_manager.broadcast({"type": "REMINDER_CREATED", "reminder": _to_response(rem).model_dump()})
    return _to_response(rem)


@router.delete("/{reminder_id}")
async def delete_reminder(reminder_id: str, db: Session = Depends(get_db)):
    rem = db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    db.delete(rem)
    db.commit()
    await ws_manager.broadcast({"type": "REMINDER_DELETED", "reminderId": reminder_id})
    return {"status": "deleted", "id": reminder_id}


@router.post("/{reminder_id}/ack")
async def acknowledge_reminder(reminder_id: str, payload: ReminderAckRequest, db: Session = Depends(get_db)):
    """6.4 — clears the missed-dose follow-up timer once the user
    acknowledges (taken/snoozed) a reminder that just fired."""
    rem = db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found.")

    rem.acknowledged = True
    rem.missed_follow_up_sent = False
    db.commit()

    log = models.DoseLog(date_key=datetime.now().strftime("%Y-%m-%d"), med_id=rem.med_id, status=payload.status)
    db.add(log)
    db.commit()

    await ws_manager.broadcast({"type": "REMINDER_ACKNOWLEDGED", "reminderId": reminder_id, "status": payload.status})
    return {"status": "acknowledged", "id": reminder_id}


@router.websocket("/ws")
async def websocket_reminder_push(websocket: WebSocket):
    """Layer 6 — clients connect once and receive REMINDER_DUE /
    CAREGIVER_ALERT pushes instantly, instead of polling the API."""
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "CONNECTED", "message": "Real-time reminder channel connected."})
        while True:
            # Keep the connection alive; clients don't need to send anything.
            data = await websocket.receive_text()
            await websocket.send_json({"type": "PONG", "received": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
