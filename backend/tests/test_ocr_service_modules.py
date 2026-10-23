from backend.perception.ocr import OCRResult
from backend.services.date_detector import detect_expiry, detect_expiry_with_confidence, normalize_expiry_value
from backend.services.medicine_matcher import choose_medicine_name
from backend.services.text_normalizer import normalize_date_token, normalize_ocr_text


def test_normalize_ocr_text_repairs_common_ocr_issues():
    raw = "FE8 2O28 O0CT"
    value = normalize_ocr_text(raw)
    assert "FEB" in value
    assert "2028" in value
    assert "OCT" in value or "OCT" in value


def test_normalize_expiry_value_handles_month_year_formats():
    assert normalize_expiry_value("02/2028") == "FEB 2028"
    assert normalize_expiry_value("FEB 2028") == "FEB 2028"
    assert normalize_expiry_value("2028-02") == "FEB 2028"


def test_detect_expiry_prefers_expiry_keyword_over_mfg_keywords():
    result = detect_expiry([
        "MFG: 01/2024",
        "EXP: 02/2028",
    ])
    assert result == "FEB 2028"


def test_detect_expiry_never_uses_non_expiry_dates():
    for label in ("MFG", "Batch", "PKD", "MRP"):
        assert detect_expiry([f"{label}: 01/2024"]) is None


def test_detect_expiry_accepts_value_on_line_after_expiry_label():
    assert detect_expiry(["EXP", "02/2028"]) == "FEB 2028"


def test_detect_expiry_uses_expiry_value_when_multiple_labels_share_line():
    assert detect_expiry(["MFG 01/2024 EXP 02/2028 MRP 100"]) == "FEB 2028"


def test_expiry_label_variants_and_supported_date_formats():
    cases = [
        (["EXP NOV 2026"], "NOV 2026"),
        (["EXP. NOV 2026"], "NOV 2026"),
        (["EXP: NOV 2026"], "NOV 2026"),
        (["EXPIRY DATE", "11/2026"], "NOV 2026"),
        (["USE BY", "11-2026"], "NOV 2026"),
        (["BEST-BEFORE", "NOV-2026"], "NOV 2026"),
        (["EXP", "11/26"], "NOV 2026"),
        (["EXP", "15/11/2026"], "NOV 2026"),
        (["EXP", "2026-11"], "NOV 2026"),
    ]
    for lines, expected in cases:
        assert detect_expiry(lines) == expected


def test_fragmented_expiry_tokens_require_a_complete_date():
    assert detect_expiry(["EXP", "NOV", "2026"]) == "NOV 2026"
    assert detect_expiry(["EXP", "11", "2026"]) == "NOV 2026"
    assert detect_expiry(["EXP", "NOV"]) is None
    assert detect_expiry(["EXP"]) is None
    assert detect_expiry(["NOV"]) is None
    assert detect_expiry(["2026"]) is None


def test_fragmented_spatial_expiry_tokens_use_bboxes():
    detections = [
        OCRResult("EXP.", 0.96, [[10, 50], [45, 50], [45, 68], [10, 68]]),
        OCRResult("NOV", 0.94, [[49, 51], [82, 51], [82, 68], [49, 68]]),
        OCRResult("2026", 0.91, [[88, 51], [128, 51], [128, 68], [88, 68]]),
    ]
    assert detect_expiry(detections) == "NOV 2026"
    assert detect_expiry_with_confidence(detections) == ("NOV 2026", 91.0)


def test_spatial_expiry_does_not_take_manufacturing_date():
    detections = [
        OCRResult("MFG", 0.98, [[10, 10], [45, 10], [45, 25], [10, 25]]),
        OCRResult("DEC", 0.98, [[50, 10], [80, 10], [80, 25], [50, 25]]),
        OCRResult("2015", 0.98, [[85, 10], [125, 10], [125, 25], [85, 25]]),
        OCRResult("EXP.", 0.96, [[10, 60], [45, 60], [45, 75], [10, 75]]),
        OCRResult("NOV", 0.94, [[50, 60], [80, 60], [80, 75], [50, 75]]),
        OCRResult("2026", 0.91, [[85, 60], [125, 60], [125, 75], [85, 75]]),
    ]
    assert detect_expiry(detections) == "NOV 2026"


def test_expiry_never_uses_non_expiry_date_labels_or_invalid_dates():
    for label in ("MFG", "PKD", "BATCH", "MRP"):
        assert detect_expiry([f"{label} 11/2026"]) is None
    assert detect_expiry(["EXP", "13/2026"]) is None
    assert detect_expiry(["EXP", "31/02/2026"]) is None


def test_date_normalization_repairs_digits_without_corrupting_months_or_names():
    assert normalize_date_token("NOV 2026") == "NOV 2026"
    assert normalize_date_token("FEBRUARY 2O28") == "FEB 2028"
    assert normalize_date_token("O5/2O26") == "05 2026"
    assert normalize_date_token("I1/2O26") == "11 2026"
    assert normalize_ocr_text("CROCIN") == "CROCIN"
    assert detect_expiry(["EXP", "O5/2O26"]) == "MAY 2026"
    assert detect_expiry(["EXP", "I1/2O26"]) == "NOV 2026"


def test_split_expiry_label_phrases_are_recognized():
    assert detect_expiry(["USE", "BY", "NOV", "2026"]) == "NOV 2026"
    assert detect_expiry(["BEST", "BEFORE", "11", "2026"]) == "NOV 2026"


def test_choose_medicine_name_prefers_prominent_brand_name():
    choice = choose_medicine_name(["DOLO 650 TABLETS", "Micro Labs Ltd", "Batch 1234"])
    assert "DOLO" in choice.upper()
