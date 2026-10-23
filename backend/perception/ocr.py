import logging
import inspect
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
try:
    import pytesseract
except ImportError:  # Keep the API/demo fallback usable without local OCR extras.
    pytesseract = None

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: list[Any]
    # Rotation (degrees: 0/90/180/270) of the image this detection came
    # from, relative to the original upright frame. Defaults to 0 so every
    # existing call site that builds an OCRResult with 3 positional/keyword
    # args (text, confidence, bbox) keeps working unchanged. Only
    # RotationAwareOCREngine (below) ever sets this to something other
    # than 0 -- it's how "orientation information" (item 4) survives the
    # rotation fallback and reaches the rest of the pipeline.
    angle: int = 0


def parse_paddleocr_results(raw_results: Any) -> list[OCRResult]:
    """Convert PaddleOCR output into the common OCRResult format."""

    results: list[OCRResult] = []

    # Newer PaddleOCR result format
    if isinstance(raw_results, dict):
        data = raw_results.get("res", raw_results)

        if isinstance(data, dict):
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_polys") or data.get("rec_boxes") or []

            if isinstance(texts, list) and isinstance(scores, list):
                for i, text in enumerate(texts):
                    text = str(text).strip()

                    if not text:
                        continue

                    try:
                        confidence = float(scores[i])
                    except (ValueError, TypeError, IndexError):
                        confidence = 0.0

                    bbox = boxes[i] if i < len(boxes) else []

                    results.append(
                        OCRResult(
                            text=text,
                            confidence=confidence,
                            bbox=bbox,
                        )
                    )

        return [
            result
            for result in results
            if result.text
        ]

    # Older PaddleOCR list format
    if isinstance(raw_results, list):
        for item in raw_results:
            results.extend(
                _parse_paddle_item(item)
            )

    return [
        result
        for result in results
        if result.text
    ]


def _parse_paddle_item(
    item: Any,
) -> list[OCRResult]:
    """Parse one item from the older PaddleOCR result format."""

    if not isinstance(item, list):
        return []

    # One OCR result:
    # [bbox, [text, confidence]]
    if (
        len(item) == 2
        and isinstance(item[1], (list, tuple))
        and len(item[1]) == 2
    ):
        bbox, text_score = item
        text, confidence = text_score

        return [
            OCRResult(
                text=str(text).strip(),
                confidence=float(confidence),
                bbox=bbox,
            )
        ]

    results: list[OCRResult] = []

    for child in item:
        results.extend(
            _parse_paddle_item(child)
        )

    return results


