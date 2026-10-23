import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from backend.perception.date_extractor import (
    MONTH_NAME_MAP,
    DateExtractionResult,
    extract_mfg_and_exp_dates,
)


@dataclass
class MedicineDetails:
    expiry_date: str | None = None
    manufacturing_date: str | None = None
    batch_number: str | None = None
    dosage: str | None = None
    date_confidence: float = 0.0
    date_needs_rescan: bool = False
    date_validation_errors: list[str] = field(default_factory=list)
    raw_date_result: Optional[dict] = None


def _format_fallback_date(raw_match: str) -> str:
    """Format and standardize fallback date string (converting textual months to MM/YYYY)."""
    raw = raw_match.strip()
    m = re.match(
        r"^(?:(0?[1-9]|[12]\d|3[01])\s*[/\-. ]\s*)?([A-Za-z]{3,9}|\d{1,2})\s*[/\-. ']?\s*(\d{2,4})$",
        raw,
    )
    if not m:
        return raw.replace(" ", "")

    d_str, mon_str, y_str = m.group(1), m.group(2), m.group(3)
    year = int(y_str)
    if year < 100:
        year = 2000 + year if year <= 50 else 1900 + year

    if mon_str.isalpha():
        month = MONTH_NAME_MAP.get(mon_str.lower()[:3]) or MONTH_NAME_MAP.get(mon_str.lower())
        if not month:
            return raw.replace(" ", "")
    else:
        month = int(mon_str)

    if d_str:
        return f"{int(d_str):02d}/{month:02d}/{year}"
    return f"{month:02d}/{year}"


def extract_expiry_date(text: str) -> str | None:
    if not text:
        return None

    # Use comprehensive date extractor first
    date_res = extract_mfg_and_exp_dates(text)
    if date_res.exp_date:
        return date_res.exp_date

    pattern = re.compile(
        r"""
        (?:EXP(?:IRY)?|EXP\s*DATE|EXP\.\s*DATE|EXP\s*DT|EXPIRY\s*DATE|USE\s*BEFORE|USE\s*BY|BEST\s*BEFORE|EXPIRES|VALID\s*UPTO|VALID\s*TILL|VAL\s*UPTO|E\.X\.P\.?)
        \s*[:.\-]?\s*
        (
            (?:(?:0?[1-9]|[12]\d|3[01])\s*[/\-. ]\s*)?
            (?:0?[1-9]|1[0-2]|[A-Za-z]{3,9})
            \s*[/\-.\s']\s*
            (?:\d{4}|\d{2})
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)
    if match:
        return _format_fallback_date(match.group(1))

    return None


def extract_manufacturing_date(text: str) -> str | None:
    if not text:
        return None
    return extract_mfg_and_exp_dates(text).mfg_date



def extract_batch_number(text: str) -> str | None:
    if not text:
        return None

    pattern = re.compile(
        r"""
        (?:
            BATCH
            (?:\s*NO)? |
            B\.?\s*NO |
            LOT
        )
        \s*[:#.\-]?\s*
        ([A-Z0-9][A-Z0-9\-/]{2,})
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)
    if match:
        return match.group(1)

    return None


def extract_dosage(text: str) -> str | None:
    if not text:
        return None

    pattern = re.compile(
        r"""
        \b
        \d+(?:\.\d+)?
        \s*
        (?:
            mg/ml
            |mg
            |mcg
            |ml
            |g
            |%
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)
    if match:
        return match.group(0).strip()

    return None


def extract_medicine_details(
    ocr_items: Union[list[Any], list[str], str],
) -> MedicineDetails:
    """
    Extract package-specific medicine information:
    - Manufacturing date (via date_extractor)
    - Expiry date (via date_extractor)
    - Date confidence score & rescan flag (< 80%)
    - Batch number
    - Dosage
    """
    if not ocr_items:
        return MedicineDetails()

    # Pass full OCR results (or strings) to modular date extraction engine
    date_result = extract_mfg_and_exp_dates(ocr_items)

    # Build combined text for regex extraction of dosage & batch number
    if isinstance(ocr_items, str):
        combined_text = ocr_items
    else:
        text_parts = []
        for item in ocr_items:
            if hasattr(item, "text"):
                text_parts.append(str(item.text or ""))
            elif isinstance(item, dict):
                text_parts.append(str(item.get("text", "") or ""))
            else:
                text_parts.append(str(item or ""))
        combined_text = " ".join(text_parts)

    batch_no = extract_batch_number(combined_text)
    dosage = extract_dosage(combined_text)

    # Fallback to direct text search if date_extractor didn't find dates
    mfg_date = date_result.mfg_date or extract_manufacturing_date(combined_text)
    exp_date = date_result.exp_date or extract_expiry_date(combined_text)

    return MedicineDetails(
        expiry_date=exp_date,
        manufacturing_date=mfg_date,
        batch_number=batch_no,
        dosage=dosage,
        date_confidence=date_result.overall_confidence,
        date_needs_rescan=date_result.needs_rescan,
        date_validation_errors=date_result.validation_errors,
        raw_date_result={
            "mfg_date": mfg_date,
            "exp_date": exp_date,
            "mfg_confidence": date_result.mfg_confidence,
            "exp_confidence": date_result.exp_confidence,
            "overall_confidence": date_result.overall_confidence,
            "is_valid": date_result.is_valid,
            "needs_rescan": date_result.needs_rescan,
            "validation_errors": date_result.validation_errors,
            "status": date_result.status,
            "mfg_bbox": date_result.mfg_bbox,
            "exp_bbox": date_result.exp_bbox,
            "matched_keyword": date_result.details.get("matched_keyword"),
        },
    )