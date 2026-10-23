import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import cv2

from backend.perception.medicine_matcher import (
    MedicineMatch,
    find_best_medicine_match,
    normalize_text as normalize_medicine_text,
)

from backend.perception.medicine_info_extractor import (
    MedicineDetails,
    extract_medicine_details,
)

from backend.perception.date_extractor import (
    DATE_CONFIDENCE_THRESHOLD,
    extract_mfg_and_exp_dates,
)

from backend.perception.ocr import (
    OCRResult,
    PaddleOCREngine,
    RotationAwareOCREngine,
    TesseractOCREngine,
)

from backend.perception.preprocessing import (
    load_image,
    prepare_for_ocr,
)

logger = logging.getLogger(__name__)


# ============================================================
# MEDBOX CONFIDENCE SETTINGS
# ============================================================
#
# 6.6, Step 2 draws exactly one line: "if the score is high
# (roughly above 80%) ... If the score is low, MedBox does not
# read out a name at all". There is no documented middle tier, so
# there is exactly one threshold here, not two. (A previous version
# of this module had a second "medium confidence" tier that still
# named a candidate medicine below the high-confidence threshold —
# that directly contradicted 6.6 and has been removed.)

HIGH_CONFIDENCE_THRESHOLD = 0.80

# Ignore OCR detections below this confidence.
#
# Kept in sync with backend.perception.date_extractor.MIN_OCR_CONFIDENCE
# (0.30), which is the floor the date-extraction confidence formula is
# actually designed around. This used to be a stricter, independent 0.40
# here, which silently discarded OCR tokens in the 0.30-0.40 band before
# the date engine ever got a chance to score them — expiry-date print is
# often small/faint/embossed and lands disproportionately in that band,
# so real EXP dates were being thrown away rather than scored low.
MIN_OCR_CONFIDENCE = 0.30

# Item 5: fallback OCR floor used only when the standard pass
# (MIN_OCR_CONFIDENCE) finds no date at all — i.e. the digits were
# filtered out before the date engine ever got a candidate to score,
# not merely scored low. This is deliberately lower than
# MIN_OCR_CONFIDENCE and is used ONLY to retry date extraction, never
# to feed the medicine-name matcher: naming the wrong medicine is a
# much higher-stakes mistake (6.6 gates that at 80% confidence) than
# a date field, which already carries its own validation checks and
# its own 80% confirmation gate downstream. See
# `is_useful_ocr_result`, `filter_ocr_results`, and the retry block in
# `_run_pipeline` (step 7b).
RETRY_MIN_OCR_CONFIDENCE = 0.15

# ------------------------------------------------------------
# SCAN TIME BUDGET
# ------------------------------------------------------------
# Hard ceiling for one whole scan. The mandatory first OCR pass always
# runs; the optional multi-pass date recovery (step 7b) only gets whatever
# time is left, and each recovery pass is abandoned if it would overrun.
# SCAN_TIME_RESERVE_SECONDS stays free for matching + building the response.
SCAN_TIME_BUDGET_SECONDS = float(os.environ.get("MEDBOX_SCAN_TIME_BUDGET_SECONDS", "45"))
SCAN_TIME_RESERVE_SECONDS = 3.0

# Date-recovery image tuning (see step 7b). Side strips used to be upscaled a
# flat 3x and then upscaled another 1.5x inside the Tesseract engine (4.5x
# total, ~15 MP for a 30% strip), which made every retry pass very slow. The
# pixel cap keeps text large enough to read while bounding the cost.
STRIP_MAX_SCALE = 3.0
STRIP_MAX_PIXELS = 3_000_000

# Minimum fuzzy similarity for medicine evidence.
FUZZY_MATCH_THRESHOLD = 0.60

# Confidence-score weights (6.1 / 6.6, Step 1): "Engine agreement
# plus per-engine confidence produces a single confidence score" /
# "based on how well the two OCR engines agreed and how closely the
# text matched a known medicine in the database."
WEIGHT_MATCH_SCORE = 0.45
WEIGHT_OCR_CONFIDENCE = 0.30
WEIGHT_ENGINE_AGREEMENT = 0.25

# Weights used when only one OCR engine actually ran (e.g. the
# secondary engine isn't installed in this environment). There is
# no agreement signal to weigh in this case, so its share is folded
# back into the other two rather than silently boosting confidence.
WEIGHT_MATCH_SCORE_SINGLE_ENGINE = 0.60
WEIGHT_OCR_CONFIDENCE_SINGLE_ENGINE = 0.40


# ============================================================
# OCR ENGINE INTERFACE
# ============================================================

class OCREngine(Protocol):
    def recognize(self, image) -> list[OCRResult]:
        ...


