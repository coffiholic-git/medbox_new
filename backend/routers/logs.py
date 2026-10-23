"""FR8 — dose log records backing the caregiver adherence chart / streaks.
This is the endpoint src/utils/api.js's logDoseAPI calls."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import DoseLogCreate, DoseLogResponse

router = APIRouter(prefix="/api/logs", tags=["Dose Logs (FR8)"])


def _to_response(log: models.DoseLog) -> DoseLogResponse:
    return DoseLogResponse(id=log.id, dateKey=log.date_key, medId=log.med_id, status=log.status, loggedAt=log.logged_at.isoformat())


@router.get("", response_model=List[DoseLogResponse])
def get_logs(date_key: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.DoseLog)
    if date_key:
        q = q.filter(models.DoseLog.date_key == date_key)
    return [_to_response(l) for l in q.order_by(models.DoseLog.logged_at.desc()).all()]


@router.post("", response_model=DoseLogResponse)
def create_log(payload: DoseLogCreate, db: Session = Depends(get_db)):
    log = models.DoseLog(date_key=payload.dateKey, med_id=payload.medId, status=payload.status)
    db.add(log)
    db.commit()
    db.refresh(log)
    return _to_response(log)
