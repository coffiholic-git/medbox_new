import os

import cv2

from backend.perception.ocr import OCRResult
from backend.perception.pipeline import recognize_medicine

IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "medicine_images", "image.png"
)


class FakeOCREngine:
    def __init__(self, results):
        self._results = results

    def recognize(self, image):
        return self._results


def test_pipeline_recognizes_high_confidence_medicine():
    engine = FakeOCREngine([OCRResult("PARACETAMOL", 0.95, [])])

    result = recognize_medicine(IMAGE_PATH, ocr_engine=engine)

    assert result["recognized"] is True
    assert result["medicine_name"] == "Paracetamol"

    # 6.6 / FR10 / Section 13: even a high-confidence recognition
    # still requires explicit user confirmation before it can be
    # saved anywhere — the pipeline must never report that
    # confirmation isn't needed.
    assert result["needs_confirmation"] is True


def test_pipeline_requires_rescan_for_low_confidence_result():
    engine = FakeOCREngine([OCRResult("unknown text", 0.30, [])])

    result = recognize_medicine(IMAGE_PATH, ocr_engine=engine)

    assert result["recognized"] is False
    assert result["medicine_name"] is None
    assert result["needs_confirmation"] is True


def test_blurred_image_passes_through_ocr_pipeline(tmp_path):
    image = cv2.imread(IMAGE_PATH)
    blurred_path = tmp_path / "blurred.png"
    assert image is not None
    assert cv2.imwrite(str(blurred_path), cv2.GaussianBlur(image, (11, 11), 0))

    engine = FakeOCREngine([OCRResult("EXP 12/2027", 0.35, [])])
    result = recognize_medicine(str(blurred_path), ocr_engine=engine, scan_mode="expiry")

    assert result["package_details"]["expiry_date"] == "12/2027"
    assert result["package_details"]["date_needs_rescan"] is True


def test_pipeline_never_names_a_candidate_below_high_confidence():
    """
    6.6, Step 2: "If the score is low, MedBox does not read out a
    name at all — it says it isn't sure and asks the user to
    rescan." A candidate found internally by the matcher must never
    leak into the response below the high-confidence threshold.
    """
    engine = FakeOCREngine(
        [OCRResult("PARAC 500", 0.55, [])]
    )

    result = recognize_medicine(IMAGE_PATH, ocr_engine=engine)

    if result["confidence"] < 0.80:
        assert result["candidate_medicine"] is None
        assert result["medicine_info"] is None
        assert result["status"] == "Needs Rescan"


def test_pipeline_uses_both_engines_and_rewards_agreement():
    """
    6.1: "run through two OCR engines in parallel". When both
    engines see the same medicine name, confidence should reflect
    that agreement rather than relying on a single engine alone.
    """
    agreeing_primary = FakeOCREngine([OCRResult("PARACETAMOL 500MG", 0.9, [])])
    agreeing_secondary = FakeOCREngine([OCRResult("PARACETAMOL 500MG", 0.85, [])])

    agreeing_result = recognize_medicine(
        IMAGE_PATH,
        ocr_engine=agreeing_primary,
        secondary_ocr_engine=agreeing_secondary,
    )

    disagreeing_secondary = FakeOCREngine([OCRResult("SOMETHING ELSE ENTIRELY", 0.85, [])])

    disagreeing_result = recognize_medicine(
        IMAGE_PATH,
        ocr_engine=agreeing_primary,
        secondary_ocr_engine=disagreeing_secondary,
    )

    assert agreeing_result["engine_agreement"] is not None
    assert disagreeing_result["engine_agreement"] is not None
    assert agreeing_result["engine_agreement"] > disagreeing_result["engine_agreement"]
    assert agreeing_result["confidence"] >= disagreeing_result["confidence"]
