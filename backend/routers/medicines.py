"""
6.5 Medicine Library + FR11 Interaction Advisory.

Manual add/edit/delete/refill of the user's medicine library. This is
NOT the camera-recognition path — a recognized medicine can only enter
the library via /api/recognition/confirm (FR10, enforced there). This
router covers direct entry (e.g. a caregiver typing a medicine in by
hand) and everyday management of medicines already on file.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import MedicineAddResponse, MedicineCreate, MedicineResponse, RefillRequest
from backend.services.interaction_service import check_interactions

router = APIRouter(prefix="/api/medicines", tags=["Medicine Library (FR8) & Interaction Advisory (FR11)"])


def _to_response(med: models.Medicine) -> MedicineResponse:
    return MedicineResponse(
        id=med.id,
        name=med.name,
        strength=med.strength,
        form=med.form,
        frequency=med.frequency,
        time=med.time,
        instructions=med.instructions,
        color=med.color,
        expiry=med.expiry,
        stock=med.stock,
        maxStock=med.max_stock,
        addedAt=med.added_at,
    )


@router.get("", response_model=List[MedicineResponse])
def get_all_medicines(db: Session = Depends(get_db)):
    """7.5 / 7.9 — canonical source the client's offline cache syncs from."""
    meds = db.query(models.Medicine).order_by(models.Medicine.added_at.desc()).all()
    return [_to_response(m) for m in meds]


@router.post("", response_model=MedicineAddResponse)
def add_medicine(payload: MedicineCreate, db: Session = Depends(get_db)):
    existing_names = [m.name for m in db.query(models.Medicine).all()]
    advisory = check_interactions(payload.name, existing_names)  # FR11 — advisory only, never blocking

    med = models.Medicine(
        name=payload.name,
        strength=payload.strength,
        form=payload.form,
        frequency=payload.frequency,
        time=payload.time,
        instructions=payload.instructions,
        color=payload.color,
        expiry=payload.expiry,
        stock=payload.stock,
        max_stock=payload.maxStock,
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    return MedicineAddResponse(medicine=_to_response(med), advisory=advisory)


@router.patch("/{med_id}/refill", response_model=MedicineResponse)
def refill_medicine(med_id: str, payload: RefillRequest, db: Session = Depends(get_db)):
    med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found.")
    med.stock = (med.stock or 0) + payload.amount
    med.max_stock = max(med.max_stock or 0, med.stock)
    db.commit()
    db.refresh(med)
    return _to_response(med)


@router.put("/{med_id}", response_model=MedicineResponse)
def update_medicine(med_id: str, payload: MedicineCreate, db: Session = Depends(get_db)):
    med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found.")
    med.name = payload.name
    med.strength = payload.strength
    med.form = payload.form
    med.frequency = payload.frequency
    med.time = payload.time
    med.instructions = payload.instructions
    med.color = payload.color
    med.expiry = payload.expiry
    med.stock = payload.stock
    med.max_stock = payload.maxStock
    db.commit()
    db.refresh(med)
    return _to_response(med)


@router.delete("/{med_id}")
def delete_medicine(med_id: str, db: Session = Depends(get_db)):
    med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found.")
    db.delete(med)
    db.commit()
    return {"status": "deleted", "id": med_id}
