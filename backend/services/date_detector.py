import re
from datetime import datetime
from typing import Any

from backend.services.text_normalizer import normalize_date_token, normalize_expiry_fragment, normalize_ocr_text

EXPIRY_KEYWORDS = [
    "EXP", "EXPIRY", "EXPIRES", "USE BY", "USE-BY", "BEST BEFORE", "BEST-BEFORE",
    "VALID UPTO", "VALID TILL", "EXP DATE", "EXPDT"
]

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_EXPIRY_LABEL = re.compile(
    r"\b(?:EXP(?:\s*\.?\s*(?:DATE|DT))?\.?|EXPIRY(?:\s*\.?\s*DATE)?|"
    r"EXPIRES|USE\s*[-.]?\s*BY|BEST\s*[-.]?\s*BEFORE|"
    r"VALID\s+(?:UPTO|TILL))\b",
    re.I,
)
_OTHER_DATE_LABEL = re.compile(
    r"\b(?:MFG|MANUFACTUR(?:E|ED|ING)|BATCH|LOT|PKD|PACKED|MRP)\b",
    re.I,
)


def _date_in_text(text: str) -> str | None:
    digit_or_ocr_digit = r"[0-9OQILSB]"
    patterns = [
        rf"\b{digit_or_ocr_digit}{{1,2}}\s*[./-]\s*{digit_or_ocr_digit}{{1,2}}\s*[./-]\s*{digit_or_ocr_digit}{{4}}\b",
        rf"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[\s./:-]*{digit_or_ocr_digit}{{2,4}}\b",
        rf"\b{digit_or_ocr_digit}{{1,2}}\s+{digit_or_ocr_digit}{{2,4}}\b",
        rf"\b{digit_or_ocr_digit}{{1,2}}\s*[./-]\s*{digit_or_ocr_digit}{{2,4}}\b",
        rf"\b{digit_or_ocr_digit}{{4}}[-/]\s*{digit_or_ocr_digit}{{1,2}}\b",
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _parse_month_year(normalize_date_token(match.group(0)))
            if parsed:
                return normalize_expiry_value(parsed)
            if index == 0:
                return None
    return None


def _looks_like_expiry_context(text: str) -> bool:
    norm = normalize_ocr_text(text or "")
    for keyword in EXPIRY_KEYWORDS:
        if keyword in norm:
            return True
    return False


def _parse_month_year(value: str):
    text = normalize_ocr_text(value or "")
    if not text:
        return None

    month_match = re.search(
        r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[ -]*(\d{2,4})\b",
        text,
    )
    if month_match:
        month_name, year = month_match.groups()
        if len(year) == 2:
            year = "20" + year if int(year) < 50 else "19" + year
        if not 1900 <= int(year) <= 2099:
            return None
        return f"{month_name} {year}"

    day_month_year = re.search(r"\b(\d{1,2})\s*[./\- ]\s*(\d{1,2})\s*[./\- ]\s*(\d{4})\b", text)
    if day_month_year:
        day, month, year = map(int, day_month_year.groups())
        try:
            datetime(year, month, day)
        except ValueError:
            return None
        month_name = next(name for name, number in MONTHS.items() if number == month)
        return f"{month_name} {year}"

    match = re.search(r"\b(\d{1,2})\s*[/\.\-\s]\s*(\d{2,4})\b", text)
    if match:
        month = int(match.group(1))
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year if int(year) < 50 else "19" + year
        if 1 <= month <= 12 and 1900 <= int(year) <= 2099:
            month_name = next(name for name, num in MONTHS.items() if num == month)
            return f"{month_name} {year}"

    match = re.search(r"\b(\d{4})\s*[-./\s]\s*(\d{1,2})\b", text)
    if match:
        year, month = match.group(1), match.group(2)
        month_num = int(month)
        if 1 <= month_num <= 12:
            month_name = next(name for name, num in MONTHS.items() if num == month_num)
            return f"{month_name} {year}"

    return None


def normalize_expiry_value(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""

    parsed = _parse_month_year(candidate)
    if parsed:
        return parsed.upper()

    normalized = normalize_expiry_fragment(candidate)
    if normalized and re.search(r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", normalized, re.I):
        return normalized.upper()

    return candidate.upper()


def detect_expiry(lines: list[str]) -> str | None:
    value, _ = detect_expiry_with_confidence(lines)
    return value


def _bbox_bounds(bbox: Any) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        if len(bbox) == 4 and all(hasattr(point, "__len__") and len(point) >= 2 for point in bbox):
            xs = [float(point[0]) for point in bbox]
            ys = [float(point[1]) for point in bbox]
            return min(xs), min(ys), max(xs), max(ys)
        if len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
            x1, y1, x2, y2 = map(float, bbox)
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _as_records(lines: list[Any]) -> list[dict]:
    records = []
    for index, item in enumerate(lines or []):
        text = getattr(item, "text", item if isinstance(item, str) else "")
        text = normalize_ocr_text(str(text or ""))
        if not text:
            continue
        confidence = getattr(item, "confidence", None)
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        record = {
            "text": text,
            "confidence": confidence,
            "bbox": _bbox_bounds(getattr(item, "bbox", None)),
            "angle": int(getattr(item, "angle", 0)),
            "index": index,
        }
        bounds = record["bbox"]
        record["center"] = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2) if bounds else None
        record["height"] = max(1.0, bounds[3] - bounds[1]) if bounds else 0.0
        records.append(record)
    grouped = {}
    for record in records:
        grouped.setdefault(record["angle"], []).append(record)
    ordered = []
    for group in grouped.values():
        if group and all(record["bbox"] is not None for record in group):
            group.sort(key=lambda record: (record["center"][1], record["center"][0]))
        ordered.extend(_coalesce_label_tokens(group))
    return ordered


def _coalesce_label_tokens(records: list[dict]) -> list[dict]:
    phrases = {
        ("USE", "BY"), ("BEST", "BEFORE"), ("VALID", "UPTO"),
        ("VALID", "TILL"), ("EXP", "DATE"), ("EXP", "DT"),
        ("EXPIRY", "DATE"),
    }
    consumed = set()
    merged = []
    for index, record in enumerate(records):
        if index in consumed:
            continue
        match = next(
            (
                size
                for size in (2,)
                if index + size <= len(records)
                and tuple(re.sub(r"[^A-Z]", "", item["text"]) for item in records[index:index + size]) in phrases
            ),
            None,
        )
        if match:
            group = records[index:index + match]
            bounds = [item["bbox"] for item in group if item["bbox"]]
            if len(bounds) == len(group):
                union = (
                    min(bound[0] for bound in bounds), min(bound[1] for bound in bounds),
                    max(bound[2] for bound in bounds), max(bound[3] for bound in bounds),
                )
                record = dict(record)
                record["bbox"] = union
                record["center"] = ((union[0] + union[2]) / 2, (union[1] + union[3]) / 2)
                record["height"] = max(1.0, union[3] - union[1])
            record = dict(record)
            record["text"] = normalize_ocr_text(" ".join(item["text"] for item in group))
            confidences = [item["confidence"] for item in group if item["confidence"] is not None]
            record["confidence"] = min(confidences) if confidences else None
            consumed.update(range(index + 1, index + match))
        merged.append(record)
    return merged


def _date_from_records(records: list[dict]) -> tuple[str | None, float]:
    labels = [record for record in records if _EXPIRY_LABEL.search(record["text"])]
    if not labels:
        return None, 0.0

    spatial = all(record["bbox"] is not None for record in records)
    for label in labels:
        label_match = _EXPIRY_LABEL.search(label["text"])
        suffix = label["text"][label_match.end():] if label_match else ""
        if _OTHER_DATE_LABEL.search(suffix):
            suffix = _OTHER_DATE_LABEL.split(suffix, maxsplit=1)[0]
        value = _date_in_text(suffix)
        if value:
            return value, _evidence_confidence([label])

        if spatial:
            nearby = _spatial_neighbors(label, records)
            token_windows = [nearby[start:start + size] for size in range(1, 5) for start in range(max(0, len(nearby) - size + 1))]
            token_windows.sort(key=lambda window: (sum(_distance(label, token) for token in window), len(window)))
        else:
            label_index = records.index(label)
            following = []
            for record in records[label_index + 1:label_index + 7]:
                if _OTHER_DATE_LABEL.search(record["text"]) or _EXPIRY_LABEL.search(record["text"]):
                    break
                following.append(record)
            token_windows = [following[start:start + size] for size in range(1, 5) for start in range(max(0, len(following) - size + 1))]

        for window in token_windows:
            if any(_OTHER_DATE_LABEL.search(record["text"]) for record in window):
                continue
            joined = " ".join([suffix, *(record["text"] for record in window)])
            value = _date_in_text(joined)
            if not value:
                continue
            if spatial and _closer_to_other_label(window, label, records):
                continue
            return value, _evidence_confidence([label, *window])

        # Same-box label and value, e.g. "EXP: NOV 2026".
        value = _date_in_text(label["text"])
        if value:
            return value, _evidence_confidence([label])

    return None, 0.0


def _distance(left: dict, right: dict) -> float:
    if not left["center"] or not right["center"]:
        return float("inf")
    return abs(left["center"][0] - right["center"][0]) + 1.5 * abs(left["center"][1] - right["center"][1])


def _spatial_neighbors(label: dict, records: list[dict]) -> list[dict]:
    x1, y1, x2, y2 = label["bbox"]
    height = max(label["height"], 8.0)
    label_cx, label_cy = label["center"]
    candidates = []
    for record in records:
        if record is label or _EXPIRY_LABEL.search(record["text"]) or _OTHER_DATE_LABEL.search(record["text"]):
            continue
        text_clean = record["text"].strip(".,:;()[]{}")
        if not text_clean:
            continue
        token_pat = (
            r"^(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|"
            r"JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|[0-9OQILSBGZ|./:-]+)$"
        )
        if not (_date_in_text(text_clean) or all(re.match(token_pat, part.strip(".,:;()[]{}"), re.I) for part in text_clean.split())):
            continue
        left, top, right, bottom = record["bbox"]
        cx, cy = record["center"]
        same_row_right = cx >= label_cx - height and abs(cy - label_cy) <= max(1.8 * height, 18)
        below_label = cy > label_cy and abs(cx - label_cx) <= max(8 * height, 100)
        if not (same_row_right or below_label):
            continue
        if right < x1 - height or left > x2 + max(10 * height, 150):
            continue
        if top > y2 + max(8 * height, 140):
            continue
        if _closer_to_other_label([record], label, records):
            continue
        candidates.append(record)

    candidates.sort(key=lambda record: (record["center"][1], record["center"][0]))
    return candidates


def _closer_to_other_label(window: list[dict], expiry_label: dict, records: list[dict]) -> bool:
    if not window:
        return False
    x_values = [record["center"][0] for record in window]
    y_values = [record["center"][1] for record in window]
    date_center = ((min(x_values) + max(x_values)) / 2, (min(y_values) + max(y_values)) / 2)
    expiry_center = expiry_label["center"]
    expiry_distance = abs(date_center[0] - expiry_center[0]) + 1.5 * abs(date_center[1] - expiry_center[1])
    for other in records:
        if not _OTHER_DATE_LABEL.search(other["text"]) or not other["center"]:
            continue
        other_distance = abs(date_center[0] - other["center"][0]) + 1.5 * abs(date_center[1] - other["center"][1])
        if other_distance < expiry_distance:
            return True
    return False


def _evidence_confidence(records: list[dict]) -> float:
    """Compute confidence from OCR engine scores of the matched records.

    Raw OCR confidence scores measure per-character recognition certainty and
    are often low (0.2–0.5) even when the text is read correctly.  We apply a
    floor so that a successfully matched + parsed date doesn't show up as
    "23% confidence" just because the OCR engine was uncertain about individual
    pixel-level strokes.
    """
    values = [record["confidence"] for record in records if record["confidence"] is not None]
    if not values:
        return 0.0
    raw = min(values) * 100.0  # use the weakest link
    # A date that passed regex parsing + month/year validation is structurally
    # correct.  Boost the raw OCR score so it reflects detection success, not
    # just pixel-level certainty.  Floor at 70 so users still see it as
    # "verified" rather than "could not read".
    boosted = max(70.0, raw)
    return round(min(boosted, 99.0), 1)


def _future_date_from_records(records: list[dict]) -> tuple[str | None, float]:
    """Fallback: find the most plausible future date in the OCR records when no
    expiry label keyword was detected at all.  Only used when the labeled path
    returns nothing — common when the "EXP" or "BEST BEFORE" text is embossed
    or foil-stamped and the OCR engine misses or fragments it.

    Only future dates are considered (past dates are MFG/batch/lot numbers).
    Confidence is intentionally scaled below 80% so the UI always prompts the
    user to verify before saving.
    """
    from datetime import date as _date
    today_year = _date.today().year
    today_month = _date.today().month

    candidates: list[tuple[str, float, int, int]] = []  # (value, conf, year, month)
    for record in records:
        text = record["text"]
        # Skip records that look like non-date label tokens (medicine name, etc.)
        if _OTHER_DATE_LABEL.search(text):
            continue
        value = _date_in_text(text)
        if not value:
            continue
        # Parse the detected value to check it's a plausible future date.
        parsed = _parse_month_year(value)
        if not parsed:
            continue
        # parsed is like "NOV 2026" — extract year/month
        m = re.match(r"([A-Z]{3})\s+(\d{4})", parsed)
        if not m:
            continue
        month_name, year_str = m.group(1), m.group(2)
        year = int(year_str)
        month = MONTHS.get(month_name, 0)
        if not month:
            continue
        # Accept only future dates (could be expiry, not MFG).
        if year < today_year or (year == today_year and month < today_month):
            continue
        # Year sanity: not unreasonably far in the future.
        if year > today_year + 20:
            continue
        raw_conf = record["confidence"] if record["confidence"] is not None else 0.70
        # Scale raw OCR confidence (0–1) to a 0–100 range, then apply a
        # soft floor for the unlabeled-fallback path.  The floor is lower than
        # the labeled path (70) because we didn't find an EXP keyword, so the
        # date is less certain to be the expiry rather than e.g. a batch date.
        # But don't hard-cap at 65 when OCR confidence is genuinely high.
        scaled = raw_conf * 100.0
        conf = round(max(55.0, min(75.0, scaled)), 1)
        candidates.append((normalize_expiry_value(parsed), conf, year, month))

    if not candidates:
        return None, 0.0

    # Prefer the nearest future date (most likely expiry, not a lot number).
    candidates.sort(key=lambda c: (c[2], c[3]))
    best = candidates[0]
    return best[0], best[1]


def detect_expiry_with_confidence(lines: list[Any]) -> tuple[str | None, float]:
    """Return normalized expiry and confidence from the label/date OCR evidence.

    Primary path: look for an EXP / EXPIRY / USE BY / BEST BEFORE keyword and
    find the date associated with it.  If no labeled expiry is found at all,
    fall back to any future-year date in the OCR text with capped (low)
    confidence so the user is always prompted to verify.
    """
    records = _as_records(lines)
    by_angle: dict[int, list[dict]] = {}
    for record in records:
        by_angle.setdefault(record["angle"], []).append(record)
    detections = [_date_from_records(group) for group in by_angle.values()]
    best = max(detections, key=lambda result: result[1], default=(None, 0.0))
    if best[0] is not None:
        return best
    # No labeled expiry found — try unlabeled future dates as a low-confidence
    # fallback so the user gets a pre-filled (but clearly unverified) date.
    return _future_date_from_records(records)

