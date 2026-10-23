import csv
import json
from pathlib import Path
import tempfile

from backend.services.ocr_service import run_recognition

BACKEND_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BACKEND_DIR / "datasets" / "expiry_kaggle" / "images"
OUTPUT_PATH = BACKEND_DIR / "datasets" / "expiry_kaggle" / "ground_truth.csv"
RAW_DEBUG_PATH = Path(tempfile.gettempdir()) / "medbox_expiry_ocr_raw.jsonl"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CSV_COLUMNS = ["image_name", "expected_medicine", "expected_expiry"]


def generate_ground_truth() -> int:
    if not IMAGES_DIR.is_dir():
        raise FileNotFoundError(f"Image directory not found: {IMAGES_DIR}")

    image_paths = sorted(
        (
            path
            for path in IMAGES_DIR.rglob("*")
            if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
        ),
        key=lambda path: path.as_posix().casefold(),
    )
    if not image_paths:
        raise ValueError(f"No supported image files found in {IMAGES_DIR}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as output, RAW_DEBUG_PATH.open(
        "w", encoding="utf-8"
    ) as raw_debug:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for index, image_path in enumerate(image_paths, start=1):
            result = run_recognition(
                image_path.read_bytes(),
                file_name=image_path.name,
                scan_mode="both",
            )
            writer.writerow({
                "image_name": image_path.relative_to(IMAGES_DIR).as_posix(),
                "expected_medicine": result.matched.get("name", "") if result.matched else "",
                "expected_expiry": result.exp_date or "",
            })
            raw_debug.write(json.dumps({
                "image_name": image_path.relative_to(IMAGES_DIR).as_posix(),
                "ocr_results": result.debug_ocr_results or [],
            }, ensure_ascii=True) + "\n")
            if index % 25 == 0 or index == len(image_paths):
                print(f"Processed {index}/{len(image_paths)} images")

    print(f"Wrote {len(image_paths)} OCR-derived labels to {OUTPUT_PATH}")
    print(f"Saved temporary raw OCR data to {RAW_DEBUG_PATH}")
    return len(image_paths)


if __name__ == "__main__":
    generate_ground_truth()