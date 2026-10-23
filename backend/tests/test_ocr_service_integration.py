"""
Integration coverage for the adapter in services/ocr_service.py that
actually wires the router up to backend/perception (as opposed to
test_recognition.py, which monkeypatches run_recognition entirely to
test the confirmation-loop logic in isolation).

These exercise the real pipeline against the sample image, so they
also double as a smoke test that backend/perception + its reference
data are actually reachable from inside the backend package.
"""
import os

from backend.services import ocr_service

# Resolved relative to this file, not the process's current working
# directory: open() always resolves a plain relative string against
# os.getcwd(), which only happens to equal the project root if pytest is
# invoked from there. Running `python -m pytest` from inside backend/ (a
# very natural place to run it from) made the old hardcoded
# "backend/data/medicine_images/image.png" resolve to a nonexistent
# backend/backend/... path and raise FileNotFoundError. This mirrors the
# CWD-independent pattern already used in test_perception_pipeline.py.
IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "medicine_images", "image.png"
)


def test_run_recognition_without_image_falls_back_to_simulated():
    result = ocr_service.run_recognition(None, file_name="whatever.jpg")

    assert result.simulated is True
    assert result.matched is not None
    assert 0.0 <= result.confidence <= 100.0


def test_run_recognition_with_real_image_runs_the_real_pipeline_or_degrades_gracefully():
    with open(IMAGE_PATH, "rb") as f:
        image_bytes = f.read()

    result = ocr_service.run_recognition(image_bytes, file_name="image.png")

    # Whether or not PaddleOCR happens to be installed in this
    # environment, the real path (simulated=False) must never crash —
    # it should either produce a real result or fall back cleanly.
    assert isinstance(result.confidence, float)
    assert isinstance(result.engines_agree, bool)
    if result.matched is not None:
        assert {"name", "strength", "form", "instructions"} <= result.matched.keys()


def test_medicine_confidence_does_not_become_expiry_confidence(monkeypatch):
    import cv2
    import numpy as np

    monkeypatch.setattr(
        ocr_service,
        "extract_clean_medicine_and_expiry",
        lambda image: {
            "medicine_name": "CROCIN",
            "expiry_date": None,
            "confidence": 0.92,
            "medicine_confidence": 0.92,
            "date_confidence": 0.0,
            "date_needs_rescan": True,
            "status": "needs_confirmation",
            "raw_ocr_results": [],
        },
    )
    success, encoded = cv2.imencode(".png", np.zeros((20, 20, 3), dtype=np.uint8))
    assert success

    result = ocr_service.run_recognition(encoded.tobytes(), file_name="package.png")

    assert result.matched["name"] == "CROCIN"
    assert result.confidence == 92.0
    assert result.exp_date is None
    assert result.date_confidence == 0.0
    assert result.date_needs_rescan is True


def test_unreadable_real_image_does_not_use_demo_fallback():
    result = ocr_service.run_recognition(b"not an image", file_name="broken.jpg")

    assert result.simulated is False
    assert result.matched is None
    assert result.exp_date is None
    assert result.confidence == 0.0
    assert result.date_confidence == 0.0
    assert result.date_needs_rescan is True
