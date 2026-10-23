import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


# 6.1 / 6.2: OCR text is "fuzzy-matched against the medicine
# database" and structured fields are pulled out for each match.
#
# This used to be a single hardcoded entry ("paracetamol"), so the
# matcher could never recognize anything else — a fresh scan of any
# other real medicine would always fall through to "no match" no
# matter how good the OCR was. It now loads the shared reference
# dataset directly from backend/data/medicine_reference.json — the
# same file the rest of the backend (medicines/interaction routers)
# already reads — so the matcher covers the full medicine library
# and there is exactly one copy of the reference data on disk, with
# the single-entry dict kept only as a last-resort fallback so the
# module still degrades gracefully if the data file is missing.
_REFERENCE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "medicine_reference.json"
)

_FALLBACK_MEDICINES = {
    "paracetamol": {
        "generic_name": "Paracetamol",
        "match_name": "paracetamol",
        "strength": "500 mg",
        "active_ingredient": "acetaminophen",
        "manufacturer": None,
        "instructions": None,
        "common_uses": ["pain relief", "fever"],
        "warning": "Use only as directed.",
    },
}


# Dosage-form and bare-unit words that carry no brand-specific
# information. Most of the real 1mg reference dataset has these baked
# directly into the `name` field (e.g. "Aciloc 150 Tablet",
# "Omee Capsule"), unlike the original 12-entry demo set. Left in
# place, a single clearly-OCR'd word like "TABLET" — printed large on
# almost every box — can out-score the actual (harder to read) brand
# name against whichever short candidate happens to end the same way,
# and can even clear the pipeline's 80% "confidently name it"
# threshold on its own. These words are stripped from the text used
# for matching and are never allowed to count as match evidence by
# themselves.
_GENERIC_FORM_WORDS = {
    "tablet", "tablets", "tab", "tabs",
    "capsule", "capsules", "cap", "caps",
    "injection", "inj",
    "syrup", "suspension", "solution",
    "cream", "ointment", "gel", "lotion",
    "drops", "drop", "inhaler", "spray",
    "powder", "patch", "suppository",
    "ml", "mg", "mcg", "gm", "iu",
}

_GENERIC_WORD_RE = re.compile(
    r"\b(" + "|".join(_GENERIC_FORM_WORDS) + r")\b"
)


def _strip_generic_words(text: str) -> str:
    """Remove dosage-form/unit words, collapsing extra whitespace left behind."""
    stripped = _GENERIC_WORD_RE.sub(" ", text)
    return re.sub(r"\s+", " ", stripped).strip()


def _load_medicines() -> dict:
    """Build the MEDICINES lookup from the shared reference dataset."""

    try:
        with open(_REFERENCE_PATH, encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, ValueError):
        # Data file missing or unreadable — fall back rather than
        # crashing the whole matching module.
        return dict(_FALLBACK_MEDICINES)

    medicines = {}

    for entry in entries:
        name = entry.get("name")

        if not name:
            continue

        key = name.strip().lower()

        # Matching is done against the brand-specific part of the name
        # only (form words stripped) so a generic word alone can never
        # win; `generic_name` is kept as-is for display/spoken output.
        match_name = _strip_generic_words(name.lower()) or name.lower()

        medicines[key] = {
            "generic_name": name,
            "match_name": match_name,
            "strength": entry.get("strength"),
            "active_ingredient": entry.get("active_ingredient"),
            "manufacturer": entry.get("manufacturer"),
            "instructions": entry.get("instructions"),
            # Not part of the shared reference file yet; kept so
            # downstream voice responses have a consistent shape.
            "common_uses": entry.get("common_uses", []),
            "warning": entry.get("warning", "Use only as directed."),
        }

    return medicines or dict(_FALLBACK_MEDICINES)


MEDICINES = _load_medicines()


@dataclass
class MedicineMatch:
    medicine_key: str | None
    medicine_info: dict | None
    score: float
    matched_text: str | None


def normalize_text(text: str) -> str:
    """
    Normalize OCR text before comparison.
    """
    text = text.lower()

    # Remove special characters.
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def similarity(a: str, b: str) -> float:
    """
    Calculate similarity between two strings.
    """
    return SequenceMatcher(None, a, b).ratio()


