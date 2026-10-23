import cv2
import numpy as np
from functools import lru_cache
from difflib import SequenceMatcher
import re
import os
import sys

from backend.perception.ocr import PaddleOCREngine, TesseractOCREngine
from backend.services.date_detector import detect_expiry_with_confidence
from backend.services.medicine_matcher import choose_medicine_name
from backend.services.preprocessing import preprocess_for_ocr
from backend.services.text_normalizer import normalize_ocr_text
from backend.services.medicine_matcher import GENERIC_WORDS

_EXPIRY_LABEL_PATTERN = re.compile(
    r"\b(?:EXP(?:IRY|IRES)?(?:\s*\.?\s*(?:DATE|DT))?|EXPDT|"
    r"USE\s*[-.]?\s*BY|BEST\s*[-.]?\s*BEFORE)\b",
    re.I,
)


@lru_cache(maxsize=1)
def get_paddle_engine():
    if sys.platform == "win32":
        os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
    engine = PaddleOCREngine()
    print("OCR Engine: PaddleOCR", flush=True)
    return engine


@lru_cache(maxsize=1)
def get_tesseract_engine():
    return TesseractOCREngine()


def _score_ocr_quality(results):
    if not results:
        return 0.0
    return max(float(r.confidence) for r in results)


def _run_expiry_crop_retry(image: np.ndarray, results):
    labels = [
        result
        for result in (results or [])
        if _EXPIRY_LABEL_PATTERN.search(normalize_ocr_text(getattr(result, "text", "")))
        and getattr(result, "bbox", None)
    ]
    if not labels:
        return []

    prepared = preprocess_for_ocr(image)
    if prepared.ndim == 2:
        prepared = cv2.cvtColor(prepared, cv2.COLOR_GRAY2BGR)
    height, width = prepared.shape[:2]
    crop_results = []

    for label in labels:
        points = np.asarray(label.bbox, dtype=np.float32).reshape(-1, 2)
        x1, y1 = np.floor(points.min(axis=0)).astype(int)
        x2, y2 = np.ceil(points.max(axis=0)).astype(int)
        margin = 100
        left, top = max(0, x1 - margin), max(0, y1 - margin)
        right, bottom = min(width, x2 + margin), min(height, y2 + margin)
        if right <= left or bottom <= top:
            continue

        crop = prepared[top:bottom, left:right]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        thresholded = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )
        crop_image = cv2.cvtColor(thresholded, cv2.COLOR_GRAY2BGR)
        crop_image = cv2.resize(crop_image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        scale_x = crop_image.shape[1] / crop.shape[1]
        scale_y = crop_image.shape[0] / crop.shape[0]

        try:
            detections = get_paddle_engine().recognize(crop_image)
        except Exception:
            detections = get_tesseract_engine().recognize(crop_image)

        for detection in detections:
            bbox = np.asarray(detection.bbox, dtype=np.float32)
            if bbox.size == 8:
                mapped = bbox.reshape(-1, 2)
                mapped[:, 0] = mapped[:, 0] / scale_x + left
                mapped[:, 1] = mapped[:, 1] / scale_y + top
                detection.bbox = mapped.tolist()
            detection.angle = int(getattr(label, "angle", 0))
            crop_results.append(detection)

    return crop_results


def run_ocr_once(image: np.ndarray):
    try:
        engine = get_paddle_engine()
        processed = preprocess_for_ocr(image)
        if processed.ndim == 2:
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
        return engine.recognize(processed)
    except Exception:
        # Tesseract performs its own CLAHE and adaptive-threshold passes.
        # Feeding it the already-binarized image removes subtle embossed text.
        return get_tesseract_engine().recognize(image)


def run_ocr_with_rotation_fallback(image: np.ndarray):
    results = run_ocr_once(image)
    if not results:
        return []

    best_conf = _score_ocr_quality(results)
    expiry_date, date_confidence = detect_expiry_with_confidence(results)
    expiry_label_found = any(
        _EXPIRY_LABEL_PATTERN.search(normalize_ocr_text(getattr(result, "text", "")))
        for result in results
    )

    if expiry_label_found and not expiry_date:
        results = results + _run_expiry_crop_retry(image, results)
        expiry_date, date_confidence = detect_expiry_with_confidence(results)

    height, width = image.shape[:2]
    rotation_may_help = best_conf < 0.60 or not expiry_label_found

    if expiry_date and date_confidence >= 80.0:
        return results

    if not expiry_date and rotation_may_help:
        rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        rotated_results = run_ocr_once(rotated)
        if rotated_results:
            for result in rotated_results:
                result.angle = 90
            return results + rotated_results

    return results


def clean_ocr_results(lines):
    cleaned = []
    for entry in (lines or []):
        text = getattr(entry, "text", str(entry))
        if not text:
            continue
        normalized = normalize_ocr_text(text)
        if normalized and len(normalized) >= 2:
            cleaned.append(normalized)
    return cleaned


def _medicine_evidence_confidence(medicine_name: str | None, results) -> float:
    if not medicine_name:
        return 0.0
    target = re.sub(r"[^A-Z0-9]", "", medicine_name.upper())
    best = 0.0
    for result in results or []:
        text = re.sub(r"[^A-Z0-9]", "", normalize_ocr_text(getattr(result, "text", "")))
        if not text:
            continue
        similarity = 1.0 if target in text else SequenceMatcher(None, target, text).ratio()
        if similarity >= 0.60:
            best = max(best, float(getattr(result, "confidence", 0.0)) * similarity)
    return round(min(1.0, max(0.0, best)), 4)


def _name_with_strength_candidate(results) -> tuple[str, float]:
    ignored = GENERIC_WORDS | {
        "MFG", "MFD", "PKD", "EXP", "EXPIRY", "BATCH", "LOT", "MRP",
        "MICRO", "LABS", "LTD", "LIMITED", "PHARMA", "INDIA", "ADDRESS",
        "MANUFACTURER", "MANUFACTURED", "INCLUSIVE", "TAXES",
    }
    candidates = []
    for result in results or []:
        text = normalize_ocr_text(getattr(result, "text", ""))
        tokens = re.findall(r"[A-Z0-9]+", text)
        if any(token in ignored for token in tokens):
            continue
        if not any(any(char.isalpha() for char in token) for token in tokens):
            continue
        if not any(any(char.isdigit() for char in token) for token in tokens):
            continue
        name_tokens = [token for token in tokens if token not in ignored]
        if not name_tokens or any(len(token) < 3 and not any(char.isdigit() for char in token) for token in name_tokens):
            continue
        candidate = " ".join(name_tokens)
        confidence = float(getattr(result, "confidence", 0.0))
        candidates.append((candidate, confidence))
    return max(candidates, key=lambda item: item[1], default=("", 0.0))


def extract_clean_medicine_and_expiry(image: np.ndarray):
    raw_results = run_ocr_with_rotation_fallback(image)
    lines = clean_ocr_results(raw_results)
    medicine_name = choose_medicine_name(lines)
    medicine_confidence = _medicine_evidence_confidence(medicine_name, raw_results)
    candidate, candidate_confidence = _name_with_strength_candidate(raw_results)
    if candidate and candidate_confidence > medicine_confidence:
        medicine_name = candidate
        medicine_confidence = candidate_confidence
    if medicine_confidence == 0.0:
        medicine_name = ""
    expiry_date, date_confidence = detect_expiry_with_confidence(raw_results)
    confidence = medicine_confidence
    status = (
        "confirmed"
        if medicine_name and expiry_date and medicine_confidence >= 0.75 and date_confidence >= 80.0
        else "needs_confirmation"
    )
    return {
        "medicine_name": medicine_name,
        "expiry_date": expiry_date,
        "confidence": confidence,
        "medicine_confidence": medicine_confidence,
        "date_confidence": date_confidence,
        "date_needs_rescan": not expiry_date,  # only if no date found at all; low-conf with a date just needs user verification
        "status": status,
        "raw_ocr_results": [
            {
                "text": result.text,
                "confidence": float(result.confidence),
                "bbox": np.asarray(result.bbox).tolist() if result.bbox is not None else [],
                "angle": int(getattr(result, "angle", 0)),
            }
            for result in raw_results
        ],
    }


try:
    get_paddle_engine()
except Exception as exc:
    print(
        f"OCR Engine: PaddleOCR unavailable ({type(exc).__name__}); Tesseract fallback enabled.",
        flush=True,
    )
