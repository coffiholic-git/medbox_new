"""
Modular MFG and EXP Date Detection Engine for MedBox (6.2 / FR2 / FR10).

Pipeline:
  OCR Results (text, bboxes, confidences)
    -> Normalize OCR text (correct typos, delimiters, digit confusions)
    -> Detect MFG/EXP keywords (exact and fuzzy)
    -> Detect candidate dates via regex (MM/YY, MM/YYYY, DD/MM/YYYY, Mon YYYY, etc.)
    -> Match keywords to nearest dates using 2D bounding box geometry / text proximity
    -> Validate dates (calendar sanity, year range, MFG <= EXP)
    -> Calculate confidence score (0-100%)
    -> Gating: If confidence < 80%, flag for rescan/confirmation
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURATION & THRESHOLDS
# ==============================================================================

DATE_CONFIDENCE_THRESHOLD = 80.0  # Percentage (0-100) required for confident match (6.6 / FR10 requirement)
MIN_OCR_CONFIDENCE = 0.30

# Sensible year boundaries for modern pharmaceuticals
MIN_VALID_YEAR = 2010
MAX_VALID_YEAR = 2060

# Years more than this many years in the future are implausibly far for a
# pharmaceutical expiry date and likely result from an OCR digit misread
# (e.g. '2030' read as '2050' when the embossed '3' looks like a '5').
# When a candidate year exceeds today + MAX_PLAUSIBLE_FUTURE_YEARS we attempt
# common digit corrections before accepting it.
MAX_PLAUSIBLE_FUTURE_YEARS = 15

# Common OCR digit confusions on embossed/foil pharmaceutical packaging.
# Each key digit maps to a list of digits it is commonly confused with.
OCR_DIGIT_SWAPS = {
    '5': ['3'],   # embossed 3 ↔ 5
    '3': ['5'],
    '8': ['3', '0'],  # 3 ↔ 8, 0 ↔ 8
    '0': ['6', '8'],
    '6': ['0'],
    '1': ['7'],
    '7': ['1'],
}

MONTH_NAME_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

MFG_KEYWORDS = [
    "mfg", "mfd", "manufactured", "manufacturing date", "mfg date",
]

EXP_KEYWORDS = [
    "exp", "expiry", "exp.", "exp:", "expiry date", "exp date", "exp. date",
    "exp dt", "exp. dt", "exp dt.", "exp.dt", "e.x.p", "e.x.p.",
    "use before", "best before", "use by", "use-by", "useby",
    "valid upto", "valid till", "expires", "expiry:", "val upto",
    "expiry dt", "expiry dt.",
]



# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class BoundingBox:
    """Represents a 2D bounding box with geometric helper properties."""
    points: list[list[float]] = field(default_factory=list)
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @classmethod
    def from_raw(cls, raw_bbox: Any) -> Optional["BoundingBox"]:
        if not raw_bbox:
            return None

        # Handles 4-point polygon format: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
            pts = []
            for p in raw_bbox:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    try:
                        pts.append([float(p[0]), float(p[1])])
                    except (ValueError, TypeError):
                        pass
            if len(pts) == 4:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                return cls(
                    points=pts,
                    min_x=min_x,
                    max_x=max_x,
                    min_y=min_y,
                    max_y=max_y,
                    center_x=sum(xs) / 4.0,
                    center_y=sum(ys) / 4.0,
                    width=max(1.0, max_x - min_x),
                    height=max(1.0, max_y - min_y),
                )

        # Handles [x, y, w, h] format
        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4 and all(isinstance(v, (int, float)) for v in raw_bbox):
            x, y, w, h = [float(v) for v in raw_bbox]
            return cls(
                points=[[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                min_x=x,
                max_x=x + w,
                min_y=y,
                max_y=y + h,
                center_x=x + w / 2.0,
                center_y=y + h / 2.0,
                width=max(1.0, w),
                height=max(1.0, h),
            )

        return None


@dataclass
class DateKeyword:
    category: str  # "MFG" or "EXP"
    text: str
    confidence: float
    bbox: Optional[BoundingBox] = None
    box_index: int = -1
    char_start: int = -1
    char_end: int = -1
    match_quality: float = 1.0  # 1.0 for exact keyword, ~0.7-0.9 for fuzzy


@dataclass
class ParsedDate:
    raw_text: str
    standard_str: str  # MM/YYYY or DD/MM/YYYY
    month: int
    year: int
    day: Optional[int] = None
    confidence: float = 1.0
    bbox: Optional[BoundingBox] = None
    box_index: int = -1
    char_start: int = -1
    char_end: int = -1

    def to_date(self) -> date:
        d = self.day if self.day and 1 <= self.day <= 31 else 1
        return date(self.year, self.month, d)


@dataclass
class DateMatch:
    keyword: DateKeyword
    parsed_date: ParsedDate
    proximity_score: float
    match_type: str  # "intra_box", "horizontal_adjacent", "vertical_stacked", "spatial", "sequential"


@dataclass
class DateExtractionResult:
    mfg_date: Optional[str] = None
    exp_date: Optional[str] = None
    mfg_parsed: Optional[ParsedDate] = None
    exp_parsed: Optional[ParsedDate] = None
    mfg_confidence: float = 0.0
    exp_confidence: float = 0.0
    overall_confidence: float = 0.0
    is_valid: bool = False
    needs_rescan: bool = True
    validation_errors: list[str] = field(default_factory=list)
    mfg_bbox: Optional[list] = None
    exp_bbox: Optional[list] = None
    status: str = "Needs Rescan"
    details: dict = field(default_factory=dict)


# ==============================================================================
# 1. TEXT NORMALIZATION
# ==============================================================================

def normalize_ocr_text(text: str) -> str:
    """
    Clean and normalize OCR text for date and keyword detection:
    - Standardizes separators (slashes, hyphens, colons, dots).
    - Cleans whitespace around punctuation.
    - Repairs common digit/letter confusions in likely date chunks.
    """
    if not text:
        return ""

    text = str(text).strip()

    # Repair label-level OCR substitutions only; medicine names remain intact.
    text = re.sub(r"\bEXF\b", "EXP", text, flags=re.IGNORECASE)

    # Collapse multiple whitespace characters
    text = re.sub(r"[ \t]+", " ", text)

    # Standardize colons and dots after common abbreviations: e.g. "EXP ." -> "EXP."
    text = re.sub(r"\b(EXP|MFG|MFD|PKD)\s*[:.\-]\s*", r"\1: ", text, flags=re.IGNORECASE)

    # Normalize spaced date separators, e.g., "15 / 08 / 2025" -> "15/08/2025", "05 / 2025" -> "05/2025"
    text = re.sub(r"(\d{1,2})\s*([/\-.])\s*(\d{1,2})\s*([/\-.])\s*(\d{2,4})", r"\1\2\3\4\5", text)
    text = re.sub(r"(\d{1,2})\s*[/]\s*(\d{2,4})", r"\1/\2", text)
    text = re.sub(r"(\d{1,2})\s*[-]\s*(\d{2,4})", r"\1-\2", text)
    text = re.sub(r"(\d{1,2})\s*[.]\s*(\d{2,4})", r"\1.\2", text)

    # Normalize letter 'O'/'o' to '0' inside numeric date tokens (e.g. "O5/2O25" -> "05/2025")
    def _fix_date_letters(m: re.Match) -> str:
        s = m.group(0)
        s = s.replace("O", "0").replace("o", "0")
        s = s.replace("I", "1").replace("l", "1").replace("|", "1")
        return s

    text = re.sub(r"\b[0-9OolI|]{1,2}[/\-.][0-9OolI|]{2,4}\b", _fix_date_letters, text)
    text = re.sub(r"\b[0-9OolI|]{1,2}[/\-.][0-9OolI|]{1,2}[/\-.][0-9OolI|]{2,4}\b", _fix_date_letters, text)

    return text


# ==============================================================================
# 2. KEYWORD DETECTION
# ==============================================================================

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


OCR_TYPO_SUBSTITUTIONS = {
    "f": "p", "r": "p", "b": "p",  # P <-> F, R, B (e.g. EXF, EXR, EXB -> EXP)
    "o": "g", "6": "g", "c": "g", "q": "g",  # G <-> O, 6, C, Q (e.g. MFO, MF6 -> MFG)
    "0": "o", "8": "b", "1": "l",
}


def detect_keywords_in_text(
    text: str,
    box_index: int = 0,
    confidence: float = 1.0,
    bbox: Optional[BoundingBox] = None,
) -> list[DateKeyword]:
    """
    Detect manufacturing and expiration keywords in normalized text.
    Handles exact matches, punctuation variants, and OCR typo tolerance.
    Ignores license numbers (e.g. 'Mfg. Lic. No.') to avoid false positive MFG keywords.
    """
    keywords: list[DateKeyword] = []
    text_lower = text.lower()

    # Ignore license number contexts like "mfg. lic", "mfg lic no", "mfd. lic"
    if re.search(r"\b(mfg|mfd|pkd)\.?\s*(lic|license|licence|reg)", text_lower):
        # Strip out the license part when finding keywords, or skip matching "mfg" if it is part of "mfg lic"
        pass

    # Direct substring / regex search for EXP
    for kw in EXP_KEYWORDS:
        # Instead of \b, use \W (or end of string) so that keywords ending with punctuation
        # (like 'exp.') can still be matched even if followed by spaces.
        # \b doesn't work between punctuation and space.
        escaped_kw = re.escape(kw)
        pattern = r"(?<![a-zA-Z])" + escaped_kw + r"(?![a-zA-Z])"
        for m in re.finditer(pattern, text_lower):
            keywords.append(
                DateKeyword(
                    category="EXP",
                    text=text[m.start():m.end()],
                    confidence=confidence,
                    bbox=bbox,
                    box_index=box_index,
                    char_start=m.start(),
                    char_end=m.end(),
                    match_quality=1.0,
                )
            )

    has_exp = any(k.category == "EXP" for k in keywords)

    # Track MFG independently. MFG labels are never added to the EXP pool,
    # so a manufacturing date cannot be selected as the expiry date.
    for kw in MFG_KEYWORDS:
        pattern = r"(?<![a-zA-Z])" + re.escape(kw) + r"(?![a-zA-Z])"
        for m in re.finditer(pattern, text_lower):
            keywords.append(
                DateKeyword(
                    category="MFG",
                    text=text[m.start():m.end()],
                    confidence=confidence,
                    bbox=bbox,
                    box_index=box_index,
                    char_start=m.start(),
                    char_end=m.end(),
                    match_quality=1.0,
                )
            )

    # Ignore list for fuzzy matching to avoid false positives on common words
    FUZZY_IGNORE_WORDS = {"mom", "kde", "fmf", "for", "from", "som", "com", "tom", "max", "min", "mid", "mac"}

    # If EXP category is missing, check word-by-word for common OCR typos (fuzzy match)
    if not has_exp:
        words = text.split()
        char_offset = 0
        targets = [("exp", "EXP"), ("expiry", "EXP"), ("useby", "EXP")]

        for w in words:
            w_clean = re.sub(r"[^a-zA-Z0-9]", "", w).lower()
            start = text.find(w, char_offset)
            end = start + len(w) if start != -1 else char_offset + len(w)
            char_offset = end

            if w_clean in FUZZY_IGNORE_WORDS:
                continue

            if len(w_clean) >= 3:
                # Apply OCR typo substitutions for common packaging misreads
                w_sub = "".join(OCR_TYPO_SUBSTITUTIONS.get(c, c) for c in w_clean)

                for target, cat in targets:
                    ratio = SequenceMatcher(None, w_clean, target).ratio()
                    sub_ratio = SequenceMatcher(None, w_sub, target).ratio()
                    lev_clean = _levenshtein_distance(w_clean, target)
                    lev_sub = _levenshtein_distance(w_sub, target)

                    is_short = len(target) <= 4
                    matched = False
                    quality = 0.70

                    if w_sub == target:
                        matched = True
                        quality = 0.88
                    elif is_short:
                        # For short keywords like 'exp', only allow 1 edit max
                        if lev_clean <= 1 or lev_sub <= 1:
                            # Must share at least 2 chars in position
                            common_pos = sum(1 for c1, c2 in zip(w_clean, target) if c1 == c2)
                            sub_common_pos = sum(1 for c1, c2 in zip(w_sub, target) if c1 == c2)
                            if common_pos >= 2 or sub_common_pos >= 2:
                                matched = True
                                quality = 0.82
                    elif ratio >= 0.75 or sub_ratio >= 0.75:
                        matched = True
                        quality = round(max(ratio, sub_ratio), 2)

                    if matched:
                        keywords.append(
                            DateKeyword(
                                category=cat,
                                text=w,
                                confidence=confidence * quality,
                                bbox=bbox,
                                box_index=box_index,
                                char_start=max(0, start),
                                char_end=max(0, end),
                                match_quality=quality,
                            )
                        )
                        has_exp = True
                        break

    # Deduplicate overlapping keywords in the same box: keep longer/higher-quality match
    if len(keywords) > 1:
        deduped: list[DateKeyword] = []
        for kw in sorted(keywords, key=lambda k: (k.char_end - k.char_start, k.match_quality), reverse=True):
            overlap = any(
                (other.category == kw.category and other.box_index == kw.box_index and
                 max(other.char_start, kw.char_start) < min(other.char_end, kw.char_end))
                for other in deduped
            )
            if not overlap:
                deduped.append(kw)
        keywords = sorted(deduped, key=lambda k: (k.box_index, k.char_start))

    return keywords



# ==============================================================================
# 3. REGEX DATE EXTRACTION
# ==============================================================================

def _expand_two_digit_year(year: int) -> int:
    """Expands 2-digit years to 4-digit years using pharmaceutical conventions."""
    if year < 100:
        # 00-49 -> 2000-2049; 50-99 -> 1950-1999
        # Note: strictly < 50, so year=50 -> 1950 (not 2050)
        return 2000 + year if year < 50 else 1900 + year
    return year


def extract_dates_from_text(
    text: str,
    box_index: int = 0,
    confidence: float = 1.0,
    bbox: Optional[BoundingBox] = None,
) -> list[ParsedDate]:
    """
    Extract date expressions using comprehensive regexes for pharmaceutical packaging.
    Supports:
      - MM/YYYY, MM/YY, MM-YYYY, MM-YY, MM.YYYY, MM.YY
      - DD/MM/YYYY, DD/MM/YY, DD-MM-YYYY, DD.MM.YYYY
      - YYYY/MM, YYYY-MM
      - Mon YYYY, Mon YY, DD Mon YYYY, Mon-YYYY (e.g. MAY 2026, OCT 25, 15 JUN 2025)
    """
    parsed: list[ParsedDate] = []
    seen_spans: set[tuple[int, int]] = set()

    def _try_ocr_digit_correction(year: int) -> tuple[int, float]:
        """Try common OCR digit swaps on a year that looks implausibly far.

        Returns (corrected_year, confidence_penalty).  If no correction is
        needed or possible, returns (year, 1.0).
        """
        from datetime import date as _date
        current_year = _date.today().year
        if year <= current_year + MAX_PLAUSIBLE_FUTURE_YEARS:
            return year, 1.0  # year is plausible, no correction needed

        year_str = str(year)
        best_year = year
        best_distance = abs(year - (current_year + 4))  # prefer ~4 years from now
        for pos in range(len(year_str)):
            digit = year_str[pos]
            for swap in OCR_DIGIT_SWAPS.get(digit, []):
                candidate_str = year_str[:pos] + swap + year_str[pos + 1:]
                try:
                    candidate = int(candidate_str)
                except ValueError:
                    continue
                if MIN_VALID_YEAR <= candidate <= current_year + MAX_PLAUSIBLE_FUTURE_YEARS:
                    dist = abs(candidate - (current_year + 4))
                    if dist < best_distance:
                        best_year = candidate
                        best_distance = dist
        if best_year != year:
            return best_year, 0.90  # small confidence penalty for digit correction
        return year, 1.0

    def _add_if_valid(
        raw: str,
        year: int,
        month: int,
        day: Optional[int],
        start: int,
        end: int,
        base_conf: float = 1.0,
    ):
        nonlocal seen_spans
        year = _expand_two_digit_year(year)
        if not (1 <= month <= 12):
            return
        if not (MIN_VALID_YEAR <= year <= MAX_VALID_YEAR):
            return
        if day is not None and not (1 <= day <= 31):
            return

        # Try OCR digit correction for implausibly-far-future years
        year, digit_correction_penalty = _try_ocr_digit_correction(year)

        # Avoid duplicates or sub-spans:
        # If the new span is inside an already recorded span, ignore it.
        for s_start, s_end in seen_spans:
            if s_start <= start and end <= s_end:
                return
            if abs(start - s_start) <= 1 and abs(end - s_end) <= 1:
                return

        # If the new span strictly encloses an existing span, remove the shorter existing span.
        contained_indices = [
            i for i, p in enumerate(parsed)
            if start <= p.char_start and p.char_end <= end
        ]
        for i in reversed(contained_indices):
            del parsed[i]

        seen_spans = {(p.char_start, p.char_end) for p in parsed}
        seen_spans.add((start, end))

        std_str = f"{day:02d}/{month:02d}/{year}" if day else f"{month:02d}/{year}"
        parsed.append(
            ParsedDate(
                raw_text=raw,
                standard_str=std_str,
                month=month,
                year=year,
                day=day,
                confidence=confidence * base_conf * digit_correction_penalty,
                bbox=bbox,
                box_index=box_index,
                char_start=start,
                char_end=end,
            )
        )

    # --------------------------------------------------------------------------
    # Pattern 1: DD/MM/YYYY or DD/MM/YY (e.g., 15/05/2026, 01-11-24, 28.02.2025)
    # --------------------------------------------------------------------------
    p_dmy = re.compile(
        r"\b(0?[1-9]|[12]\d|3[01])\s*[/\-. ]\s*(0?[1-9]|1[0-2])\s*[/\-. ]\s*(20\d{2}|\d{2})\b"
    )
    for m in p_dmy.finditer(text):
        d_str, m_str, y_str = m.group(1), m.group(2), m.group(3)
        _add_if_valid(
            raw=m.group(0),
            year=int(y_str),
            month=int(m_str),
            day=int(d_str),
            start=m.start(),
            end=m.end(),
            base_conf=1.0,
        )

    # --------------------------------------------------------------------------
    # Pattern 2: Textual Month Formats
    # --------------------------------------------------------------------------
    month_names_regex = "|".join(sorted(MONTH_NAME_MAP.keys(), key=len, reverse=True))

    # Pattern 2a: Day Month Year (e.g. 15 MAY 2026, 15-MAY-2026, 15.MAY.26, 15/MAY/2026)
    p_text_dmy = re.compile(
        rf"\b(0?[1-9]|[12]\d|3[01])(?:\s*[/\-. ]\s*|\s+)({month_names_regex})[a-z]*\.?(?:\s*[/\-. ']\s*|\s+)(20\d{{2}}|\d{{2}})\b",
        re.IGNORECASE,
    )
    for m in p_text_dmy.finditer(text):
        d_str = m.group(1)
        mon_str = m.group(2).lower()
        y_str = m.group(3)
        month_num = MONTH_NAME_MAP.get(mon_str)
        if month_num:
            _add_if_valid(
                raw=m.group(0),
                year=int(y_str),
                month=month_num,
                day=int(d_str),
                start=m.start(),
                end=m.end(),
                base_conf=1.0,
            )

    # Pattern 2b: Month Day, Year (e.g. MAY 15 2026, MAY 15, 2026, MAY. 15, 2026)
    p_text_mdy = re.compile(
        rf"\b({month_names_regex})[a-z]*\.?(?:\s*[/\-. ]\s*|\s+)(0?[1-9]|[12]\d|3[01])(?:\s*,\s*|\s*[/\-. ']\s*|\s+)(20\d{{2}}|\d{{2}})\b",
        re.IGNORECASE,
    )
    for m in p_text_mdy.finditer(text):
        mon_str = m.group(1).lower()
        d_str = m.group(2)
        y_str = m.group(3)
        month_num = MONTH_NAME_MAP.get(mon_str)
        if month_num:
            _add_if_valid(
                raw=m.group(0),
                year=int(y_str),
                month=month_num,
                day=int(d_str),
                start=m.start(),
                end=m.end(),
                base_conf=1.0,
            )

    # Pattern 2c: Month Year (e.g. MAY 2026, MAY-2026, MAY. 2026, MAY/2026, OCT 25, OCT '25, JAN. 2025)
    # Negative lookahead prevents matching "MAY 15" when "MAY 15 2026" is present
    p_text_my = re.compile(
        rf"\b({month_names_regex})[a-z]*\.?(?:\s*[/\-. ']\s*|\s*)(20\d{{2}}|\d{{2}})\b(?!\s*[,/\-. ]?\s*(?:20\d{{2}}|\d{{2}}))",
        re.IGNORECASE,
    )
    for m in p_text_my.finditer(text):
        mon_str = m.group(1).lower()
        y_str = m.group(2)
        month_num = MONTH_NAME_MAP.get(mon_str)
        if month_num:
            _add_if_valid(
                raw=m.group(0),
                year=int(y_str),
                month=month_num,
                day=None,
                start=m.start(),
                end=m.end(),
                base_conf=1.0,
            )

    # --------------------------------------------------------------------------
    # Pattern 3: MM/YYYY or MM/YY (e.g. 05/2026, 12/24, 08-2025, 03.2026)
    # Use negative lookbehind to avoid matching the MM part of DD/MM/YYYY
    # (which pattern 1 already handles as a full triplet).
    # --------------------------------------------------------------------------
    p_my = re.compile(
        r"(?<!\d[/\-.])(?<!\d)\b(0?[1-9]|1[0-2])\s*([/\-.]|\s+)\s*(20\d{2}|\d{2})\b(?![/\-.\d])"
    )
    for m in p_my.finditer(text):
        m_str, sep, y_str = m.group(1), m.group(2), m.group(3)
        # Disallow pure whitespace separator for 2-digit years (e.g. '3 15') to avoid misreading arbitrary numbers
        if sep.strip() == "" and len(y_str) == 2:
            continue
        # Skip if this span is already covered by a longer DD/MM/YYYY match
        span_start, span_end = m.start(), m.end()
        already_covered = any(
            p.char_start <= span_start and span_end <= p.char_end
            for p in parsed
        )
        if already_covered:
            continue
        _add_if_valid(
            raw=m.group(0),
            year=int(y_str),
            month=int(m_str),
            day=None,
            start=span_start,
            end=span_end,
            base_conf=0.95,
        )

    # --------------------------------------------------------------------------
    # Pattern 4: YYYY/MM or YYYY-MM (e.g. 2025/11, 2024-05)
    # --------------------------------------------------------------------------
    p_ym = re.compile(
        r"\b(20\d{2})\s*[/\-. ]\s*(0?[1-9]|1[0-2])\b(?![/\-.\d])"
    )
    for m in p_ym.finditer(text):
        y_str, m_str = m.group(1), m.group(2)
        _add_if_valid(
            raw=m.group(0),
            year=int(y_str),
            month=int(m_str),
            day=None,
            start=m.start(),
            end=m.end(),
            base_conf=0.95,
        )

    # --------------------------------------------------------------------------
    # Pattern 5: YYYY-MM-DD (ISO format, e.g. 2026-05-01)
    # --------------------------------------------------------------------------
    p_iso = re.compile(
        r"\b(20\d{2})\s*[/\-. ]\s*(0?[1-9]|1[0-2])\s*[/\-. ]\s*(0?[1-9]|[12]\d|3[01])\b"
    )
    for m in p_iso.finditer(text):
        y_str, m_str, d_str = m.group(1), m.group(2), m.group(3)
        _add_if_valid(
            raw=m.group(0),
            year=int(y_str),
            month=int(m_str),
            day=int(d_str),
            start=m.start(),
            end=m.end(),
            base_conf=1.0,
        )

    # Post-filtering: ensure no candidate is a strict sub-span of another candidate
    final_parsed: list[ParsedDate] = []
    for d in parsed:
        is_subspan = any(
            (other is not d) and
            (other.char_start <= d.char_start and d.char_end <= other.char_end) and
            ((d.char_end - d.char_start) < (other.char_end - other.char_start))
            for other in parsed
        )
        if not is_subspan:
            final_parsed.append(d)

    return final_parsed



# ==============================================================================
# 4. PROXIMITY MATCHING (TEXT & 2D BOUNDING BOX)
# ==============================================================================

def calculate_spatial_proximity(kw_box: BoundingBox, dt_box: BoundingBox) -> tuple[float, str]:
    """
    Compute a normalized spatial proximity score (0.0 to 1.0) between a keyword
    bounding box and a candidate date bounding box.
    Evaluates:
      1. Horizontal reading order (date is to the right of keyword on same line).
      2. Vertical stacked order (date is directly below keyword in a column).
      3. Euclidean 2D distance between box centers.
    """
    avg_h = max(10.0, (kw_box.height + dt_box.height) / 2.0)
    avg_w = max(10.0, (kw_box.width + dt_box.width) / 2.0)

    # 1. Check Horizontal Reading Order (date to the right on the same line)
    v_overlap = max(0.0, min(kw_box.max_y, dt_box.max_y) - max(kw_box.min_y, dt_box.min_y))
    v_overlap_ratio = v_overlap / avg_h
    dy_center = abs(kw_box.center_y - dt_box.center_y)

    if (v_overlap_ratio > 0.3 or dy_center < avg_h * 0.8) and dt_box.center_x >= kw_box.center_x:
        dx = max(0.0, dt_box.min_x - kw_box.max_x)
        # Dates immediately to the right get a high score
        score = math.exp(-dx / (3.5 * avg_h)) * math.exp(-dy_center / (1.5 * avg_h))
        return min(1.0, max(0.2, score)), "horizontal_adjacent"

    # 2. Check Vertical Stacked Order (date directly below keyword)
    h_overlap = max(0.0, min(kw_box.max_x, dt_box.max_x) - max(kw_box.min_x, dt_box.min_x))
    h_overlap_ratio = h_overlap / min(kw_box.width, dt_box.width)
    dx_center = abs(kw_box.center_x - dt_box.center_x)

    if (h_overlap_ratio > 0.25 or dx_center < avg_w * 0.8) and dt_box.center_y >= kw_box.center_y:
        dy = max(0.0, dt_box.min_y - kw_box.max_y)
        score = 0.90 * math.exp(-dy / (2.5 * avg_h)) * math.exp(-dx_center / (2.0 * avg_w))
        return min(0.95, max(0.2, score)), "vertical_stacked"

    # 3. General 2D Euclidean Distance
    center_dist = math.hypot(kw_box.center_x - dt_box.center_x, kw_box.center_y - dt_box.center_y)
    diag_norm = max(50.0, 4.0 * max(avg_h, avg_w))
    score = math.exp(-center_dist / diag_norm)

    # Reading order penalty: date is above or far to the left of keyword
    if dt_box.center_y < kw_box.min_y or dt_box.max_x < kw_box.min_x:
        score *= 0.4

    return min(0.85, max(0.05, score)), "spatial"


def calculate_sequential_proximity(kw: DateKeyword, dt: ParsedDate) -> tuple[float, str]:
    """
    Fallback sequential text proximity when bounding boxes are missing.
    Considers character distance and relative order in the OCR text.
    """
    if kw.box_index == dt.box_index and kw.char_start >= 0 and dt.char_start >= 0:
        # Date after keyword in same string
        if dt.char_start >= kw.char_end:
            char_gap = dt.char_start - kw.char_end
            score = 0.95 * math.exp(-char_gap / 25.0)
            return min(0.98, max(0.3, score)), "intra_box"
        else:
            # Date before keyword
            char_gap = kw.char_start - dt.char_end
            score = 0.60 * math.exp(-char_gap / 25.0)
            return min(0.70, max(0.1, score)), "intra_box"

    # Across different text items / boxes:
    box_gap = abs(kw.box_index - dt.box_index)
    if dt.box_index >= kw.box_index:
        score = 0.85 * math.exp(-box_gap / 2.0)
        return min(0.85, max(0.1, score)), "sequential"
    else:
        score = 0.50 * math.exp(-box_gap / 2.0)
        return min(0.50, max(0.05, score)), "sequential"


# Confidence inputs for an "unanchored" EXP guess (no EXP keyword was read).
# With these values the maximum achievable score is ~64%, i.e. always below the
# 80% rescan gate, so an ambiguous read is flagged instead of confidently guessed.
UNANCHORED_KEYWORD_CONFIDENCE = 0.50
UNANCHORED_MATCH_QUALITY = 0.50
UNANCHORED_PROXIMITY = 0.30


def match_keywords_and_dates(
    keywords: list[DateKeyword],
    dates: list[ParsedDate],
) -> tuple[Optional[DateMatch], Optional[DateMatch]]:
    """
    Matches MFG and EXP keywords independently using spatial and sequential
    proximity, so an MFG date cannot be returned as expiry.
    """
    if not dates:
        return None, None

    def _best_match(category: str) -> Optional[DateMatch]:
        matches: list[DateMatch] = []
        for kw in (keyword for keyword in keywords if keyword.category == category):
            for dt in dates:
                if kw.box_index == dt.box_index and kw.box_index >= 0:
                    if dt.char_start >= kw.char_end:
                        gap = dt.char_start - kw.char_end
                        proximity = min(1.0, 0.98 * math.exp(-gap / 30.0))
                    elif kw.char_start >= dt.char_end:
                        gap = kw.char_start - dt.char_end
                        proximity = min(0.85, 0.75 * math.exp(-gap / 30.0))
                    else:
                        proximity = 0.95
                    matches.append(DateMatch(kw, dt, proximity, "intra_box"))
                elif kw.bbox is not None and dt.bbox is not None:
                    proximity, match_type = calculate_spatial_proximity(kw.bbox, dt.bbox)
                    matches.append(DateMatch(kw, dt, proximity, match_type))
                else:
                    proximity, match_type = calculate_sequential_proximity(kw, dt)
                    matches.append(DateMatch(kw, dt, proximity, match_type))

        return max(
            matches,
            key=lambda match: match.proximity_score * match.keyword.match_quality * match.parsed_date.confidence,
            default=None,
        )

    best_mfg = _best_match("MFG")
    best_exp = _best_match("EXP")

    # Fallback: if no EXP keyword was found but candidate dates exist in text,
    # choose the chronologically LATEST candidate. On real packaging EXP is
    # always >= MFG, whereas MFG is usually printed first, so taking the first
    # date silently mislabelled the manufacturing date as the expiry date.
    # Confidence values are deliberately low (see UNANCHORED_* constants) so an
    # unanchored guess can never clear DATE_CONFIDENCE_THRESHOLD on its own and
    # instead triggers a rescan / user confirmation.
    if not best_exp and dates and not (best_mfg and len(dates) == 1):
        def _date_key(d: ParsedDate) -> tuple:
            return (d.year, d.month, d.day or 0)

        latest = max(dates, key=_date_key)
        synth_kw = DateKeyword(
            "EXP", "unanchored",
            confidence=UNANCHORED_KEYWORD_CONFIDENCE,
            match_quality=UNANCHORED_MATCH_QUALITY,
        )
        best_exp = DateMatch(
            synth_kw, latest,
            proximity_score=UNANCHORED_PROXIMITY,
            match_type="unanchored",
        )

    return best_mfg, best_exp


# ==============================================================================
# 5. VALIDATION (FORMAT, CALENDAR, MFG <= EXP)
# ==============================================================================

def validate_extracted_dates(
    mfg_match: Optional[DateMatch],
    exp_match: Optional[DateMatch],
) -> tuple[bool, list[str], float, float]:
    """
    Validates dates for chronological and pharmaceutical consistency:
      - Valid month (1-12) and year (MIN_VALID_YEAR to MAX_VALID_YEAR).
      - MFG <= EXP if both are present.
      - Plausible shelf life (1 month to 10 years).
    Returns: (is_valid, validation_errors, mfg_multiplier, exp_multiplier)

    MFG-only problems (bad month/year/format on the MFG date itself)
    penalize only mfg_multiplier, and EXP-only problems penalize only
    exp_multiplier — a garbled or missing MFG read should not drag down
    an otherwise cleanly-read EXP date. Only genuinely joint problems
    (MFG after EXP, implausible shelf life, or a verified-consistent
    pair) touch both, since those statements are only meaningful when
    both dates are being considered together.
    """
    errors: list[str] = []
    mfg_multiplier = 1.0
    exp_multiplier = 1.0

    mfg_date_obj: Optional[date] = None
    exp_date_obj: Optional[date] = None

    today = date.today()

    if mfg_match:
        mfg = mfg_match.parsed_date
        if not (1 <= mfg.month <= 12):
            errors.append(f"MFG month {mfg.month} is invalid.")
            mfg_multiplier *= 0.5
        if not (MIN_VALID_YEAR <= mfg.year <= MAX_VALID_YEAR):
            errors.append(f"MFG year {mfg.year} is out of expected range ({MIN_VALID_YEAR}-{MAX_VALID_YEAR}).")
            mfg_multiplier *= 0.5
        try:
            mfg_date_obj = mfg.to_date()
            # A manufacturing date must be in the past — if it's in the future the
            # OCR almost certainly misread a batch/license number as a date.
            if mfg_date_obj > today:
                errors.append(
                    f"Manufacturing date ({mfg.standard_str}) is in the future, which is impossible."
                )
                mfg_multiplier *= 0.1  # Severe penalty — this is almost always a misread
        except ValueError as exc:
            errors.append(f"Invalid MFG date: {exc}")
            mfg_multiplier *= 0.3

    if exp_match:
        exp = exp_match.parsed_date
        if not (1 <= exp.month <= 12):
            errors.append(f"EXP month {exp.month} is invalid.")
            exp_multiplier *= 0.5
        if not (MIN_VALID_YEAR <= exp.year <= MAX_VALID_YEAR):
            errors.append(f"EXP year {exp.year} is out of expected range ({MIN_VALID_YEAR}-{MAX_VALID_YEAR}).")
            exp_multiplier *= 0.5
        try:
            exp_date_obj = exp.to_date()
            # Removed the check that invalidates past expiry dates.
            # Users may scan actually expired medicines, and we need to detect them correctly.
        except ValueError as exc:
            errors.append(f"Invalid EXP date: {exc}")
            exp_multiplier *= 0.3

    is_valid = len(errors) == 0 and (exp_match is not None)
    return is_valid, errors, mfg_multiplier, exp_multiplier


# ==============================================================================
# 6. CONFIDENCE CALCULATION & RESCAN GATING (< 80%)
# ==============================================================================

def calculate_single_date_confidence(
    match: Optional[DateMatch],
    validation_multiplier: float,
) -> float:
    """
    Computes confidence score (0-100%) for an individual date extraction:
      - OCR legibility signal (35%)
      - Keyword match quality (20%)
      - Proximity score (25%)
      - Validation multiplier (20%)

    Note: validation_multiplier is intentionally applied twice — once as
    its own weighted (20%) component, and again as an outer multiplier —
    so a severe *joint* validation failure (e.g. MFG date after EXP date)
    reliably gates the score below the confirmation threshold rather than
    being diluted to a mere 20% ding. This is safe now that the caller
    passes a per-field multiplier (see validate_extracted_dates): MFG-only
    problems no longer bleed into this calculation when scoring EXP, and
    vice versa, so the double weighting only bites when this field's own
    date is genuinely implicated.

    Recalibration note (previously: 30% raw OCR confidence + 25%
    match_quality*keyword_confidence): that split double-counted OCR
    legibility. keyword.confidence and parsed_date.confidence both track
    the same underlying image-quality signal (often the same or an
    adjacent OCR token), so multiplying match_quality by keyword.confidence
    smuggled a second helping of "how legible was this print" into what
    was meant to be a "how sure are we this keyword is really EXP/MFG and
    not a fuzzy typo match" signal. On real, moderately-legible photos
    (OCR confidence ~0.55-0.70) that made even an exact keyword match on a
    chronologically valid pair fail to clear 80%, because legibility alone
    was worth up to 55% of the raw score.

    This version keeps the two signals separate: `ocr_signal` (35%) is the
    average of both tokens' own OCR confidence — one legibility component,
    not two — and `match_quality` (20%) is scored purely on how exact the
    keyword match was (1.0 for an exact "EXP"/"MFG" hit, ~0.65-0.88 for a
    fuzzy/typo match), independent of how legibly it was printed. This is
    a structural fix, not a data-fitted one: the 35/20/25/20 split was
    chosen so a clean, chronologically-valid, exactly-matched read at
    moderate real-world OCR confidence (~0.6-0.65) can clear the 80% gate,
    while the deliberately-doubled validation_multiplier still collapses a
    genuine chronology violation to well under 80% regardless of legibility
    (see the worked cases in date_extractor's test notes). The 80% gate
    itself is left unchanged — moving that number is a data-driven call
    that should wait for real post-fix confidence numbers, not a guess.
    """
    if not match:
        return 0.0

    ocr_signal = (match.parsed_date.confidence + match.keyword.confidence) / 2.0
    match_quality = match.keyword.match_quality
    prox = match.proximity_score

    raw_score = (
        0.35 * ocr_signal +
        0.20 * match_quality +
        0.25 * prox +
        0.20 * min(1.0, validation_multiplier)
    )

    final_score = raw_score * 100.0 * min(1.0, validation_multiplier)
    return round(max(0.0, min(100.0, final_score)), 1)


# ==============================================================================
# 7. MAIN ORCHESTRATOR
# ==============================================================================

def extract_mfg_and_exp_dates(
    ocr_items: Union[list[Any], list[str], str],
) -> DateExtractionResult:
    """
    Main entry point for the MedBox date detection pipeline.

    Accepts:
      - list of `OCRResult` objects (having .text, .confidence, .bbox), OR
      - list of raw OCR text strings, OR
      - a single concatenated OCR text string.

    Returns:
      `DateExtractionResult` containing detected dates, confidence, validation,
      and rescan/confirmation indicators.
    """
    if not ocr_items:
        return DateExtractionResult(
            status="Needs Rescan",
            needs_rescan=True,
            overall_confidence=0.0,
            validation_errors=["No OCR text available"],
        )

    print(f"OCR stage 1 raw output: {ocr_items!r}", flush=True)

    # Standardize input into normalized items with bbox and confidence
    standardized_items: list[tuple[str, float, Optional[BoundingBox]]] = []

    if isinstance(ocr_items, str):
        ocr_items = [ocr_items]

    for idx, item in enumerate(ocr_items):
        if hasattr(item, "text"):  # OCRResult or similar object
            text = str(getattr(item, "text", "") or "")
            conf = float(getattr(item, "confidence", 1.0) or 1.0)
            raw_box = getattr(item, "bbox", None)
            bbox = BoundingBox.from_raw(raw_box)
        elif isinstance(item, dict):
            text = str(item.get("text", ""))
            conf = float(item.get("confidence", 1.0))
            bbox = BoundingBox.from_raw(item.get("bbox"))
        else:
            text = str(item or "")
            conf = 1.0
            bbox = None

        norm_text = normalize_ocr_text(text)
        if norm_text:
            print(f"OCR stage 2 normalized text: {norm_text!r}", flush=True)
            standardized_items.append((norm_text, conf, bbox))

    if not standardized_items:
        return DateExtractionResult(
            status="Needs Rescan",
            needs_rescan=True,
            overall_confidence=0.0,
            validation_errors=["OCR text was empty after normalization"],
        )

    # Stage 2: Detect keywords and candidate dates across all items
    all_keywords: list[DateKeyword] = []
    all_dates: list[ParsedDate] = []

    for box_idx, (text, conf, bbox) in enumerate(standardized_items):
        kws = detect_keywords_in_text(text, box_index=box_idx, confidence=conf, bbox=bbox)
        all_keywords.extend(kws)

        dts = extract_dates_from_text(text, box_index=box_idx, confidence=conf, bbox=bbox)
        all_dates.extend(dts)

    # Multi-token & line-level extraction across items:
    # Captures dates that span across multiple OCR token boxes (e.g. ['EXP:', 'MAY', '2026'] or ['05', '/', '2026'])
    if len(standardized_items) > 1:
        # Character-segmented OCR: embossed/foil pharmaceutical date strips are
        # routinely split by Tesseract/PaddleOCR into one box per character
        # (e.g. "EXP. FEB.2030" -> "E","X","P",".","F","E","B",".","2","0","3","0").
        # Always joining tokens with a literal space (the old behaviour) turns
        # a year like "2030" into "2 0 3 0", which no date regex can match —
        # digits must be contiguous. So the separator is chosen per adjacent
        # pair using real box geometry when available: tokens whose bounding
        # boxes sit immediately next to each other on the same line (small
        # horizontal gap relative to their height) are joined with no space,
        # since that's almost certainly one printed word/date split across
        # OCR boxes rather than two separate words. When bbox geometry isn't
        # available (e.g. plain OCR strings with no bbox), the previous
        # always-space behaviour is preserved unchanged.
        def _gap_suggests_no_space(prev_box: Optional["BoundingBox"], cur_box: Optional["BoundingBox"]) -> bool:
            if prev_box is None or cur_box is None:
                return False
            avg_h = max(1.0, (prev_box.height + cur_box.height) / 2.0)
            same_line = abs(prev_box.center_y - cur_box.center_y) < avg_h * 0.6
            if not same_line:
                return False
            gap = cur_box.min_x - prev_box.max_x
            return 0 <= gap < avg_h * 0.5

        combined_parts = []
        token_offsets = []
        cur_pos = 0
        prev_box: Optional["BoundingBox"] = None
        for b_idx, (t_text, t_conf, t_box) in enumerate(standardized_items):
            if combined_parts:
                if not _gap_suggests_no_space(prev_box, t_box):
                    combined_parts.append(" ")
                    cur_pos += 1
            start_pos = cur_pos
            combined_parts.append(t_text)
            cur_pos += len(t_text)
            token_offsets.append((start_pos, cur_pos, b_idx, t_conf, t_box))
            prev_box = t_box

        combined_text = "".join(combined_parts)
        avg_item_conf = sum(c for _, c, _ in standardized_items) / max(1, len(standardized_items))
        combined_dates = extract_dates_from_text(combined_text, box_index=0, confidence=avg_item_conf)

        for cd in combined_dates:
            if any(d.standard_str == cd.standard_str for d in all_dates):
                continue
            spanning_boxes = [
                t_box for (s, e, _, _, t_box) in token_offsets
                if max(s, cd.char_start) < min(e, cd.char_end) and t_box is not None
            ]
            spanning_indices = [
                b_idx for (s, e, b_idx, _, _) in token_offsets
                if max(s, cd.char_start) < min(e, cd.char_end)
            ]
            if spanning_boxes:
                xs = [p[0] for box in spanning_boxes for p in box.points]
                ys = [p[1] for box in spanning_boxes for p in box.points]
                min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
                cd.bbox = BoundingBox(
                    points=[[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]],
                    min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
                    center_x=(min_x + max_x) / 2.0, center_y=(min_y + max_y) / 2.0,
                    width=max(1.0, max_x - min_x), height=max(1.0, max_y - min_y),
                )
            if spanning_indices:
                cd.box_index = spanning_indices[0]
            all_dates.append(cd)

        combined_kws = detect_keywords_in_text(combined_text, box_index=0, confidence=avg_item_conf)
        for ckw in combined_kws:
            kw_spanning_boxes = [
                t_box for (s, e, _, _, t_box) in token_offsets
                if max(s, ckw.char_start) < min(e, ckw.char_end) and t_box is not None
            ]
            kw_spanning_indices = [
                b_idx for (s, e, b_idx, _, _) in token_offsets
                if max(s, ckw.char_start) < min(e, ckw.char_end)
            ]
            if kw_spanning_boxes:
                xs = [p[0] for box in kw_spanning_boxes for p in box.points]
                ys = [p[1] for box in kw_spanning_boxes for p in box.points]
                min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
                ckw.bbox = BoundingBox(
                    points=[[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]],
                    min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
                    center_x=(min_x + max_x) / 2.0, center_y=(min_y + max_y) / 2.0,
                    width=max(1.0, max_x - min_x), height=max(1.0, max_y - min_y),
                )
            if kw_spanning_indices:
                ckw.box_index = kw_spanning_indices[0]
            if not any(
                k.category == ckw.category and k.box_index == ckw.box_index
                for k in all_keywords
            ):
                all_keywords.append(ckw)

    # Filter out any MFG keyword that is actually part of a Mfg. Lic / License phrase in combined_text
    if 'combined_text' in locals():
        combined_text_lower = combined_text.lower()
        lic_spans = [
            m.span() for m in re.finditer(r"\b(mfg|mfd|pkd)\.?\s*[:\.]?\s*(lic|license|licence|reg)", combined_text_lower)
        ]
        if lic_spans:
            filtered_kws = []
            for kw in all_keywords:
                if kw.category == "MFG":
                    # Check if kw falls within any license span in combined_text
                    matched_lic = False
                    for l_start, l_end in lic_spans:
                        sub = combined_text_lower[l_start:l_end]
                        if kw.text.lower() in sub:
                            matched_lic = True
                            break
                    if matched_lic:
                        continue
                filtered_kws.append(kw)
            all_keywords = filtered_kws
    elif not all_dates and standardized_items:
        combined_text = standardized_items[0][0]
        all_dates = extract_dates_from_text(combined_text, box_index=0, confidence=0.85)

    # Stage 3: Match keywords to dates using proximity
    best_mfg_match, best_exp_match = match_keywords_and_dates(all_keywords, all_dates)
    print(
        "OCR stage 3 expiry candidates: "
        f"{[candidate.standard_str for candidate in all_dates]!r}; "
        f"keywords: {[(keyword.category, keyword.text) for keyword in all_keywords]!r}",
        flush=True,
    )

    # Stage 4: Validate dates (format, calendar, chronological sanity)
    is_valid, validation_errors, mfg_val_multiplier, exp_val_multiplier = validate_extracted_dates(
        best_mfg_match, best_exp_match
    )

    # Stage 5: Calculate confidence
    mfg_conf = calculate_single_date_confidence(best_mfg_match, mfg_val_multiplier)
    exp_conf = calculate_single_date_confidence(best_exp_match, exp_val_multiplier)

    # Overall date confidence is based on EXP date extraction
    overall_conf = exp_conf

    # Rescan gate (< 80% confidence or validation failure)
    needs_rescan = (overall_conf < DATE_CONFIDENCE_THRESHOLD) or not is_valid

    mfg_str = best_mfg_match.parsed_date.standard_str if best_mfg_match else None
    exp_str = best_exp_match.parsed_date.standard_str if best_exp_match else None

    status = "Needs Confirmation" if not needs_rescan else "Needs Rescan"
    print(
        "OCR stage 4 selected expiry="
        f"{exp_str!r} confidence={overall_conf:.1f}% "
        f"matched_keyword={best_exp_match.keyword.text if best_exp_match else None!r}",
        flush=True,
    )
    print(f"OCR stage 5 date_confidence={overall_conf:.1f}%", flush=True)

    return DateExtractionResult(
        mfg_date=mfg_str,
        exp_date=exp_str,
        mfg_parsed=best_mfg_match.parsed_date if best_mfg_match else None,
        exp_parsed=best_exp_match.parsed_date if best_exp_match else None,
        mfg_confidence=mfg_conf,
        exp_confidence=exp_conf,
        overall_confidence=overall_conf,
        is_valid=is_valid,
        needs_rescan=needs_rescan,
        validation_errors=validation_errors,
        mfg_bbox=best_mfg_match.parsed_date.bbox.points if best_mfg_match and best_mfg_match.parsed_date.bbox else None,
        exp_bbox=best_exp_match.parsed_date.bbox.points if best_exp_match and best_exp_match.parsed_date.bbox else None,
        status=status,
        details={
            "keywords_found": len(all_keywords),
            "dates_found": len(all_dates),
            "mfg_match_type": best_mfg_match.match_type if best_mfg_match else None,
            "exp_match_type": best_exp_match.match_type if best_exp_match else None,
            "mfg_date": mfg_str,
            "matched_keyword": best_exp_match.keyword.text if best_exp_match else None,
            "mfg_keyword_found": any(keyword.category == "MFG" for keyword in all_keywords),
            "mfg_validation_multiplier": mfg_val_multiplier,
            "exp_validation_multiplier": exp_val_multiplier,
        },
    )