def correct_common_ocr_errors(text: str) -> str:
    """
    Correct a few common OCR character errors.

    These corrections are intentionally conservative.
    """

    replacements = {
        "0": "o",
        "1": "l",
        "5": "s",
        "8": "b",
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    return text


def compare_ocr_text(text: str, medicine_name: str) -> float:
    """
    Compare OCR text against a medicine name using
    multiple matching strategies.

    Both arguments are expected to already be normalized by the
    caller (find_best_medicine_match does this once, up front) —
    normalize_text is not re-applied here so it runs exactly once
    per string instead of on every candidate comparison.
    """

    if not text:
        return 0.0

    # Short medicine names (≤ 4 chars, e.g. "alex", "nise") are
    # disproportionately easy to match by accident: SequenceMatcher
    # gives 0.57+ for unrelated 3-4 char fragments. Require the entire
    # text to contain an exact substring match for very short names,
    # not just a fuzzy character similarity.
    mn_len = len(medicine_name)
    if mn_len <= 4:
        # Must appear as a whole word in the text
        if re.search(r'\b' + re.escape(medicine_name) + r'\b', text):
            return 1.0
        return 0.0

    # Direct similarity.
    best_score = similarity(text, medicine_name)

    # OCR corrections.
    corrected_text = correct_common_ocr_errors(text)

    corrected_score = similarity(corrected_text, medicine_name)
    best_score = max(best_score, corrected_score)

    # Compare again with generic dosage-form/unit words removed from
    # the OCR side too. Without this, OCR text like "INJECTION" still
    # carries those characters into the whole-string comparison and
    # can pick up a coincidentally-similar (but unrelated) short
    # candidate name purely on character overlap, even though the
    # form word itself was already stripped from medicine_name.
    stripped_text = _strip_generic_words(corrected_text)
    if stripped_text:
        best_score = max(best_score, similarity(stripped_text, medicine_name))

    # Compare individual OCR words. Generic dosage-form/unit words
    # (tablet, capsule, ml, mg, ...) are skipped here even though most
    # are >=4 chars — printed large on nearly every box, a word like
    # "TABLET" reading cleanly says nothing about *which* medicine
    # this is, and letting it stand alone as evidence is what let it
    # out-score genuine (harder to read) brand-name matches.
    #
    # Also require the OCR word to be at least 60% as long as the
    # medicine match_name — a 3-char OCR fragment should never be
    # allowed to score highly against a 10-char medicine name just
    # because their characters happen to overlap.
    for word in corrected_text.split():

        if len(word) < 4 or word in _GENERIC_FORM_WORDS:
            continue

        # Skip words that are far shorter than the medicine name —
        # a short fragment can have misleadingly high SequenceMatcher
        # ratios against the beginning/end of a long name.
        if len(word) < mn_len * 0.6:
            continue

        word_score = similarity(word, medicine_name)
        best_score = max(best_score, word_score)

    return best_score


def find_best_medicine_match(ocr_texts: list[str]) -> MedicineMatch:
    """
    Find the medicine whose name most closely matches
    the OCR detections.
    """

    best_key = None
    best_info = None
    best_score = 0.0
    best_text = None

    # Normalize each OCR detection exactly once, up front. This used
    # to happen inside the medicine loop below, re-normalizing the
    # same OCR text once per medicine in MEDICINES (and then again
    # inside compare_ocr_text) — harmless since normalize_text is
    # idempotent, but wasted work repeated on every candidate.
    normalized_ocr_texts = []
    for raw_text in ocr_texts:
        if not isinstance(raw_text, str):
            continue
        text = normalize_text(raw_text)
        if text:
            normalized_ocr_texts.append(text)

    for medicine_key, medicine_info in MEDICINES.items():

        # Match against the brand-specific part of the name (form
        # words stripped) — see _strip_generic_words / _load_medicines.
        # Normalized once per medicine here, not once per (medicine,
        # OCR text) comparison inside compare_ocr_text.
        medicine_name = normalize_text(
            medicine_info.get("match_name") or medicine_info["generic_name"]
        )

        for text in normalized_ocr_texts:

            score = compare_ocr_text(
                text,
                medicine_name
            )

            if score > best_score:

                best_score = score
                best_key = medicine_key
                best_info = medicine_info
                best_text = text

    # Accept strong matches.
    #
    # 0.65 threshold (raised from 0.60) requires stronger evidence before
    # naming a medicine — the fuzzy match is already a generous comparison
    # and 0.60 was low enough that short, ambiguous names (e.g. "Alex")
    # were matching unrelated OCR tokens. Short medicine names (match_name
    # ≤ 5 chars) require an even tighter 0.80 to avoid false positives from
    # short common words on any medicine package.
    mn_len = len(normalize_text(best_info.get('match_name') or '')) if best_info else 0
    threshold = 0.80 if mn_len <= 5 else 0.65

    if best_score >= threshold:

        return MedicineMatch(
            medicine_key=best_key,
            medicine_info=best_info,
            score=best_score,
            matched_text=best_text,
        )

    # No sufficiently strong match.
    return MedicineMatch(
        medicine_key=None,
        medicine_info=None,
        score=best_score,
        matched_text=best_text,
    )