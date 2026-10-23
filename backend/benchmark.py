import argparse
import csv
import json
import re
import time
from pathlib import Path

from backend.services import ocr_service
from backend.services.date_detector import normalize_expiry_value

BACKEND_DIR = Path(__file__).resolve().parent
DATASET_DIR = BACKEND_DIR / "datasets" / "expiry_kaggle"
IMAGE_DIR = DATASET_DIR / "images"
RESULTS_PATH = BACKEND_DIR / "benchmark_results.csv"
FAILURES_PATH = BACKEND_DIR / "benchmark_failures.csv"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABEL_COLUMN_ALIASES = {
    "image_name": ("image_name", "filename", "file_name", "image"),
    "expected_medicine": ("expected_medicine", "medicine_name", "medicine", "drug_name"),
    "expected_expiry": ("expected_expiry", "expiry_date", "expiry", "expiration_date"),
}


def _normalize_medicine(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _normalize_expiry(value: str | None) -> str:
    return normalize_expiry_value(value or "").casefold().strip()


def _find_column(fieldnames: list[str] | None, aliases: tuple[str, ...]) -> str | None:
    columns = {name.strip().casefold(): name for name in (fieldnames or []) if name}
    return next((columns[alias] for alias in aliases if alias in columns), None)


def _load_labels(labels_path: Path) -> dict[str, dict[str, str]]:
    with labels_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = {
            field: _find_column(reader.fieldnames, aliases)
            for field, aliases in LABEL_COLUMN_ALIASES.items()
        }
        missing = [field for field, column in columns.items() if column is None]
        if missing:
            raise ValueError(
                f"Ground-truth CSV must provide columns for: {', '.join(missing)}. "
                "Expected image_name, expected_medicine, expected_expiry."
            )

        labels = {}
        for row in reader:
            image_name = (row.get(columns["image_name"]) or "").strip()
            if not image_name:
                continue
            labels[image_name.replace("\\", "/")] = {
                "medicine": (row.get(columns["expected_medicine"]) or "").strip(),
                "expiry": (row.get(columns["expected_expiry"]) or "").strip(),
            }
        return labels


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def benchmark_dataset(
    image_dir: str | Path = IMAGE_DIR,
    labels_path: str | Path | None = None,
) -> dict:
    image_dir = Path(image_dir)
    if not image_dir.is_dir():
        raise FileNotFoundError(f"Benchmark image directory not found: {image_dir}")

    dataset_dir = image_dir.parent
    if labels_path is None:
        candidates = [dataset_dir / "ground_truth.csv", dataset_dir / "annotations.csv"]
        labels_path = next((path for path in candidates if path.is_file()), None)
    if labels_path is None or not Path(labels_path).is_file():
        raise FileNotFoundError(
            f"Ground-truth CSV not found under {dataset_dir}. Add ground_truth.csv or "
            "annotations.csv with image_name, expected_medicine, expected_expiry columns."
        )

    labels = _load_labels(Path(labels_path))
    images = sorted(
        (path for path in image_dir.rglob("*") if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS),
        key=lambda path: path.as_posix().casefold(),
    )
    if not images:
        raise ValueError(f"No supported images found in {image_dir}")

    summary = {
        "total_images": 0,
        "correct_medicine": 0,
        "correct_expiry": 0,
        "medicine_accuracy": 0.0,
        "expiry_accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "F1_score": 0.0,
        "average_scan_time": 0.0,
    }
    failures = []
    total_elapsed = 0.0
    true_positive = false_positive = false_negative = 0

    for image_path in images:
        relative_name = image_path.relative_to(image_dir).as_posix()
        truth = labels.get(relative_name) or labels.get(image_path.name)
        if truth is None:
            raise ValueError(f"Ground truth missing for image: {relative_name}")
        if not truth["medicine"] or not truth["expiry"]:
            raise ValueError(f"Ground-truth medicine or expiry is empty for image: {relative_name}")

        started = time.perf_counter()
        result = ocr_service.run_recognition(image_path.read_bytes(), file_name=image_path.name, scan_mode="both")
        elapsed = time.perf_counter() - started
        total_elapsed += elapsed

        predicted_medicine = result.matched.get("name") if result.matched else None
        predicted_expiry = result.exp_date
        confidence = float(result.confidence or 0.0)
        status = (
            "low_confidence"
            if confidence < ocr_service.CONFIDENCE_THRESHOLD or not result.matched
            else "pending_confirmation"
        )

        medicine_correct = _normalize_medicine(predicted_medicine) == _normalize_medicine(truth["medicine"])
        expiry_correct = _normalize_expiry(predicted_expiry) == _normalize_expiry(truth["expiry"])
        summary["total_images"] += 1
        summary["correct_medicine"] += int(medicine_correct)
        summary["correct_expiry"] += int(expiry_correct)

        for predicted, expected, correct in (
            (predicted_medicine, truth["medicine"], medicine_correct),
            (predicted_expiry, truth["expiry"], expiry_correct),
        ):
            if correct:
                true_positive += 1
            else:
                false_negative += 1
                if predicted:
                    false_positive += 1

        reasons = []
        if not medicine_correct:
            reasons.append("medicine mismatch" if predicted_medicine else "medicine not detected")
        if not expiry_correct:
            reasons.append("expiry mismatch" if predicted_expiry else "expiry not detected")
        if reasons:
            failures.append({
                "image_name": relative_name,
                "predicted_medicine": predicted_medicine or "",
                "expected_medicine": truth["medicine"],
                "predicted_expiry": predicted_expiry or "",
                "expected_expiry": truth["expiry"],
                "reason_for_failure": "; ".join(reasons),
            })

        print(json.dumps({
            "image_name": relative_name,
            "medicine_name": predicted_medicine,
            "expiry_date": predicted_expiry,
            "confidence": confidence,
            "status": status,
        }, ensure_ascii=True))

    total = summary["total_images"]
    summary["medicine_accuracy"] = summary["correct_medicine"] / total
    summary["expiry_accuracy"] = summary["correct_expiry"] / total
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    summary["precision"] = precision
    summary["recall"] = recall
    summary["F1_score"] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    summary["average_scan_time"] = total_elapsed / total

    _write_csv(RESULTS_PATH, list(summary), [summary])
    _write_csv(
        FAILURES_PATH,
        ["image_name", "predicted_medicine", "expected_medicine", "predicted_expiry", "expected_expiry", "reason_for_failure"],
        failures,
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark the upload OCR service against labeled package images.")
    parser.add_argument("--images", type=Path, default=IMAGE_DIR)
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark_dataset(args.images, args.labels), indent=2))