"""
Tests for the orientation-aware OCR layer (backend/perception/ocr.py).

Covers:
  1. Normal horizontal medicine image.
  2. Vertically oriented medicine name.
  3. Rotated expiry date.
  4. Medicine name vertical + expiry date horizontal in the SAME image
     (end-to-end through the real pipeline, so this also proves the
     existing expiry-date regex / medicine-name matcher run unchanged).
  5. Text detected from multiple rotations, correctly deduplicated.
  6. Low-confidence OCR results (engine keeps them; pipeline filter drops them).
  7. Normal image where no rotation is required (single 0-degree pass, no dup noise).
  8. Existing expiry-date regex behavior continuing to work unchanged.

No real camera / real PaddleOCR install is required: rotation orchestration
is tested against small in-memory numpy images and fake inner OCR engines
(the same FakeOCREngine pattern already used by test_perception_pipeline.py),
and PaddleOCR's angle-classification config is tested by injecting a fake
``paddleocr`` module so the test doesn't depend on the (optional, heavy)
real package being installed.
"""
import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.perception.ocr import (
    OCRResult,
    RotationAwareOCREngine,
    _map_bbox_to_original,
    _rotate_image,
    deduplicate_ocr_results,
)
from backend.perception.pipeline import recognize_medicine
import os

IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "medicine_images", "image.png"
)


# ============================================================
# Test helpers
# ============================================================


class FakeSequentialOCREngine:
    """Fake inner OCR engine for RotationAwareOCREngine.

    Returns one canned list of OCRResult per call, in call order. This
    mirrors how RotationAwareOCREngine actually drives an inner engine --
    once per configured rotation, in order (0, 90, 180, 270 by default) --
    without needing real image content or a real OCR backend for each
    orientation.
    """

    def __init__(self, results_by_call):
        self._queue = list(results_by_call)
        self.calls = []

    def recognize(self, image):
        self.calls.append(image.shape)
        if not self._queue:
            return []
        return self._queue.pop(0)


class FlakyOCREngine:
    """Fake inner engine that raises on a specific call index."""

    def __init__(self, results_by_call, fail_on_call_index):
        self._queue = list(results_by_call)
        self._fail_on = fail_on_call_index
        self._call_index = -1

    def recognize(self, image):
        self._call_index += 1
        if self._call_index == self._fail_on:
            raise RuntimeError("simulated transient OCR engine failure")
        if self._call_index < len(self._queue):
            return self._queue[self._call_index]
        return []


# ============================================================
# 1. Normal horizontal medicine image
# ============================================================


def test_normal_horizontal_image_recovers_text_at_zero_degrees():
    horizontal_hit = [OCRResult("PARACETAMOL 500MG", 0.93, [[5, 5], [80, 5], [80, 20], [5, 20]])]
    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([horizontal_hit, [], [], []])
    )

    image = np.zeros((100, 200, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].text == "PARACETAMOL 500MG"
    assert results[0].confidence == pytest.approx(0.93)
    assert results[0].angle == 0


# ============================================================
# 2. Vertically oriented medicine name
# ============================================================


def test_vertical_medicine_name_recovered_via_90_degree_pass():
    # Nothing legible at 0 degrees; the name only comes back once the
    # engine sees the image rotated 90 degrees (i.e. it was printed
    # vertically on the package).
    vertical_hit = [OCRResult("AMOXICILLIN", 0.88, [[2, 2], [40, 2], [40, 12], [2, 12]])]
    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([[], vertical_hit, [], []])
    )

    image = np.zeros((120, 60, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].text == "AMOXICILLIN"
    assert results[0].angle == 90
    # bbox must be re-projected into the ORIGINAL image's coordinate
    # space, not left in the rotated frame's coordinates.
    for point in results[0].bbox:
        x, y = point
        assert 0 <= x <= 60
        assert 0 <= y <= 120


# ============================================================
# 3. Rotated expiry date
# ============================================================


def test_rotated_expiry_date_recovered_via_270_degree_pass():
    exp_hit = [OCRResult("EXP 05/2027", 0.81, [[1, 1], [30, 1], [30, 9], [1, 9]])]
    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([[], [], [], exp_hit])
    )

    image = np.zeros((150, 90, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].text == "EXP 05/2027"
    assert results[0].angle == 270


# ============================================================
# 4. Medicine name vertical + expiry date horizontal, SAME image
#    (end-to-end through the real pipeline: proves the existing
#    medicine-name matcher and expiry-date regex are untouched)
# ============================================================


def test_vertical_name_and_horizontal_date_in_same_image_end_to_end():
    exp_at_zero = [
        OCRResult("EXP 08/2028", 0.90, [[10, 10], [70, 10], [70, 22], [10, 22]])
    ]
    name_at_ninety = [
        OCRResult("PARACETAMOL", 0.97, [[3, 3], [50, 3], [50, 15], [3, 15]])
    ]
    batch_at_one_eighty = [
        OCRResult("BATCH B4471", 0.70, [[4, 4], [44, 4], [44, 14], [4, 14]])
    ]

    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine(
            [exp_at_zero, name_at_ninety, batch_at_one_eighty, []]
        )
    )

    result = recognize_medicine(IMAGE_PATH, ocr_engine=engine)

    # Medicine-name matching (untouched) still recognizes the name that
    # only showed up in the 90-degree pass.
    assert result["recognized"] is True
    assert result["medicine_name"] == "Paracetamol"

    # Expiry-date regex/detection (untouched) still recovers the date
    # that only showed up in the 0-degree pass, even though it arrived
    # alongside vertical/rotated text for other fields in the SAME image.
    assert result["package_details"]["expiry_date"] is not None
    assert "2028" in result["package_details"]["expiry_date"]


