"""Vitals tracking (blood pressure / glucose / pulse) — supports the
frontend's VitalsTracker component. Not in the FR table itself, but
part of the shipped app's data surface, so it gets a real backend
instead of staying zustand-only."""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import VitalCreate, VitalResponse

router = APIRouter(prefix="/api/vitals", tags=["Vitals Tracking"])


def _to_response(v: models.Vital) -> VitalResponse:
    return VitalResponse(id=v.id, date=v.date, bpSystolic=v.bp_systolic, bpDiastolic=v.bp_diastolic, glucose=v.glucose, pulse=v.pulse)


@router.get("", response_model=List[VitalResponse])
def get_vitals(db: Session = Depends(get_db)):
    vitals = db.query(models.Vital).order_by(models.Vital.created_at.asc()).all()
    return [_to_response(v) for v in vitals]


@router.post("", response_model=VitalResponse)
def add_vital(payload: VitalCreate, db: Session = Depends(get_db)):
    v = models.Vital(
        date=payload.date or datetime.now().strftime("%a"),
        bp_systolic=payload.bpSystolic,
        bp_diastolic=payload.bpDiastolic,
        glucose=payload.glucose,
        pulse=payload.pulse,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return _to_response(v)
