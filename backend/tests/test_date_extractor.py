"""
Unit tests for the MedBox EXP date detection pipeline (backend/perception/date_extractor.py).

MedBox tracks expiry dates only: MFG/MFD/PKD dates are deliberately ignored, so
`mfg_date` is always None and must never leak into `exp_date`.
"""
import pytest
from backend.perception.date_extractor import (
    BoundingBox,
    DateExtractionResult,
    DateKeyword,
    ParsedDate,
    calculate_spatial_proximity,
    detect_keywords_in_text,
    extract_dates_from_text,
    extract_mfg_and_exp_dates,
    match_keywords_and_dates,
    normalize_ocr_text,
    validate_extracted_dates,
)
from backend.perception.medicine_info_extractor import (
    extract_expiry_date,
    extract_manufacturing_date,
    extract_medicine_details,
)
from backend.perception.ocr import OCRResult


# ==============================================================================
# 1. OCR TEXT NORMALIZATION
# ==============================================================================

def test_normalize_ocr_text_cleans_separators_and_spaces():
    raw = "EXP  :   05  /  2025"
    norm = normalize_ocr_text(raw)
    assert "EXP:" in norm
    assert "05/2025" in norm


def test_normalize_ocr_text_replaces_letter_o_in_date_tokens():
    raw = "MFG: O5/2O24   EXP: 12/2O26"
    norm = normalize_ocr_text(raw)
    assert "05/2024" in norm
    assert "12/2026" in norm


# ==============================================================================
# 2. KEYWORD DETECTION
# ==============================================================================

def test_detect_keywords_exact_matches():
    text = "EXPIRY DATE: 12/2025"
    kws = detect_keywords_in_text(text)
    categories = [k.category for k in kws]
    assert "EXP" in categories


def test_detect_keywords_various_pharmaceutical_variants():
    text = "USE BEFORE: 09/26"
    kws = detect_keywords_in_text(text)
    categories = [k.category for k in kws]
    assert "EXP" in categories


def test_detect_keywords_fuzzy_typo_correction():
    # EXF -> EXP (ratio >= 0.65 or edit distance <= 1)
    kws_exp = detect_keywords_in_text("EXF 08/2025")
    assert len(kws_exp) >= 1
    assert kws_exp[0].category == "EXP"
    assert kws_exp[0].match_quality < 1.0

    # EXB -> EXP (B <-> P typo)
    kws_exb = detect_keywords_in_text("EXB 11/2026")
    assert len(kws_exb) >= 1
    assert kws_exb[0].category == "EXP"


def test_ocr_label_normalization_and_mfg_separation():
    items = [
        OCRResult("MFG: 03/2024", 0.95, [[0, 0], [80, 0], [80, 20], [0, 20]]),
        OCRResult("EXF", 0.90, [[0, 30], [30, 30], [30, 50], [0, 50]]),
        OCRResult("12/2026", 0.92, [[40, 30], [100, 30], [100, 50], [40, 50]]),
    ]

    result = extract_mfg_and_exp_dates(items)

    assert result.exp_date == "12/2026"
    assert result.details["matched_keyword"] == "EXP"
    assert result.details["mfg_keyword_found"] is True
    assert result.mfg_date == "03/2024"


def test_detect_keywords_use_by():
    kws = detect_keywords_in_text("USE BY 12/2026")
    assert any(k.category == "EXP" for k in kws)


# ==============================================================================
# 3. REGEX DATE EXTRACTION
# ==============================================================================

@pytest.mark.parametrize(
    "text,expected_std",
    [
        ("EXP: 05/2026", "05/2026"),
        ("EXP: 05-2026", "05/2026"),
        ("EXP: 05.2026", "05/2026"),
        ("EXP: 11/24", "11/2024"),
        ("EXP: 15/08/2025", "15/08/2025"),
        ("EXP: MAY 2026", "05/2026"),
        ("EXP: MAY-2026", "05/2026"),
        ("EXP: MAY. 2026", "05/2026"),
        ("EXP: MAY/2026", "05/2026"),
        ("EXP: 15 MAY 2026", "15/05/2026"),
        ("EXP: MAY 15 2026", "15/05/2026"),
        ("EXP: OCT 25", "10/2025"),
        ("EXP: OCT '25", "10/2025"),
        ("EXP: JAN. 2025", "01/2025"),
        ("BEST BEFORE: JAN 2027", "01/2027"),
        ("USE BY 12/2026", "12/2026"),
        ("EXP: 05 / 2026", "05/2026"),
        ("EXP: 15 - 08 - 2025", "15/08/2025"),
        ("EXP: 2026/04", "04/2026"),
    ],
)
def test_extract_dates_standard_formats(text, expected_std):
    norm = normalize_ocr_text(text)
    dates = extract_dates_from_text(norm)
    assert len(dates) >= 1
    assert dates[0].standard_str == expected_std