class PaddleOCREngine:
    """
    Primary OCR engine for MedBox (6.1 / 10 — Technology Stack).

    This was previously missing entirely: the pipeline only ever
    ran Tesseract, even though PaddleOCR is the documented primary
    engine and `paddleocr`/`paddlepaddle` are already listed in
    requirements.txt. `parse_paddleocr_results` existed and was
    unit-tested, but nothing in the codebase ever called it.

    PaddleOCR itself is imported lazily so importing this module
    doesn't require the (large) paddleocr/paddlepaddle install
    unless this engine is actually used.
    """

    def __init__(self, lang: str = "en") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError(
                "paddleocr is not installed. Install it with "
                "`pip install paddleocr paddlepaddle` to use "
                "PaddleOCREngine, or pass a different ocr_engine "
                "to recognize_medicine()."
            ) from exc

        parameters = inspect.signature(PaddleOCR).parameters
        if "use_textline_orientation" in parameters:
            self._uses_predict_api = True
            self._engine = PaddleOCR(
                lang=lang,
                use_textline_orientation=True,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
        else:
            self._uses_predict_api = False
            self._engine = PaddleOCR(
                use_angle_cls=True,
                lang=lang,
                show_log=False,
            )

    def recognize(self, image: np.ndarray) -> list[OCRResult]:
        """Run PaddleOCR and adapt v2 or v3 results to OCRResult objects."""
        if self._uses_predict_api:
            raw_results = self._engine.predict(image)
        else:
            raw_results = self._engine.ocr(image, cls=True)

        if not isinstance(raw_results, (list, tuple)):
            raw_results = [raw_results]

        results = []
        for page in raw_results:
            payload = getattr(page, "json", page)
            if callable(payload):
                payload = payload()
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            results.extend(parse_paddleocr_results(payload))
        return results


class TesseractOCREngine:
    """
    OCR engine using Tesseract for MedBox.

    Per 10 (Technology Stack) and Layer 3 (Docker + docker-compose),
    this must run on Linux in CI/containers as well as on a
    developer's machine, so the tesseract binary is located
    cross-platform instead of a single hardcoded Windows path:

    1. ``TESSERACT_CMD`` environment variable, if set (explicit
       override for unusual installs).
    2. Whatever ``tesseract`` resolves to on the system PATH
       (this is what the Docker image and most Linux/macOS
       installs provide).
    3. The common Windows install location, purely as a last
       resort for local development.
    """

    def __init__(self) -> None:
        if pytesseract is None:
            raise ImportError(
                "pytesseract is not installed. Install the backend requirements "
                "to use TesseractOCREngine."
            )
        tesseract_cmd = (
            os.environ.get("TESSERACT_CMD")
            or shutil.which("tesseract")
        )

        if not tesseract_cmd:
            windows_default = Path(
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )
            if windows_default.exists():
                tesseract_cmd = str(windows_default)

        if not tesseract_cmd:
            raise FileNotFoundError(
                "Tesseract binary was not found. Install it "
                "(e.g. `apt-get install tesseract-ocr` in the "
                "Docker image) or set the TESSERACT_CMD "
                "environment variable to its path."
            )

        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def recognize(
        self,
        image: np.ndarray,
    ) -> list[OCRResult]:
        """Run Tesseract OCR on a prepared OpenCV image."""

        # Enlarge the image moderately (1.5x) to aid small medicine text without
        # blowing up pixel area 9x (which makes Tesseract crawl).
        image = cv2.resize(
            image,
            None,
            fx=1.5,
            fy=1.5,
            interpolation=cv2.INTER_LINEAR,
        )

        # Convert to grayscale only if the image is still in color.
        if len(image.shape) == 3:
            gray = cv2.cvtColor(
                image,
                cv2.COLOR_BGR2GRAY,
            )
        else:
            gray = image

        # Reduce small image noise.
        gray = cv2.GaussianBlur(
            gray,
            (3, 3),
            0,
        )

        # Improve contrast for metallic medicine strips using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)

        thresholded = cv2.adaptiveThreshold(
            contrast_enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

        def _extract_from_img(target_img: np.ndarray, psm_mode: int = 11) -> list[OCRResult]:
            try:
                data = pytesseract.image_to_data(
                    target_img,
                    config=f"--psm {psm_mode}",
                    output_type=pytesseract.Output.DICT,
                )
            except Exception:
                return []

            items: list[OCRResult] = []
            for i, text in enumerate(data.get("text", [])):
                text = str(text).strip()
                if not text:
                    continue

                try:
                    raw_conf = float(data.get("conf", [])[i])
                    # Tesseract outputs -1 for non-dictionary words and for digit-only /
                    # date tokens (e.g. "05/2026", "EXP", "MFG").  These are typically
                    # very reliably recognised; a flat 0.80 is more accurate than 0.75
                    # and keeps them well above the MIN_OCR_CONFIDENCE = 0.30 floor.
                    confidence = 0.80 if raw_conf < 0 else raw_conf / 100.0
                except (ValueError, TypeError, IndexError):
                    confidence = 0.55

                if confidence < 0.15:
                    continue

                x = int(data["left"][i])
                y = int(data["top"][i])
                width = int(data["width"][i])
                height = int(data["height"][i])

                bbox = [
                    [x, y],
                    [x + width, y],
                    [x + width, y + height],
                    [x, y + height],
                ]

                items.append(
                    OCRResult(
                        text=text,
                        confidence=confidence,
                        bbox=bbox,
                    )
                )
            return items

        # Fast tri-pass recognition:
        # Pass 1: Contrast-enhanced grayscale with PSM 6 (uniform block) — best for
        #         structured label rows (name, dosage, MFG/EXP lines).
        # Pass 2: Contrast-enhanced grayscale with PSM 11 (sparse text) — catches
        #         embossed or foil-stamped dates scattered across the image.
        # Pass 3: Adaptive thresholded binary with PSM 6 — optimal for high-contrast
        #         printed text on white/light backgrounds.
        pass1_results = _extract_from_img(contrast_enhanced, psm_mode=6)
        pass2_results = _extract_from_img(contrast_enhanced, psm_mode=11)
        pass3_results = _extract_from_img(thresholded, psm_mode=6)

        def _merge_results(base: list[OCRResult], new_results: list[OCRResult]) -> list[OCRResult]:
            """Merge new_results into base, deduplicating by IoU overlap."""
            merged = list(base)
            for r1 in new_results:
                b1 = r1.bbox
                if not b1 or len(b1) < 4:
                    merged.append(r1)
                    continue

                x1_min, y1_min = b1[0][0], b1[0][1]
                x1_max, y1_max = b1[2][0], b1[2][1]
                area1 = max(1.0, (x1_max - x1_min) * (y1_max - y1_min))

                overlapping_idx = None
                for idx, r2 in enumerate(merged):
                    b2 = r2.bbox
                    if not b2 or len(b2) < 4:
                        continue

                    x2_min, y2_min = b2[0][0], b2[0][1]
                    x2_max, y2_max = b2[2][0], b2[2][1]
                    area2 = max(1.0, (x2_max - x2_min) * (y2_max - y2_min))

                    ix_min = max(x1_min, x2_min)
                    iy_min = max(y1_min, y2_min)
                    ix_max = min(x1_max, x2_max)
                    iy_max = min(y1_max, y2_max)

                    if ix_max > ix_min and iy_max > iy_min:
                        inter = (ix_max - ix_min) * (iy_max - iy_min)
                        iou = inter / (area1 + area2 - inter)
                        if iou > 0.40:
                            overlapping_idx = idx
                            break

                if overlapping_idx is not None:
                    if r1.confidence > merged[overlapping_idx].confidence:
                        merged[overlapping_idx] = r1
                else:
                    merged.append(r1)
            return merged

        # Merge all three passes: start from pass3 (thresholded PSM6) as base,
        # then add pass1 (enhanced PSM6) and pass2 (enhanced PSM11).
        merged_results = _merge_results(pass3_results, pass1_results)
        merged_results = _merge_results(merged_results, pass2_results)

        merged_results.sort(
            key=lambda r: (
                r.bbox[0][1] if r.bbox and len(r.bbox) >= 1 else 0,
                r.bbox[0][0] if r.bbox and len(r.bbox) >= 1 else 0,
            )
        )
        return merged_results


# ============================================================
# ROTATION-AWARE OCR (0deg / 90deg / 180deg / 270deg fallback)
# ============================================================
#
# PaddleOCR's own `use_angle_cls` (already enabled in PaddleOCREngine
# above) only classifies and corrects a detected text LINE's reading
# direction between 0 and 180 degrees. It does not help the detector
# find text that is printed sideways (90/270 degrees) relative to the
# frame, and it says nothing about TesseractOCREngine, which has no
# orientation awareness of its own at all. A single medicine package
# photo can legitimately contain a vertical medicine name, a horizontal
# expiry date, and a batch number rotated some other way, all at once
# -- so no single whole-image rotation "fixes" the picture.
#
# RotationAwareOCREngine below is a thin decorator around any existing
# OCREngine (PaddleOCREngine, TesseractOCREngine, or a test fake): it
# reruns the wrapped engine on the image rotated to each of 0/90/180/270
# degrees, maps every detected bounding box back into the ORIGINAL
# image's coordinate space, tags each result with the rotation angle
# that produced it, and deduplicates detections of the same physical
# text across rotations, keeping the highest-confidence version.

ROTATION_ANGLES: tuple[int, ...] = (0, 90, 180, 270)


def _rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    """Rotate ``image`` clockwise by ``angle`` degrees (0/90/180/270)."""

    if angle == 0:
        return image
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Unsupported rotation angle: {angle}")


def _map_point_to_original(
    x: float,
    y: float,
    angle: int,
    orig_h: int,
    orig_w: int,
) -> tuple[float, float]:
    """
    Map a point (x, y) detected on the image rotated by ``angle`` degrees
    (via `_rotate_image`) back into the coordinate space of the original,
    unrotated image (whose size is orig_h x orig_w).

    These are the algebraic inverses of `_rotate_image`'s transforms,
    derived from how cv2.rotate remaps pixel coordinates:

      * 90deg  CW forward:  x' = orig_h - 1 - y,  y' = x
                 -> inverse: x  = y',              y  = orig_h - 1 - x'
      * 180deg forward:     x' = orig_w - 1 - x,  y' = orig_h - 1 - y
                 -> inverse: x  = orig_w - 1 - x', y  = orig_h - 1 - y'
      * 270deg CW forward:  x' = y,                y' = orig_w - 1 - x
                 -> inverse: x  = orig_w - 1 - y',  y  = x'
    """

    if angle == 0:
        return x, y
    if angle == 90:
        return y, orig_h - 1 - x
    if angle == 180:
        return orig_w - 1 - x, orig_h - 1 - y
    if angle == 270:
        return orig_w - 1 - y, x
    raise ValueError(f"Unsupported rotation angle: {angle}")


def _map_bbox_to_original(
    bbox: Any,
    angle: int,
    orig_h: int,
    orig_w: int,
) -> Any:
    """
    Re-project a bounding box detected on a rotated frame back into the
    original image's coordinate space (item 4: bounding boxes must be
    preserved/meaningful, not left in a rotated frame's coordinates).

    Handles the two bbox shapes this codebase's OCR engines produce:
      * a 4-point polygon: [[x, y], [x, y], [x, y], [x, y]]
      * a flat rectangle:  [x, y, w, h]

    Any other shape (or an empty/missing bbox) is returned unchanged --
    a detection's text/confidence is never discarded just because its
    bbox couldn't be confidently re-projected.
    """

    if not bbox or angle == 0:
        return bbox

    try:
        # 4-point polygon: [[x, y], [x, y], [x, y], [x, y]]
        if (
            isinstance(bbox, (list, tuple))
            and len(bbox) == 4
            and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in bbox)
        ):
            return [
                list(
                    _map_point_to_original(
                        float(p[0]), float(p[1]), angle, orig_h, orig_w
                    )
                )
                for p in bbox
            ]

        # Flat rectangle: [x, y, w, h]
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(
            isinstance(v, (int, float)) for v in bbox
        ):
            x, y, w, h = (float(v) for v in bbox)
            corners = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            return [
                list(
                    _map_point_to_original(
                        px, py, angle, orig_h, orig_w
                    )
                )
                for px, py in corners
            ]
    except (TypeError, ValueError, IndexError):
        pass

    return bbox


def _normalize_for_dedup(text: str) -> str:
    """
    Collapse OCR text down to just its upper-cased alphanumerics, so
    that formatting noise between two detections of the same physical
    text (spacing, punctuation, case -- e.g. "Exp: 05/2026" from one
    rotation vs "EXP 05 2026" from another) doesn't defeat
    deduplication.
    """
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _is_date_or_label_text(text: str) -> bool:
    """Keep rotating when an upright pass only found date metadata."""

    normalized = (text or "").upper()
    return bool(
        re.search(r"\b(?:EXP|MFG|LOT|BATCH|PKD)\b", normalized)
        or re.search(r"\b\d{1,2}[/-]\d{2,4}\b", normalized)
    )


def _bbox_extent(bbox: Any) -> tuple[float, float, float, float] | None:
    """Axis-aligned (min_x, min_y, max_x, max_y) extent of a point-list
    bbox, or None if ``bbox`` isn't in a recognizable shape."""

    if not bbox:
        return None
    try:
        xs = [float(point[0]) for point in bbox]
        ys = [float(point[1]) for point in bbox]
    except (TypeError, ValueError, IndexError):
        return None
    if len(xs) < 2 or len(ys) < 2:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_iou(bbox_a: Any, bbox_b: Any) -> float:
    """Intersection-over-union of two point-list bboxes; 0.0 if either
    bbox can't be interpreted or they don't overlap."""

    extent_a = _bbox_extent(bbox_a)
    extent_b = _bbox_extent(bbox_b)
    if extent_a is None or extent_b is None:
        return 0.0

    ax_min, ay_min, ax_max, ay_max = extent_a
    bx_min, by_min, bx_max, by_max = extent_b

    area_a = max(1.0, (ax_max - ax_min) * (ay_max - ay_min))
    area_b = max(1.0, (bx_max - bx_min) * (by_max - by_min))

    ix_min, iy_min = max(ax_min, bx_min), max(ay_min, by_min)
    ix_max, iy_max = min(ax_max, bx_max), min(ay_max, by_max)

    if ix_max <= ix_min or iy_max <= iy_min:
        return 0.0

    intersection = (ix_max - ix_min) * (iy_max - iy_min)
    return intersection / (area_a + area_b - intersection)


def deduplicate_ocr_results(
    results: list[OCRResult],
    iou_threshold: float = 0.45,
) -> list[OCRResult]:
    """
    Merge OCR detections that represent the same physical text -- e.g.
    the same word picked up at more than one rotation -- keeping the
    highest-confidence version of each (items 5 and 6).

    Two detections are treated as duplicates when:
      1. They normalize (see `_normalize_for_dedup`) to the same text,
         AND
      2. Whenever BOTH carry a usable bounding box, those boxes overlap
         by at least ``iou_threshold`` (IoU). If either side's bbox is
         missing or in an unrecognized shape, matching text alone is
         treated as sufficient -- a real duplicate should never survive
         just because bbox geometry wasn't available (e.g. plain test
         fakes that pass ``bbox=[]``).

    Input order is otherwise preserved: the first time a given piece of
    text is seen, its position in the output is fixed; later duplicates
    only ever update that entry's confidence/bbox/angle (when the new
    detection is more confident), never its position.
    """

    deduped: list[OCRResult] = []

    for result in results:
        text = (result.text or "").strip()
        if not text:
            continue

        normalized = _normalize_for_dedup(text)
        if not normalized:
            # Punctuation/symbol-only OCR noise: nothing meaningful to
            # dedupe on, so just pass it through as-is.
            deduped.append(result)
            continue

        match_index = None
        for index, existing in enumerate(deduped):
            if _normalize_for_dedup(existing.text) != normalized:
                continue
            if result.bbox and existing.bbox:
                if _bbox_iou(result.bbox, existing.bbox) < iou_threshold:
                    # Same text, but in two clearly different places on
                    # the package (e.g. printed twice) -- keep both.
                    continue
            match_index = index
            break

        if match_index is None:
            deduped.append(result)
        elif result.confidence > deduped[match_index].confidence:
            # Prefer the highest-confidence detection (item 6).
            deduped[match_index] = result

    return deduped


class RotationAwareOCREngine:
    """
    Decorator around another OCR engine (PaddleOCREngine, TesseractOCREngine,
    or any test fake implementing ``recognize(image) -> list[OCRResult]``)
    that makes OCR robust to per-region orientation.

    It runs the wrapped ("inner") engine once per rotation angle in
    ``angles`` (default: 0/90/180/270 degrees), re-projects every detected
    bounding box back into the ORIGINAL image's coordinate space, tags
    each OCRResult with the ``angle`` that produced it, and deduplicates
    the combined results across rotations (`deduplicate_ocr_results`),
    keeping the highest-confidence version of anything detected more than
    once.

    This deliberately does NOT decide whether the source is PaddleOCR or
    Tesseract, and does not touch either engine's own preprocessing/config
    -- it is a pure post-hoc robustness layer that can wrap either one
    (or both), so the rest of the pipeline keeps receiving plain
    ``list[OCRResult]`` exactly as before.
    """

    def __init__(
        self,
        inner_engine: Any,
        angles: tuple[int, ...] = ROTATION_ANGLES,
        iou_threshold: float = 0.45,
        confidence_threshold: float = 0.85,
    ) -> None:
        # 0 degrees always runs first: it's the common case, and for
        # engines whose own angle classification already fixes 0/180
        # degree text (PaddleOCR's use_angle_cls), it alone usually
        # recovers most of what's on the package.
        angles = tuple(dict.fromkeys(angles))  # de-dupe, preserve order
        if 0 in angles:
            angles = (0,) + tuple(a for a in angles if a != 0)
        else:
            angles = (0,) + angles

        self.inner_engine = inner_engine
        self.angles = angles
        self.iou_threshold = iou_threshold
        self.confidence_threshold = confidence_threshold

    def recognize(self, image: np.ndarray) -> list[OCRResult]:
        """Run the inner engine at every configured rotation and return
        the merged, deduplicated, original-coordinate-space results."""

        if image is None or getattr(image, "size", 1) == 0:
            return []

        orig_h, orig_w = image.shape[:2]
        collected: list[OCRResult] = []

        for angle in self.angles:
            rotated = _rotate_image(image, angle)

            try:
                raw_results = self.inner_engine.recognize(rotated) or []
            except Exception:
                # One rotation failing (e.g. a transient engine error)
                # shouldn't take down the other, likely-still-useful
                # rotations.
                logger.warning(
                    "OCR pass at %d\u00b0 raised an exception; skipping "
                    "that rotation and continuing with the others.",
                    angle,
                    exc_info=True,
                )
                continue

            for result in raw_results:
                mapped_bbox = _map_bbox_to_original(
                    result.bbox, angle, orig_h, orig_w
                )
                collected.append(
                    OCRResult(
                        text=result.text,
                        confidence=result.confidence,
                        bbox=mapped_bbox,
                        angle=angle,
                    )
                )

            # The common case is an upright package. Do not pay for any
            # rotation once the first pass has a sufficiently clear read.
            if angle == 0 and any(
                result.confidence >= self.confidence_threshold
                and not _is_date_or_label_text(result.text)
                for result in raw_results
            ):
                break

        return deduplicate_ocr_results(
            collected, iou_threshold=self.iou_threshold
        )
