import re


MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

OCR_FIXES = {
    "O": "0", "o": "0",
    "I": "1", "l": "1", "|": "1",
    "S": "5", "s": "5",
    "B": "8", "b": "8",
    "G": "6", "g": "6",
    "Z": "2", "z": "2",
}

_MONTH_NAMES = {
    "JANUARY": "JAN", "FEBRUARY": "FEB", "MARCH": "MAR", "APRIL": "APR",
    "MAY": "MAY", "JUNE": "JUN", "JULY": "JUL", "AUGUST": "AUG",
    "SEPTEMBER": "SEP", "OCTOBER": "OCT", "NOVEMBER": "NOV", "DECEMBER": "DEC",
}
_MONTH_ABBREVIATIONS = set(_MONTH_NAMES.values())
_DATE_DIGIT_FIXES = str.maketrans({
    "O": "0", "Q": "0", "I": "1", "L": "1", "|": "1",
    "S": "5", "B": "8", "G": "6", "Z": "2",
})


def _normalize_month_token(value: str) -> str:
    token = value.upper()
    token = token.replace("FE8", "FEB").replace("0CT", "OCT")
    token = token.replace("N0V", "NOV").replace("JU1", "JUL")
    token = token.replace("0", "O").replace("1", "I").replace("5", "S").replace("8", "B")
    return _MONTH_NAMES.get(token, token)


def _normalize_date_digits(value: str) -> str:
    return value.upper().translate(_DATE_DIGIT_FIXES)


def normalize_ocr_text(text: str) -> str:
    if not text:
        return ""

    cleaned = str(text).upper().strip()
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("EXPIRY DATE", "EXP")
    cleaned = cleaned.replace("EXP DATE", "EXP")
    cleaned = cleaned.replace("USE BY", "EXP")
    cleaned = cleaned.replace("BEST BEFORE", "EXP")
    cleaned = cleaned.replace("VALID UPTO", "EXP")
    cleaned = cleaned.replace("VALID TILL", "EXP")
    cleaned = cleaned.replace("EXPIRES", "EXP")
    cleaned = re.sub(r"(?i)MFG\.?", "MFG", cleaned)
    cleaned = re.sub(r"(?i)MFD\.?", "MFG", cleaned)
    cleaned = re.sub(r"(?i)PKD\.?", "PKD", cleaned)
    cleaned = re.sub(r"(?i)BATCH", "BATCH", cleaned)
    cleaned = re.sub(r"(?i)MICRO LABS LTD", "", cleaned)

    for old, new in {"FE8": "FEB", "2O28": "2028", "O0CT": "OCT", "0CT": "OCT", "FEBRUARY": "FEB"}.items():
        cleaned = cleaned.replace(old, new)

    cleaned = re.sub(r"(?i)\b2O(\d{2})\b", r"20\1", cleaned)
    cleaned = re.sub(r"(?i)\bO(\d{2})\b", r"0\1", cleaned)
    cleaned = re.sub(r"(?i)\bFE8\b", "FEB", cleaned)
    cleaned = re.sub(r"(?i)\b0CT\b", "OCT", cleaned)
    cleaned = re.sub(r"(?i)\bO0CT\b", "OCT", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_date_token(token: str) -> str:
    token = str(token or "").strip().upper()
    if not token:
        return token

    month_year = re.fullmatch(r"\s*([A-Z0-9]{3,9})([\s./-]+)([A-Z0-9]{2,4})\s*", token)
    if month_year:
        month = _normalize_month_token(month_year.group(1))
        year = _normalize_date_digits(month_year.group(3))
        if month in _MONTH_ABBREVIATIONS and year.isdigit():
            return f"{month} {year}"

    numeric_parts = re.fullmatch(r"([A-Z0-9]{1,4})([\s./-]+)([A-Z0-9]{1,4})(?:([\s./-]+)([A-Z0-9]{2,4}))?", token)
    if numeric_parts:
        parts = [numeric_parts.group(1), numeric_parts.group(3), numeric_parts.group(5)]
        normalized = [
            _normalize_date_digits(part) if part and any(char.isdigit() or char in "OQILSBGZ|" for char in part) else part
            for part in parts
        ]
        if all(not part or part.isdigit() for part in normalized):
            return " ".join(part for part in normalized if part)

    return token


def normalize_expiry_fragment(value: str) -> str:
    token = normalize_date_token(value)
    if not token:
        return ""
    token = token.upper()

    for month_name, month_num in MONTHS.items():
        if month_name in token:
            token = token.replace(month_name, month_name)
            return token

    match = re.search(r"(\d{1,2})\s*/?\s*(\d{2,4})", token)
    if match:
        month = int(match.group(1))
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year if int(year) < 50 else "19" + year
        if 1 <= month <= 12:
            month_name = next(name for name, num in MONTHS.items() if num == month)
            return f"{month_name} {year}"

    return token