def test_extract_dates_subspan_containment_filter():
    # 15/08/2025 should not simultaneously yield 08/2025
    dates = extract_dates_from_text("EXP: 15/08/2025")
    assert len(dates) == 1
    assert dates[0].standard_str == "15/08/2025"

    # MAY 15 2026 should yield 15/05/2026, not 05/2015
    dates_m15 = extract_dates_from_text("EXP: MAY 15 2026")
    assert len(dates_m15) == 1
    assert dates_m15[0].standard_str == "15/05/2026"


def test_extract_dates_discards_impossible_calendar_values():
    dates = extract_dates_from_text("BATCH NO: 99/99/9999")
    assert len(dates) == 0



# ==============================================================================
# 4. SPATIAL & PROXIMITY MATCHING
# ==============================================================================

def test_proximity_intra_box_matching():
    res = extract_mfg_and_exp_dates(["EXP: 12/2025"])
    assert res.exp_date == "12/2025"
    assert res.mfg_date is None
    assert res.is_valid is True
    assert res.overall_confidence >= 80.0
    assert res.needs_rescan is False


def test_spatial_proximity_horizontal_reading_order():
    # Box 1: "EXP DATE:" on left [x: 10..80, y: 100..130]
    box1 = BoundingBox.from_raw([[10, 100], [80, 100], [80, 130], [10, 130]])
    # Box 2: "11/2026" on right [x: 90..160, y: 100..130]
    box2 = BoundingBox.from_raw([[90, 100], [160, 100], [160, 130], [90, 130]])

    score, match_type = calculate_spatial_proximity(box1, box2)
    assert match_type == "horizontal_adjacent"
    assert score > 0.80


def test_spatial_proximity_vertical_column_order():
    # Box 1: "MFG DATE" on top [x: 10..100, y: 50..80]
    box1 = BoundingBox.from_raw([[10, 50], [100, 50], [100, 80], [10, 80]])
    # Box 2: "03/2023" directly below [x: 10..100, y: 90..120]
    box2 = BoundingBox.from_raw([[10, 90], [100, 90], [100, 120], [10, 120]])

    score, match_type = calculate_spatial_proximity(box1, box2)
    assert match_type == "vertical_stacked"
    assert score > 0.75


def test_spatial_proximity_with_ocr_results():
    ocr_items = [
        OCRResult(text="EXP:", confidence=0.98, bbox=[[10, 100], [70, 100], [70, 130], [10, 130]]),
        OCRResult(text="02/2026", confidence=0.95, bbox=[[80, 100], [150, 100], [150, 130], [80, 130]]),
    ]
    res = extract_mfg_and_exp_dates(ocr_items)
    assert res.exp_date == "02/2026"
    assert res.is_valid is True
    assert res.overall_confidence >= 80.0
    assert res.needs_rescan is False


# ==============================================================================
# 5. CONFIDENCE GATING (< 80%) & RESCAN
# ==============================================================================

def test_low_confidence_when_date_missing():
    res = extract_mfg_and_exp_dates(["PARACETAMOL 500MG TABLETS - TAKE WITH WATER"])
    assert res.overall_confidence < 80.0
    assert res.needs_rescan is True
    assert res.status == "Needs Rescan"


def test_low_confidence_when_ocr_confidence_is_poor():
    ocr_items = [
        OCRResult(text="EXP: 05/2026", confidence=0.35, bbox=[[0, 0], [100, 0], [100, 30], [0, 30]]),
    ]
    res = extract_mfg_and_exp_dates(ocr_items)
    # With poor OCR confidence, overall date score should fall below 80%
    assert res.overall_confidence < 80.0
    assert res.needs_rescan is True


# ==============================================================================
# 5b. MFG MUST NEVER BE REPORTED AS EXP (unanchored-fallback regression)
# ==============================================================================

