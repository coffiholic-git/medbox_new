from backend.perception.medicine_matcher import (
    MEDICINES,
    find_best_medicine_match,
    normalize_text,
)


def test_normalize_text_removes_extra_symbols():
    assert normalize_text(" Para-cetamol 500mg! ") == "para cetamol 500mg"


def test_find_best_medicine_match_finds_known_name_in_ocr_text():
    match = find_best_medicine_match(["PARACETAMOL 500"])

    assert match.medicine_key == "paracetamol"
    assert match.score >= 0.9


def test_medicine_database_is_not_limited_to_a_single_entry():
    """
    6.1: OCR text is "fuzzy-matched against the medicine database".
    The matcher previously only knew about a single hardcoded
    medicine (Paracetamol), so scanning anything else could never
    be recognized regardless of OCR quality. It should now load the
    full shared reference dataset (backend/data/medicine_reference.json).
    """
    assert len(MEDICINES) > 1


def test_find_best_medicine_match_recognizes_a_medicine_other_than_paracetamol():
    match = find_best_medicine_match(["AMOXICILLIN 500 MG"])

    assert match.medicine_key == "amoxicillin"
    assert match.score >= 0.8