# ============================================================
# 5. Text detected from multiple rotations: deduplicated,
#    highest confidence kept
# ============================================================


def test_same_text_detected_at_multiple_rotations_is_deduplicated():
    orig_h = orig_w = 100

    # Same physical text ("CROCIN 650"), located at the same spot on the
    # PACKAGE, picked up once at 0 degrees with low confidence and once
    # at 180 degrees with high confidence (e.g. PaddleOCR's own
    # use_angle_cls flipped it right-side-up at 180 too). The 180-degree
    # detection's bbox is expressed in the 180-rotated frame -- i.e. the
    # forward-rotated coordinates of the same physical corners -- exactly
    # as the real inner engine would report it.
    bbox_at_zero = [[10, 10], [90, 10], [90, 25], [10, 25]]
    bbox_at_180_frame = [
        [orig_w - 1 - x, orig_h - 1 - y] for x, y in bbox_at_zero
    ]

    low_conf_hit = [OCRResult("CROCIN 650", 0.55, bbox_at_zero)]
    high_conf_hit = [OCRResult("Crocin 650", 0.92, bbox_at_180_frame)]

    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([low_conf_hit, [], high_conf_hit, []])
    )

    image = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].confidence == pytest.approx(0.92)
    assert results[0].angle == 180  # the surviving (higher-confidence) detection


def test_deduplicate_ocr_results_directly_prefers_highest_confidence():
    results = [
        OCRResult("Dolo 650", 0.40, [[0, 0], [50, 0], [50, 20], [0, 20]], angle=0),
        OCRResult("DOLO 650", 0.85, [[0, 0], [50, 0], [50, 20], [0, 20]], angle=90),
        OCRResult("dolo   650!", 0.60, [[0, 0], [50, 0], [50, 20], [0, 20]], angle=180),
    ]

    deduped = deduplicate_ocr_results(results)

    assert len(deduped) == 1
    assert deduped[0].confidence == pytest.approx(0.85)
    assert deduped[0].angle == 90


def test_deduplicate_ocr_results_keeps_same_text_in_different_locations():
    """Two separate print occurrences of the same word must NOT collapse
    into one -- only overlapping bboxes count as duplicates."""
    results = [
        OCRResult("TABLET", 0.80, [[0, 0], [30, 0], [30, 10], [0, 10]]),
        OCRResult("TABLET", 0.75, [[200, 200], [230, 200], [230, 210], [200, 210]]),
    ]

    deduped = deduplicate_ocr_results(results)

    assert len(deduped) == 2


# ============================================================
# 6. Low-confidence OCR results
# ============================================================


def test_low_confidence_results_are_preserved_by_the_ocr_layer():
    """
    The OCR/rotation layer's job (item 3) is to hand the pipeline
    cleaner, more complete text -- filtering by confidence stays the
    pipeline's job (backend.perception.pipeline.filter_ocr_results,
    unchanged). So RotationAwareOCREngine must not silently drop a
    low-confidence detection itself.
    """
    faint_hit = [OCRResult("faint smudge", 0.12, [[0, 0], [20, 0], [20, 8], [0, 8]])]
    engine = RotationAwareOCREngine(FakeSequentialOCREngine([faint_hit, [], [], []]))

    image = np.zeros((50, 50, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].confidence == pytest.approx(0.12)

    # The existing pipeline-level confidence filter (unchanged) is what
    # actually screens this out downstream.
    from backend.perception.pipeline import filter_ocr_results

    filtered = filter_ocr_results(results)
    assert filtered == []


def test_one_rotation_failing_does_not_lose_the_others():
    good_hit = [OCRResult("METFORMIN", 0.90, [[0, 0], [40, 0], [40, 10], [0, 10]])]
    engine = RotationAwareOCREngine(
        FlakyOCREngine([[], [], [], good_hit], fail_on_call_index=1)
    )

    image = np.zeros((60, 60, 3), dtype=np.uint8)
    results = engine.recognize(image)

    assert len(results) == 1
    assert results[0].text == "METFORMIN"
    assert results[0].angle == 270


# ============================================================
# 7. Normal image where no rotation is required
# ============================================================


def test_no_rotation_needed_returns_exactly_one_clean_result():
    only_zero_hit = [OCRResult("IBUPROFEN 400MG", 0.95, [[5, 5], [90, 5], [90, 18], [5, 18]])]
    engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([only_zero_hit, [], [], []])
    )

    image = np.zeros((80, 160, 3), dtype=np.uint8)
    results = engine.recognize(image)

    # No duplicate noise from the other three rotations finding nothing.
    assert len(results) == 1
    assert results[0].text == "IBUPROFEN 400MG"
    assert results[0].angle == 0


