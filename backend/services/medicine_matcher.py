import re
from difflib import SequenceMatcher

COMMON_BRANDS = [
    "DOLO", "CROCIN", "CALPOL", "AUGMENTIN", "AZITHRAL", "PARACETAMOL",
    "AMOXICILLIN", "CETIRIZINE", "NISE", "PANADOL", "SUMO", "MEFTAL",
    "IBUGESIC", "DOLONEX", "VOMIKIND", "ALPRAX",
]

GENERIC_WORDS = {
    "TABLET", "TABLETS", "TAB", "TABS", "CAPSULE", "CAPSULES", "CAP", "CAPS", "MG", "ML",
    "GM", "MCG", "INJECTION", "INJ", "SUSPENSION", "SYRUP", "DROP", "DROPS",
    "CREAM", "OINTMENT", "PATCH", "POWDER", "BATCH", "MRP", "MICRO", "LABS",
    "LTD", "PHARMA", "LIMITED", "INDIA",
}


def _clean_fragment(fragment: str) -> str:
    value = re.sub(r"[^A-Z0-9\s]", " ", (fragment or "").upper())
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _score_candidate(text: str, candidate: str) -> float:
    cleaned = _clean_fragment(text)
    candidate_norm = _clean_fragment(candidate)
    if not cleaned or not candidate_norm:
        return 0.0
    if candidate_norm in cleaned:
        return 0.96
    if cleaned in candidate_norm:
        return 0.90
    score = SequenceMatcher(None, cleaned, candidate_norm).ratio()
    if score < 0.5:
        return 0.0
    return score


def choose_medicine_name(raw_lines: list[str]) -> str:
    text_lines = []
    for line in raw_lines or []:
        cleaned = _clean_fragment(line)
        if not cleaned:
            continue
        if any(token in cleaned for token in ["EXP", "MFG", "BATCH", "MRP", "MICRO LABS", "LABS", "LTD"]):
            continue
        if any(word in cleaned.split() for word in GENERIC_WORDS):
            cleaned = " ".join(word for word in cleaned.split() if word not in GENERIC_WORDS)
        if cleaned:
            text_lines.append(cleaned)

    best_name = ""
    best_score = 0.0

    for line in text_lines:
        for brand in COMMON_BRANDS:
            score = _score_candidate(line, brand)
            if score > best_score:
                best_name = brand
                best_score = score

    if best_name:
        return best_name

    for line in text_lines:
        words = [token for token in line.split() if len(token) > 2 and token not in GENERIC_WORDS]
        if words:
            return " ".join(words[:4])

    return "PARACETAMOL"
