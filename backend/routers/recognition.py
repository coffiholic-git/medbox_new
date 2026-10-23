"""
6.1 Medicine Recognition, 6.2 OCR Extraction, 6.6 Confirmation Loop.
FR2, FR3, FR10.

The hard rule from 6.6 / Section 13: a scan NEVER writes to the
medicine library or a reminder by itself. `/scan` only ever returns a
pending, unsaved result. `/confirm` is the *only* place a Medicine row
can be created from a recognition — enforced here by construction
(only this function sets `confirmed_via_recognition_id`), not just by
convention.
"""
import base64
import binascii
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import (
    ConfirmRecognitionRequest,
    ConfirmRecognitionResponse,
    InteractionAdvisory,
    MedicineResponse,
    ScanRequest,
    ScanResult,
)
from backend.services import ocr_service
from backend.services.interaction_service import check_interactions
from backend.routers.medicines import _to_response

router = APIRouter(prefix="/api/recognition", tags=["Recognition (FR2/FR3), Confirmation Loop (FR10)"])
logger = logging.getLogger(__name__)


def _scan_contract_fields(result: ocr_service.RecognitionResult) -> dict:
    """Return only the clean fields the frontend should display."""
    date_confidence = round(float(result.date_confidence or 0.0) / 100.0, 3)
    fields = {
        "medicine_name": result.matched["name"] if result.matched else None,
        "mfg_date": (result.package_details or {}).get("manufacturing_date") or (result.package_details or {}).get("mfg_date"),
        "expiry_date": result.exp_date,
        "date_confidence": date_confidence,
        "ocr_text": result.ocr_text.split() if result.ocr_text else [],
        "matched_keyword": result.matched_keyword,
    }
    print(f"OCR stage 6 scan JSON fields: {fields!r}", flush=True)
    return fields


@router.post("/scan", response_model=ScanResult)
def scan_medicine_label(payload: ScanRequest, db: Session = Depends(get_db)):
    image_bytes = None
    if payload.image_base64:
        try:
            image_bytes = base64.b64decode(payload.image_base64)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="image_base64 could not be decoded.")

    result = ocr_service.run_recognition(
        image_bytes,
        file_name=payload.file_name or "",
        scan_mode=payload.scan_mode,
    )

    # 6.6 Step 2 — branch on the score. Below threshold: no name is
    # guessed at all, just an honest "not confident, please rescan."
    if result.confidence < ocr_service.CONFIDENCE_THRESHOLD or not result.matched:
        history = models.RecognitionHistory(
            ocr_text=result.ocr_text,
            detected_name=result.matched["name"] if result.matched else None,
            detected_strength=result.matched["strength"] if result.matched else None,
            detected_exp=result.exp_date,
            date_confidence=result.date_confidence,
            confidence=result.confidence,
            engine_agreement=result.engines_agree,
            status="low_confidence",
        )
        db.add(history)
        db.commit()
        return ScanResult(
            recognitionId=history.id,
            ocrTextExtracted=result.ocr_text,
            detectedName=None,
            detectedStrength=None,
            detectedForm=None,
            instructionsFound=None,
            confidence=result.confidence,
            status="low_confidence",
            spokenResponse=ocr_service.spoken_confirmation_prompt(result),
            **_scan_contract_fields(result),
        )

    entry = result.matched
    history = models.RecognitionHistory(
        ocr_text=result.ocr_text,
        detected_name=entry["name"],
        detected_strength=entry["strength"],
        detected_form=entry["form"],
        detected_exp=result.exp_date,
        date_confidence=result.date_confidence,
        instructions_found=entry["instructions"],
        confidence=result.confidence,
        engine_agreement=result.engines_agree,
        status="pending_confirmation",
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    return ScanResult(
        recognitionId=history.id,
        ocrTextExtracted=result.ocr_text,
        detectedName=entry["name"],
        detectedStrength=entry["strength"],
        detectedForm=entry["form"],
        instructionsFound=entry["instructions"],
        confidence=result.confidence,
        status="pending_confirmation",
        spokenResponse=ocr_service.spoken_confirmation_prompt(result),
        **_scan_contract_fields(result),
    )


@router.post("/confirm", response_model=ConfirmRecognitionResponse)
def confirm_recognition_result(payload: ConfirmRecognitionRequest, db: Session = Depends(get_db)):
    history = db.query(models.RecognitionHistory).filter(models.RecognitionHistory.id == payload.recognitionId).first()
    if not history:
        raise HTTPException(status_code=404, detail="Unknown recognitionId — nothing to confirm.")

    if history.status == "low_confidence":
        # 6.6 — a low-confidence read can never be confirmed into anything,
        # regardless of what the client sends. Only path forward is a rescan.
        raise HTTPException(
            status_code=400,
            detail="This recognition was below the confidence threshold and cannot be confirmed. Please rescan.",
        )

    if history.status == "confirmed":
        raise HTTPException(status_code=400, detail="This recognition was already confirmed.")

    if payload.userAction == "reject":
        history.status = "rejected"
        db.commit()
        return ConfirmRecognitionResponse(
            success=True,
            addedToLibrary=False,
            spokenResponse="Okay, I've discarded that result. You can scan again whenever you're ready.",
        )

    if payload.userAction not in ("confirm", "edit"):
        raise HTTPException(status_code=400, detail="userAction must be 'confirm', 'edit', or 'reject'.")

    final_name = (payload.finalName if payload.userAction == "edit" and payload.finalName else history.detected_name)
    final_strength = (
        payload.finalStrength if payload.userAction == "edit" and payload.finalStrength else history.detected_strength
    )
    if not final_name:
        raise HTTPException(status_code=400, detail="No medicine name to confirm.")

    final_exp = payload.expDate if payload.expDate is not None else history.detected_exp

    existing_names: List[str] = [m.name for m in db.query(models.Medicine).all()]
    advisory = check_interactions(final_name, existing_names)

    # The ONLY place in the codebase that sets confirmed_via_recognition_id —
    # this is FR10's gate enforced by construction, not just validated input.
    med = models.Medicine(
        name=final_name,
        strength=final_strength or "",
        form=history.detected_form or "Tablet",
        instructions=history.instructions_found or "Take with water",
        expiry=final_exp or "",
        stock=payload.stock,
        max_stock=payload.stock,
        confirmed_via_recognition_id=history.id,
    )
    db.add(med)
    history.status = "confirmed"
    db.commit()
    db.refresh(med)
    history.final_medicine_id = med.id
    db.commit()

    spoken = f"Confirmed. {final_name} {final_strength or ''} has been added to your medicine library.".replace("  ", " ")

    if advisory.hasConflict:
        spoken += f" One thing to note: {advisory.advisoryMessage}"

    reminder_note = ""
    if payload.createReminder:
        reminder = models.Reminder(
            med_id=med.id,
            med_name=med.name,
            dosage=med.strength,
            quantity="1 tablet",
            time=payload.reminderTime or "9:00 AM",
            frequency=payload.reminderFrequency or "daily",
            is_active=True,
        )
        db.add(reminder)
        db.commit()
        reminder_note = f" A daily reminder is set for {payload.reminderTime}."

    return ConfirmRecognitionResponse(
        success=True,
        addedToLibrary=True,
        spokenResponse=spoken + reminder_note,
        medicine=_to_response(med),
        advisory=advisory,
    )