@lru_cache(maxsize=1)
def _default_primary_engine() -> OCREngine:
    """Use PaddleOCR when present, otherwise run real Tesseract OCR.

    The former implementation raised when the optional Paddle package was
    absent, so the API discarded an otherwise usable local Tesseract install
    and always returned simulated recognition.  Tesseract remains a genuine
    OCR path; the service-level simulation is now reserved for when neither
    local engine can run.

    The chosen engine is wrapped in RotationAwareOCREngine so the mandatory
    first OCR pass (step 3) itself reads text correctly regardless of
    orientation -- a vertical medicine name, a horizontal expiry date and a
    rotated batch number can all be picked up from ONE pass over the same
    photo, rather than relying on the narrower, date-only rotation retry in
    step 7b below to rescue anything that wasn't upright. PaddleOCR's own
    use_angle_cls (see PaddleOCREngine) only corrects a line's 0/180-degree
    reading direction, not sideways (90/270) text, and TesseractOCREngine
    has no orientation-awareness of its own at all -- this wrapper covers
    both gaps for whichever engine ends up primary.
    """
    try:
        inner_engine = PaddleOCREngine()
        logger.info("Active OCR engine: PaddleOCR")
    except ImportError:
        logger.warning("PaddleOCR unavailable; active primary OCR engine: Tesseract")
        inner_engine = TesseractOCREngine()
    return RotationAwareOCREngine(inner_engine)


@lru_cache(maxsize=1)
def _default_secondary_engine() -> OCREngine:
    """Tesseract is the documented cross-check engine (6.1 / Section 10).

    Wrapped for the same reason as the primary engine above: Tesseract has
    no built-in orientation handling, so without this wrapper the
    cross-check engine would silently miss any rotated text the primary
    engine's rotation-awareness recovered, which would drag down the
    engine-agreement signal (6.1/6.6) for no good reason.
    """
    return RotationAwareOCREngine(TesseractOCREngine())


def _unwrap_ocr_engine(engine: OCREngine) -> OCREngine:
    """Return the plain (non-rotation-wrapped) engine underneath ``engine``.

    Returns ``engine`` itself when it isn't a RotationAwareOCREngine (e.g. a
    caller-supplied engine, or a test fake) -- unwrapping is a no-op in that
    case.
    """
    return getattr(engine, "inner_engine", engine)