# ============================================================
# 8. Existing expiry-date regex behavior continues to work unchanged
# ============================================================


def test_date_extractor_unaffected_by_the_new_angle_field():
    """
    OCRResult now carries an `angle` field (item 4), but the existing
    date-extraction regex/engine is duck-typed on `.text` / `.confidence`
    / `.bbox` only, and must keep behaving identically regardless of what
    angle produced a detection.
    """
    from backend.perception.date_extractor import extract_mfg_and_exp_dates

    # Angle-tagged items (as RotationAwareOCREngine now produces) mixed
    # with an un-tagged, default-angle item -- the date engine only
    # looks at .text/.confidence/.bbox, so the angle field must be
    # transparently ignored either way.
    ocr_items = [
        OCRResult("EXP: 12/2029", 0.92, [[0, 0], [60, 0], [60, 15], [0, 15]], angle=90),
        OCRResult("some unrelated vertical text", 0.85, [[0, 40], [60, 40], [60, 55], [0, 55]], angle=270),
    ]

    result = extract_mfg_and_exp_dates(ocr_items)

    assert result.exp_date is not None
    assert "2029" in result.exp_date

    # Same OCRResult, but with the default angle=0, must produce an
    # identical date result -- the new field has no effect on detection.
    ocr_items_no_angle = [
        OCRResult("EXP: 12/2029", 0.92, [[0, 0], [60, 0], [60, 15], [0, 15]]),
        OCRResult("some unrelated vertical text", 0.85, [[0, 40], [60, 40], [60, 55], [0, 55]]),
    ]
    result_no_angle = extract_mfg_and_exp_dates(ocr_items_no_angle)
    assert result_no_angle.exp_date == result.exp_date


def test_pipeline_expiry_regex_path_matches_plain_zero_angle_baseline():
    """Sanity check: a RotationAwareOCREngine that only ever finds
    anything at 0 degrees must produce the same expiry-date result as
    passing the same OCRResult straight through un-rotated -- the
    rotation wrapper must not alter outcomes for already-upright text."""
    plain_hit = OCRResult("PARACETAMOL EXP 03/2030", 0.9, [[0, 0], [80, 0], [80, 15], [0, 15]])

    baseline_engine = FakeSequentialOCREngine([[plain_hit]])
    rotation_engine = RotationAwareOCREngine(
        FakeSequentialOCREngine([[plain_hit], [], [], []])
    )

    baseline_result = recognize_medicine(IMAGE_PATH, ocr_engine=baseline_engine)
    rotation_result = recognize_medicine(IMAGE_PATH, ocr_engine=rotation_engine)

    assert (
        baseline_result["package_details"]["expiry_date"]
        == rotation_result["package_details"]["expiry_date"]
    )
    assert baseline_result["medicine_name"] == rotation_result["medicine_name"]


# ============================================================
# Bbox round-trip regression: verifies _map_bbox_to_original really is
# the geometric inverse of _rotate_image, using real cv2 rotation as
# ground truth (not just re-deriving the same formulas).
# ============================================================


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_bbox_mapping_is_the_true_inverse_of_rotation(angle):
    orig_h, orig_w = 40, 25
    orig_x, orig_y = 5, 30  # within bounds: x < orig_w, y < orig_h

    marker = np.zeros((orig_h, orig_w), dtype=np.uint8)
    marker[orig_y, orig_x] = 255

    rotated = _rotate_image(marker, angle)
    ys, xs = np.where(rotated == 255)
    assert len(xs) == 1
    rot_x, rot_y = int(xs[0]), int(ys[0])

    degenerate_bbox = [[rot_x, rot_y]] * 4
    mapped = _map_bbox_to_original(degenerate_bbox, angle, orig_h, orig_w)

    assert mapped[0][0] == pytest.approx(orig_x, abs=1)
    assert mapped[0][1] == pytest.approx(orig_y, abs=1)


# ============================================================
# PaddleOCR angle classification: verify it's enabled if the (optional)
# package is present, without requiring the real heavy install here.
# ============================================================


def test_paddleocr_engine_enables_angle_classification(monkeypatch):
    fake_paddleocr_module = types.ModuleType("paddleocr")
    mock_paddleocr_cls = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.ocr.return_value = []
    mock_paddleocr_cls.return_value = mock_engine_instance
    fake_paddleocr_module.PaddleOCR = mock_paddleocr_cls

    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr_module)

    from backend.perception.ocr import PaddleOCREngine

    ocr_engine = PaddleOCREngine(lang="en")

    # use_angle_cls=True is what enables PaddleOCR's built-in angle
    # classifier (item: "enable angle/orientation classification if
    # supported by the installed version").
    _, kwargs = mock_paddleocr_cls.call_args
    assert kwargs.get("use_angle_cls") is True

    image = np.zeros((10, 10, 3), dtype=np.uint8)
    ocr_engine.recognize(image)

    _, ocr_call_kwargs = mock_engine_instance.ocr.call_args
    assert ocr_call_kwargs.get("cls") is True