@pytest.mark.parametrize(
    "lines",
    [
        ["BATCH A1", "05/2023", "05/2026"],   # MFG printed first, no keywords read
        ["05/2026", "05/2023"],               # reverse print order
        ["05/2023", "BATCH A1", "05/2026", "08/2024"],  # more than two candidates
        ["MFG: 05/2023", "XQZ 05/2026"],      # MFG labelled, EXP label unreadable
    ],
)
def test_unanchored_fallback_picks_latest_date_and_forces_rescan(lines):
    res = extract_mfg_and_exp_dates(lines)
    assert res.exp_date == "05/2026"          # latest date, never the first/MFG one
    assert res.mfg_date == ("05/2023" if any("MFG:" in line for line in lines) else None)
    assert res.overall_confidence < 80.0      # an unanchored guess can't clear the gate
    assert res.needs_rescan is True


def test_unanchored_fallback_confidence_cannot_reach_gate_even_with_perfect_ocr():
    ocr_items = [
        OCRResult(text="05/2023", confidence=1.0, bbox=[[0, 0], [60, 0], [60, 20], [0, 20]]),
        OCRResult(text="05/2026", confidence=1.0, bbox=[[70, 0], [130, 0], [130, 20], [70, 20]]),
    ]
    res = extract_mfg_and_exp_dates(ocr_items)
    assert res.exp_date == "05/2026"
    assert res.overall_confidence < 80.0
    assert res.needs_rescan is True


@pytest.mark.parametrize(
    "lines",
    [
        ["MFG: 05/2023", "EXP: 05/2026"],
        ["EXP: 05/2026", "MFG: 05/2023"],     # EXP printed before MFG
        ["MFG: 05/2023  EXP: 05/2026"],       # both on one line
    ],
)
def test_keyword_anchored_exp_wins_regardless_of_print_order(lines):
    res = extract_mfg_and_exp_dates(lines)
    assert res.exp_date == "05/2026"
    assert res.mfg_date == "05/2023"
    assert res.overall_confidence >= 80.0
    assert res.needs_rescan is False


def test_mfg_only_label_is_flagged_for_rescan_not_confirmed():
    res = extract_mfg_and_exp_dates(["MFG: 05/2023"])
    assert res.mfg_date == "05/2023"
    assert res.exp_date is None
    assert res.needs_rescan is True


# ==============================================================================
# 6. INTEGRATION WITH MEDICINE_INFO_EXTRACTOR
# ==============================================================================

def test_extract_medicine_details_backwards_compatible():
    raw_texts = [
        "PARACETAMOL 500mg",
        "BATCH NO: B12345",
        "EXP: 06/2026",
    ]
    details = extract_medicine_details(raw_texts)
    assert details.dosage == "500mg"
    assert details.batch_number == "B12345"
    assert details.manufacturing_date is None
    assert details.expiry_date == "06/2026"
    assert details.date_confidence >= 80.0
    assert details.date_needs_rescan is False


def test_multi_token_date_with_separate_mfg_box():
    # Simulates Tesseract image_to_data word-by-word output
    ocr_items = [
        OCRResult(text="EXP:", confidence=0.96, bbox=[[10, 50], [50, 50], [50, 70], [10, 70]]),
        OCRResult(text="MAY", confidence=0.95, bbox=[[60, 50], [100, 50], [100, 70], [60, 70]]),
        OCRResult(text="2026", confidence=0.95, bbox=[[110, 50], [160, 50], [160, 70], [110, 70]]),
    ]
    res = extract_mfg_and_exp_dates(ocr_items)
    assert res.mfg_date is None
    assert res.exp_date == "05/2026"
    assert res.is_valid is True
    assert res.overall_confidence >= 80.0
    assert res.needs_rescan is False


def test_medicine_info_extractor_fallbacks():
    assert extract_expiry_date("EXP: MAY 2026") == "05/2026"
    assert extract_expiry_date("EXP 05.2026") == "05/2026"
    assert extract_expiry_date("BEST BEFORE: JAN 2027") == "01/2027"
    assert extract_expiry_date("USE BY 12/2026") == "12/2026"
    assert extract_manufacturing_date("MFG: 05.2023") == "05/2023"
    assert extract_manufacturing_date("DOM: 10/2024") is None