# ============================================================
# OCR CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """
    Clean OCR text while preserving useful characters.
    """

    if not text:
        return ""

    text = str(text).strip()

    # Replace repeated whitespace.
    text = re.sub(r"\s+", " ", text)

    return text


def is_useful_ocr_result(
    result: OCRResult,
    min_confidence: float = MIN_OCR_CONFIDENCE,
    min_length: int = 2,
) -> bool:
    """
    Remove obvious OCR garbage.

    OCR detections below ``min_confidence`` are ignored. Defaults to
    MIN_OCR_CONFIDENCE; the date-extraction retry pass (item 5) calls
    this with the lower RETRY_MIN_OCR_CONFIDENCE instead, but only for
    a date-only re-extraction, never for the medicine-name path.

    ``min_length`` used to be a hardcoded ``< 2`` cutoff applied
    unconditionally, regardless of ``min_confidence``. That silently
    discarded every single-character OCR token — and embossed/foil
    pharmaceutical date strips are routinely segmented character-by-
    character by Tesseract/PaddleOCR (e.g. "EXP. FEB.2030" comes back
    as separate one-character boxes: "E", "X", "P", ".", "F", "E"...).
    Because this length check ran before the confidence check even
    mattered, the item-5 date-retry pass's lower RETRY_MIN_OCR_CONFIDENCE
    never got a chance to rescue those tokens — they were gone before
    extract_dates_from_text ever saw them, producing a genuine zero
    date candidates rather than a low-confidence one. The retry pass
    now calls this with min_length=1 so single-character fragments can
    still combine into a date via the multi-token/combined-text path.
    """

    text = clean_text(result.text)

    if not text:
        return False

    # Ignore low-confidence OCR.
    if result.confidence < min_confidence:
        return False

    # Ignore extremely short detections.
    if len(text) < min_length:
        return False

    # Count letters and numbers.
    alphanumeric = sum(
        character.isalnum()
        for character in text
    )

    if alphanumeric == 0:
        return False

    # Ignore text that is mostly symbols.
    ratio = alphanumeric / len(text)

    if ratio < 0.50:
        return False

    return True


def filter_ocr_results(
    ocr_results: list[OCRResult],
    min_confidence: float = MIN_OCR_CONFIDENCE,
    min_length: int = 2,
) -> list[OCRResult]:
    """
    Keep only useful OCR detections at or above ``min_confidence``.

    ``min_length`` is forwarded to `is_useful_ocr_result` — the
    date-extraction retry pass calls this with min_length=1 so that
    character-segmented date fragments (common on embossed/foil
    packaging) aren't discarded before the date engine can combine
    them via its multi-token text-joining path.
    """

    filtered = []

    for result in ocr_results:

        if not is_useful_ocr_result(result, min_confidence=min_confidence, min_length=min_length):
            continue

        # Clean OCR text.
        try:
            result.text = clean_text(result.text)
        except Exception:
            pass

        filtered.append(result)

    return filtered


# ============================================================
# MEDICINE EVIDENCE
# ============================================================

def calculate_medicine_ocr_confidence(
    ocr_results: list[OCRResult],
    medicine_match: MedicineMatch,
) -> float:
    """
    Calculate OCR confidence supporting the medicine match.

    Uses:
    1. Exact/contained matching.
    2. Individual-word fuzzy matching.
    3. The matcher score as fallback evidence.

    Deliberately compares against `all_ocr_results` (raw, per-engine
    OCRResult objects with their own confidence scores) rather than
    the normalized text from step 6. This needs each detection's
    individual confidence value, which only lives on the raw
    OCRResult objects — normalized_texts is a flat list of strings
    with that per-result confidence already discarded. Only text
    equality/similarity is compared here, so normalization
    (lowercasing, punctuation stripping) doesn't need to have already
    happened — `clean_text(result.text).lower()` below is sufficient.
    """

    if not medicine_match.medicine_key:
        return 0.0

    if not medicine_match.medicine_info:
        return 0.0

    medicine_name = str(
        medicine_match.medicine_info.get(
            "generic_name",
            "",
        )
    ).lower().strip()

    if not medicine_name:
        return 0.0

    best_evidence = 0.0

    # --------------------------------------------------------
    # Examine every OCR detection.
    # --------------------------------------------------------

    for result in ocr_results:

        text = clean_text(result.text).lower()

        if not text:
            continue

        # ----------------------------------------------------
        # Exact / contained match
        # ----------------------------------------------------

        if medicine_name in text:

            evidence = float(result.confidence)

            best_evidence = max(
                best_evidence,
                evidence,
            )

            continue

        # ----------------------------------------------------
        # Compare individual words.
        # ----------------------------------------------------

        for word in text.split():

            if len(word) < 4:
                continue

            similarity = SequenceMatcher(
                None,
                word,
                medicine_name,
            ).ratio()

            if similarity >= FUZZY_MATCH_THRESHOLD:

                evidence = (
                    float(result.confidence)
                    * similarity
                )

                best_evidence = max(
                    best_evidence,
                    evidence,
                )

    # --------------------------------------------------------
    # Matcher score fallback.
    # --------------------------------------------------------

    if medicine_match.score > 0:

        matcher_evidence = (
            float(medicine_match.score)
            * 0.70
        )

        best_evidence = max(
            best_evidence,
            matcher_evidence,
        )

    return min(
        max(best_evidence, 0.0),
        1.0,
    )


# ============================================================
# ENGINE AGREEMENT (6.1 / 6.6, Step 1)
# ============================================================

def calculate_engine_agreement(
    primary_texts: list[str],
    secondary_texts: list[str],
) -> float | None:
    """
    Estimate how well the two OCR engines agree on what's on the
    package, independent of whether either one matched a known
    medicine yet.

    Returns None when only one engine actually produced usable
    text, since there is nothing to compare against — the caller
    treats that as "no cross-check available" rather than as
    disagreement.
    """

    if not primary_texts or not secondary_texts:
        return None

    primary_combined = " ".join(primary_texts).lower()
    secondary_combined = " ".join(secondary_texts).lower()

    if not primary_combined or not secondary_combined:
        return None

    return SequenceMatcher(
        None,
        primary_combined,
        secondary_combined,
    ).ratio()


# ============================================================
# MAIN MEDBOX PIPELINE
# ============================================================

def recognize_medicine(
    image_path: str | Path,
    ocr_engine: OCREngine | None = None,
    secondary_ocr_engine: OCREngine | None = None,
    scan_mode: str = "both",
) -> dict[str, object]:
    """
    Run the complete MedBox medicine recognition pipeline.

    Pipeline (6.1):

        Image
          -> Preprocessing (OpenCV)
          -> Primary OCR (PaddleOCR) + Secondary OCR (Tesseract), in parallel
          -> OCR filtering
          -> Package information extraction
          -> Medicine matching
          -> Confidence calculation (matcher score + OCR confidence + engine agreement)
          -> Safe structured result (6.6 / Section 13)

    ``ocr_engine`` overrides the primary engine (defaults to
    PaddleOCR) and ``secondary_ocr_engine`` overrides the cross-check
    engine (defaults to Tesseract). Both are only auto-constructed
    when the caller supplies neither — a test that passes a single
    fake ``ocr_engine`` still runs in single-engine mode rather than
    silently instantiating a second real engine.
    """

    result, _ocr_texts = _run_pipeline(
        image_path,
        ocr_engine=ocr_engine,
        secondary_ocr_engine=secondary_ocr_engine,
        scan_mode=scan_mode,
    )
    return result


def recognize_medicine_with_audit_trail(
    image_path: str | Path,
    ocr_engine: OCREngine | None = None,
    secondary_ocr_engine: OCREngine | None = None,
    scan_mode: str = "both",
) -> tuple[dict[str, object], str]:
    """
    Same pipeline and same safety guarantees as ``recognize_medicine``,
    but additionally returns the raw combined OCR text alongside the
    safety result.

    ``recognize_medicine`` deliberately never exposes raw OCR text in
    its result (6.6 / Section 13) — it isn't something to read out or
    act on. This wrapper exists for callers like the backend's
    recognition-history audit trail (7.6), which needs *some* record
    of what the scan actually saw, purely for logging, without
    re-running OCR a second time or loosening what
    ``recognize_medicine`` itself promises callers.
    """

    result, ocr_texts = _run_pipeline(
        image_path,
        ocr_engine=ocr_engine,
        secondary_ocr_engine=secondary_ocr_engine,
        scan_mode=scan_mode,
    )
    return result, " ".join(ocr_texts)


def _run_ocr_engines(
    prepared_image,
    primary_engine: OCREngine,
    ocr_engine: OCREngine | None,
    secondary_ocr_engine: OCREngine | None,
) -> tuple[list[OCRResult], list[OCRResult]]:
    """
    Run the primary and secondary OCR engines concurrently (6.1: "in
    parallel"). Both engines spend nearly all their time in native code /
    subprocesses, so plain threads give a real speed-up.

    Error semantics match the previous sequential code: a primary-engine
    failure, or a failure of an explicitly supplied secondary engine,
    propagates; a failure of the auto-constructed default secondary engine
    just means primary-only recognition.
    """

    # Caller supplied both engines explicitly: errors from either propagate.
    if secondary_ocr_engine is not None:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="medbox-ocr") as pool:
            primary_future = pool.submit(primary_engine.recognize, prepared_image)
            secondary_future = pool.submit(secondary_ocr_engine.recognize, prepared_image)
            primary_results = primary_future.result()
            secondary_results = secondary_future.result()
        return primary_results, secondary_results

    # Caller supplied a single (primary) engine: single-engine mode.
    if ocr_engine is not None:
        return primary_engine.recognize(prepared_image), []

    # Default engines: primary + Tesseract cross-check.
    try:
        sec_eng = _default_secondary_engine()
    except Exception:
        logger.warning(
            "Secondary OCR engine unavailable; continuing "
            "with primary-only recognition."
        )
        return primary_engine.recognize(prepared_image), []

    if isinstance(_unwrap_ocr_engine(primary_engine), TesseractOCREngine) and isinstance(
        _unwrap_ocr_engine(sec_eng), TesseractOCREngine
    ):
        # Same engine twice (both fell back to Tesseract because PaddleOCR
        # isn't installed) would just repeat identical work -- unwrapped
        # here since both are now RotationAwareOCREngine(TesseractOCREngine())
        # instances rather than bare TesseractOCREngine ones.
        primary_results = primary_engine.recognize(prepared_image)
        return primary_results, primary_results

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="medbox-ocr") as pool:
        primary_future = pool.submit(primary_engine.recognize, prepared_image)
        secondary_future = pool.submit(sec_eng.recognize, prepared_image)
        primary_results = primary_future.result()
        try:
            secondary_results = secondary_future.result()
        except Exception:
            logger.warning(
                "Secondary OCR engine unavailable; continuing "
                "with primary-only recognition."
            )
            secondary_results = []
    return primary_results, secondary_results


class _RetryBudget:
    """Wall-clock budget shared by all optional date-recovery OCR passes."""

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.exhausted = False

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def has_time(self) -> bool:
        if self.exhausted:
            return False
        if self.remaining() <= 0:
            self.exhausted = True
            return False
        return True


def _run_pipeline(
    image_path: str | Path,
    ocr_engine: OCREngine | None = None,
    secondary_ocr_engine: OCREngine | None = None,
    scan_mode: str = "both",
) -> tuple[dict[str, object], list[str]]:
    """Shared implementation behind both public entry points above."""

    scan_started = time.monotonic()

    # --------------------------------------------------------
    # 1-2. Load + preprocess image
    # --------------------------------------------------------

    image = load_image(image_path)
    full_prepared_image = prepare_for_ocr(image)
    prepared_image = full_prepared_image

    # Read the most information-dense region first. The full frame remains
    # available as a fallback for weak or mode-specific reads.
    if scan_mode == "medicine":
        h = max(1, int(prepared_image.shape[0] * 0.35))
        prepared_image = prepared_image[:h, :]
    elif scan_mode == "expiry":
        width = max(1, int(prepared_image.shape[1] * 0.30))
        prepared_image = prepared_image[:, :width]

    # --------------------------------------------------------
    # 3. Run OCR engines
    #
    # 6.1: "run through two OCR engines in parallel — PaddleOCR as
    # primary, Tesseract/EasyOCR as a cross-check." A previous
    # version of this pipeline only ever ran a single engine
    # (Tesseract) and never used PaddleOCR at all, so there was no
    # cross-check and no engine-agreement signal feeding into 6.6's
    # confidence score. That is corrected here.
    # --------------------------------------------------------

    primary_engine = ocr_engine or _default_primary_engine()
    primary_raw_results, secondary_raw_results = _run_ocr_engines(
        prepared_image,
        primary_engine,
        ocr_engine=ocr_engine,
        secondary_ocr_engine=secondary_ocr_engine,
    )

    # ROI is the fast path. If it produced no usable evidence, retry once on
    # the complete frame before the later date-specific recovery passes.
    roi_results = primary_raw_results + secondary_raw_results
    if scan_mode == "medicine" and not roi_results:
        primary_raw_results, secondary_raw_results = _run_ocr_engines(
            full_prepared_image,
            primary_engine,
            ocr_engine=ocr_engine,
            secondary_ocr_engine=secondary_ocr_engine,
        )
    elif scan_mode == "expiry" and not any(
        re.search(r"\b(?:EXP|MFG|LOT|BATCH)\b|\d{1,2}[/-]\d{2,4}", r.text or "", re.IGNORECASE)
        for r in roi_results
    ):
        width = max(1, int(full_prepared_image.shape[1] * 0.30))
        right_strip = full_prepared_image[:, -width:]
        primary_raw_results, secondary_raw_results = _run_ocr_engines(
            right_strip,
            primary_engine,
            ocr_engine=ocr_engine,
            secondary_ocr_engine=secondary_ocr_engine,
        )

    # The step 7b date-recovery passes below do their OWN manual rotation
    # of small strips/the full image (cv2.rotate, pre-existing logic, left
    # untouched). If they ran through primary_engine as-is, a
    # RotationAwareOCREngine-wrapped primary would rotate those
    # already-rotated crops another 4 ways each -- 4x slower per retry pass
    # for no benefit, and prone to eating the whole retry time budget.
    # retry_ocr_engine is the plain engine underneath, so step 7b keeps
    # doing exactly its own single, targeted rotation per pass.
    retry_ocr_engine = _unwrap_ocr_engine(primary_engine)

    # --------------------------------------------------------
    # 4. Filter OCR results (per engine)
    # --------------------------------------------------------

    primary_results = filter_ocr_results(primary_raw_results)
    secondary_results = filter_ocr_results(secondary_raw_results)

    all_ocr_results = primary_results + secondary_results

    # --------------------------------------------------------
    # 5. Extract OCR text
    # --------------------------------------------------------

    primary_texts = [
        clean_text(result.text)
        for result in primary_results
        if clean_text(result.text)
    ]
    secondary_texts = [
        clean_text(result.text)
        for result in secondary_results
        if clean_text(result.text)
    ]
    ocr_texts = primary_texts + secondary_texts

    print(
        f"OCR stage raw Paddle/secondary results: {[result.text for result in all_ocr_results]!r}",
        flush=True,
    )
    logger.debug("Primary OCR text: %r", primary_texts)
    logger.debug("Secondary OCR text: %r", secondary_texts)

    # --------------------------------------------------------
    # 6. Normalize text
    #
    # Diagram order is OCR extracts text -> Normalize text -> Fuzzy
    # match against medicine dataset. Normalization (lowercasing,
    # stripping punctuation/symbols, collapsing whitespace) was
    # previously only ever applied implicitly, inside the matcher's
    # own comparison helpers. It is pulled out here as its own
    # explicit stage so the pipeline's step order matches the
    # documented flow and the normalized text is available on its
    # own, not just as a side effect of matching.
    # --------------------------------------------------------

    normalized_texts = [
        normalize_medicine_text(text)
        for text in ocr_texts
        if normalize_medicine_text(text)
    ]

    logger.debug("Normalized OCR text: %r", normalized_texts)

    # --------------------------------------------------------
    # 7. Extract package-specific medicine information
    #
    # This includes:
    # - Dosage
    # - Manufacturing date
    # - Expiry date
    # - Batch number
    #
    # Uses the raw (pre-normalization) OCR text, since normalization
    # strips punctuation that dates/batch numbers rely on (e.g. "/",
    # "-") — only the matching step below needs normalized text.
    # --------------------------------------------------------

    medicine_details = (
        MedicineDetails()
        if scan_mode == "medicine"
        else extract_medicine_details(all_ocr_results if all_ocr_results else ocr_texts)
    )

    # --------------------------------------------------------
    # 7b. Fallback date pass (item 5): retry with a lenient OCR floor
    #
    # Fires only when the standard pass found NO date at all for a
    # field (not merely a low-confidence one — that case already goes
    # through the normal 80% gate and correctly asks for a rescan/
    # confirmation). A missing field usually means the real digits
    # never made it past MIN_OCR_CONFIDENCE in the first place, so
    # there was nothing for the date engine to score.
    #
    # RETRY_MIN_OCR_CONFIDENCE (0.15) < MIN_OCR_CONFIDENCE (0.30), so
    # the lenient token set is always a superset of the strict one —
    # this can only find a field the strict pass missed, never lose
    # one it already had, but `retry_is_safe` below checks that
    # explicitly rather than assuming it.
    #
    # Scoped to date extraction only: the lenient OCR results never
    # touch `all_ocr_results`, `normalized_texts`, or the medicine
    # matcher, so a faint digit can rescue a date field without a
    # faint word ever being allowed to help name a medicine.
    # --------------------------------------------------------

    date_retry_package_details: dict[str, object] | None = None
    date_retry_budget_exhausted = False

    # ── Multi-pass date recovery ──────────────────────────────────────────
    # Indian medicine packages (Dolo-650, Crocin, etc.) print EXP on a
    # narrow vertical side strip. Running OCR on the full-width image means
    # that strip occupies only a tiny fraction of pixels — too small for
    # Tesseract to read reliably. Strategy (cheapest / most likely first):
    #   Pass 0   — Lenient standard orientation (re-scores existing OCR
    #              output; no new OCR run, so it is essentially free).
    #   Pass 1-4 — Crop the left/right 30% strips, scale them up (capped by
    #              STRIP_MAX_PIXELS) and OCR them rotated 90° CW and CCW.
    #              Side-strip text is almost always rotated 90°; 0° is
    #              already covered by the main pass and 180° is rare.
    #   Pass 5-6 — Full-image 90° rotations (fallback for packages where the
    #              date area is centred rather than on an edge strip). These
    #              are the most expensive passes, so they run last.
    #
    # Cost control:
    #   (a) Skip the entire block if the fast path already found an expiry
    #       date at or above the confirmation threshold.
    #   (b) Stop as soon as any pass produces a candidate at or above the
    #       confirmation threshold.
    #   (c) Hard wall-clock budget: the whole scan (first OCR pass included)
    #       is held to SCAN_TIME_BUDGET_SECONDS. Every OCR pass here is run
    #       with a timeout equal to the time still left; once the budget is
    #       gone no further passes start and the best candidate found so far
    #       is used (a low-confidence result simply asks for a rescan).
    candidates = []

    fast_path_exp_confident = scan_mode == "medicine" or (
        bool(medicine_details.expiry_date)
        and medicine_details.date_confidence >= DATE_CONFIDENCE_THRESHOLD
    )

    if fast_path_exp_confident:
        logger.debug(
            "Date multi-pass retry skipped: fast path already confident (%.1f%%).",
            medicine_details.date_confidence,
        )
    else:
        import numpy as np

        retry_budget = _RetryBudget(
            scan_started + SCAN_TIME_BUDGET_SECONDS - SCAN_TIME_RESERVE_SECONDS
        )
        # One worker: passes run one after another, but each can be abandoned
        # at the deadline (an in-flight OCR call can't be interrupted, so it
        # is left to finish in the background while the request returns).
        retry_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="medbox-date-retry")

        def _ocr_image_leniently(img: "np.ndarray") -> "list":
            """Run primary OCR on img within the remaining budget.

            Uses retry_ocr_engine (the unwrapped engine) rather than
            primary_engine directly -- see the comment where
            retry_ocr_engine is set, in step 3 above.
            """
            if not retry_budget.has_time():
                return []
            future = retry_executor.submit(retry_ocr_engine.recognize, img)
            try:
                raw = future.result(timeout=retry_budget.remaining())
            except FutureTimeoutError:
                retry_budget.exhausted = True
                future.cancel()
                logger.warning(
                    "Date retry pass abandoned: scan time budget (%.0fs) reached.",
                    SCAN_TIME_BUDGET_SECONDS,
                )
                return []
            except Exception:
                return []
            return filter_ocr_results(raw, min_confidence=RETRY_MIN_OCR_CONFIDENCE, min_length=1)

        def _extract_candidate(ocr_items: "list") -> "object | None":
            if not ocr_items:
                return None
            return extract_mfg_and_exp_dates(ocr_items)

        def _candidate_is_good_enough(c) -> bool:
            return bool(c) and c.overall_confidence >= DATE_CONFIDENCE_THRESHOLD

        def _done() -> bool:
            return (not retry_budget.has_time()) or any(
                _candidate_is_good_enough(c) for c in candidates
            )

        def _scale_strip(strip: "np.ndarray") -> "np.ndarray":
            """Upscale a strip for OCR, capped so the pixel count stays bounded."""
            sh, sw = strip.shape[:2]
            scale = min(STRIP_MAX_SCALE, (STRIP_MAX_PIXELS / max(1, sh * sw)) ** 0.5)
            if scale <= 1.0:
                return strip
            return cv2.resize(strip, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        try:
            # Pass 0: lenient standard orientation (re-scoring only, no new OCR)
            base_lenient = (
                filter_ocr_results(primary_raw_results, min_confidence=RETRY_MIN_OCR_CONFIDENCE, min_length=1)
                + filter_ocr_results(secondary_raw_results, min_confidence=RETRY_MIN_OCR_CONFIDENCE, min_length=1)
            )
            c = _extract_candidate(base_lenient)
            if c:
                candidates.append(c)

            # Pass 1-4: left and right 30% strips, rotated 90° each way
            if not _done():
                try:
                    h, w = prepared_image.shape[:2]
                    strip_w = max(1, int(w * 0.30))
                    for strip in (prepared_image[:, :strip_w], prepared_image[:, w - strip_w:]):
                        scaled = _scale_strip(strip)
                        for rot_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                            c = _extract_candidate(_ocr_image_leniently(cv2.rotate(scaled, rot_code)))
                            if c:
                                candidates.append(c)
                            if _done():
                                break
                        if _done():
                            break
                except Exception as err:
                    logger.debug("Side-strip date scan skipped: %s", err)

            # Pass 5-6: full-image 90° rotations (centre-printed dates)
            if not _done():
                try:
                    for rot_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                        c = _extract_candidate(_ocr_image_leniently(cv2.rotate(prepared_image, rot_code)))
                        if c:
                            candidates.append(c)
                        if _done():
                            break
                except Exception as err:
                    logger.debug("Full-image rotation date scan skipped: %s", err)
        finally:
            date_retry_budget_exhausted = retry_budget.exhausted or not retry_budget.has_time()
            retry_executor.shutdown(wait=False, cancel_futures=True)

    if candidates:
        # Pick the candidate with the highest overall date confidence.
        retry_date_result = max(candidates, key=lambda r: r.overall_confidence)

        gained_mfg = bool(retry_date_result.mfg_date) and not medicine_details.manufacturing_date
        gained_exp = bool(retry_date_result.exp_date) and not medicine_details.expiry_date
        higher_conf = retry_date_result.overall_confidence > medicine_details.date_confidence

        if higher_conf or gained_mfg or gained_exp:
            logger.info(
                "Date strip-scan selected (MFG: %s, EXP: %s, Conf: %.1f%% vs prev %.1f%%).",
                retry_date_result.mfg_date,
                retry_date_result.exp_date,
                retry_date_result.overall_confidence,
                medicine_details.date_confidence,
            )
            date_retry_package_details = {
                "manufacturing_date": retry_date_result.mfg_date,
                "expiry_date": retry_date_result.exp_date,
                "date_confidence": retry_date_result.overall_confidence,
                "date_needs_rescan": retry_date_result.needs_rescan,
                "date_validation_errors": retry_date_result.validation_errors,
                "matched_keyword": retry_date_result.details.get("matched_keyword"),
                "raw_date_result": {
                    "mfg_date": retry_date_result.mfg_date,
                    "exp_date": retry_date_result.exp_date,
                    "mfg_confidence": retry_date_result.mfg_confidence,
                    "exp_confidence": retry_date_result.exp_confidence,
                    "overall_confidence": retry_date_result.overall_confidence,
                    "is_valid": retry_date_result.is_valid,
                    "needs_rescan": retry_date_result.needs_rescan,
                    "validation_errors": retry_date_result.validation_errors,
                    "status": retry_date_result.status,
                    "mfg_bbox": retry_date_result.mfg_bbox,
                    "exp_bbox": retry_date_result.exp_bbox,
                    "matched_keyword": retry_date_result.details.get("matched_keyword"),
                },
                "date_retry_used": True,
            }


    # --------------------------------------------------------
    # 8. Fuzzy match against medicine dataset
    # --------------------------------------------------------

    medicine_match = (
        MedicineMatch(None, None, 0.0, None)
        if scan_mode == "expiry"
        else find_best_medicine_match(normalized_texts)
    )

    # --------------------------------------------------------
    # 9. Calculate OCR evidence + engine agreement
    # --------------------------------------------------------

    ocr_confidence = calculate_medicine_ocr_confidence(
        all_ocr_results,
        medicine_match,
    )

    engine_agreement = calculate_engine_agreement(
        primary_texts,
        secondary_texts,
    )

    # --------------------------------------------------------
    # 10. Calculate final confidence
    # --------------------------------------------------------

    if medicine_match.medicine_key:

        if engine_agreement is None:
            # Single-engine run: no agreement signal available.
            combined_confidence = (
                WEIGHT_MATCH_SCORE_SINGLE_ENGINE * medicine_match.score
                + WEIGHT_OCR_CONFIDENCE_SINGLE_ENGINE * ocr_confidence
            )
        else:
            combined_confidence = (
                WEIGHT_MATCH_SCORE * medicine_match.score
                + WEIGHT_OCR_CONFIDENCE * ocr_confidence
                + WEIGHT_ENGINE_AGREEMENT * engine_agreement
            )

    else:

        combined_confidence = 0.0

    # --------------------------------------------------------
    # 11. Build final result
    # --------------------------------------------------------

    safety_result = _build_safety_result(
        medicine_match=medicine_match,
        confidence=combined_confidence,
        medicine_details=medicine_details,
        engine_agreement=engine_agreement,
    )

    # Apply the item-5 date retry, if it recovered anything. Only the
    # date-related keys are touched — dosage/batch_number and the
    # medicine-name/confidence decision above are entirely unaffected,
    # since the retry never ran medicine matching.
    if date_retry_package_details is not None:
        safety_result["package_details"].update(date_retry_package_details)
    else:
        safety_result["package_details"].setdefault("date_retry_used", False)

    scan_seconds = time.monotonic() - scan_started
    safety_result["package_details"]["date_retry_budget_exhausted"] = date_retry_budget_exhausted
    safety_result["package_details"]["scan_seconds"] = round(scan_seconds, 2)
    logger.info("Scan finished in %.1fs (budget %.0fs).", scan_seconds, SCAN_TIME_BUDGET_SECONDS)

    return safety_result, ocr_texts


# ============================================================
# FINAL OUTPUT
# ============================================================

def _build_safety_result(
    medicine_match: MedicineMatch,
    confidence: float,
    medicine_details,
    engine_agreement: float | None = None,
) -> dict[str, object]:
    """
    Build a clean structured result.

    Raw OCR text is intentionally not returned.

    Package-specific information extracted directly from
    the medicine package is stored separately from general
    medicine information.

    6.6 / Section 13 / FR10: MedBox must never treat a recognition
    result as already-confirmed. This function only ever describes
    a *candidate* result for the voice/confirmation layer to read
    back — it never sets ``needs_confirmation`` to False, and it
    never exposes a candidate name below the high-confidence
    threshold (a previous version did both: it skipped confirmation
    entirely above 80%, and named a candidate medicine in a "medium
    confidence" tier below 80% — 6.6 explicitly says a low-confidence
    read "does not read out a name at all").
    """

    confidence = round(
        max(
            0.0,
            min(1.0, confidence),
        ),
        3,
    )

    # ========================================================
    # PACKAGE INFORMATION
    # ========================================================

    package_details = {
        "dosage": medicine_details.dosage,
        "manufacturing_date": medicine_details.manufacturing_date,
        "mfg_date": medicine_details.manufacturing_date,
        "expiry_date": medicine_details.expiry_date,
        "batch_number": medicine_details.batch_number,
        "date_confidence": medicine_details.date_confidence,
        "date_needs_rescan": medicine_details.date_needs_rescan,
        "date_validation_errors": medicine_details.date_validation_errors,
        "raw_date_result": medicine_details.raw_date_result,
        "matched_keyword": (medicine_details.raw_date_result or {}).get("matched_keyword"),
    }

    # ========================================================
    # HIGH CONFIDENCE — read back the candidate and ask "is that
    # right?" (7.6). Confirmation is still required; nothing here
    # is saved or acted on until that confirmation happens (FR10).
    # ========================================================

    if (
        medicine_match.medicine_key
        and medicine_match.medicine_info
        and confidence >= HIGH_CONFIDENCE_THRESHOLD
    ):

        medicine_info = medicine_match.medicine_info

        return {
            "recognized": True,

            "medicine_name": medicine_info["generic_name"],

            "candidate_medicine": medicine_info["generic_name"],

            "confidence": confidence,

            "engine_agreement": engine_agreement,

            "needs_confirmation": True,

            "medicine_info": medicine_info,

            "package_details": package_details,

            "message":
                f"The medicine appears to be {medicine_info['generic_name']}"
                + (
                    f" {medicine_info['strength']}."
                    if medicine_info.get("strength")
                    else "."
                )
                + " Is that right?",

            "status": "Needs Confirmation",
        }

    # ========================================================
    # BELOW THRESHOLD — no name is guessed at all (6.6, Step 2).
    # Any candidate the matcher found internally is deliberately
    # withheld from the response so it can never be spoken.
    # ========================================================

    return {
        "recognized": False,

        "medicine_name": None,

        "candidate_medicine": None,

        "confidence": confidence,

        "engine_agreement": engine_agreement,

        "needs_confirmation": True,

        "medicine_info": None,

        "package_details": package_details,

        "message":
            "I am not confident about the medicine name. "
            "Please capture the package again with better lighting.",

        "status": "Needs Rescan",
    }
