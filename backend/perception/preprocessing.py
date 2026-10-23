from pathlib import Path

import cv2
import numpy as np


def load_image(image_path: str | Path) -> np.ndarray:
    """Load an image from disk using OpenCV.

    OpenCV's imread only supports a fixed set of codecs and returns
    None (not an exception) for anything else — notably AVIF/HEIC,
    which some phones/browsers save by default. The frontend now
    re-encodes uploads to JPEG before sending them, but this is a
    second line of defense: fall back to Pillow, which covers a
    broader set of formats, before giving up and asking for a rescan.
    """
    path = Path(image_path)
    image = cv2.imread(str(path))

    if image is None:
        image = _load_with_pillow(path)

    if image is None:
        raise FileNotFoundError(
            f"Could not load image: {path}"
        )

    return image


def _load_with_pillow(path: Path) -> np.ndarray | None:
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(path) as pil_image:
            rgb = pil_image.convert("RGB")
            array = np.array(rgb)
    except Exception:
        return None

    # PIL gives RGB; the rest of the pipeline (and cv2.imread) expects BGR.
    return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)


def resize_with_aspect_ratio(
    image: np.ndarray,
    max_width: int = 1000,
    max_height: int = 1000,
) -> np.ndarray:
    """Resize an image to fit inside max_width/max_height without stretching."""
    height, width = image.shape[:2]

    scale = min(
        max_width / width,
        max_height / height,
        1.0,
    )

    if scale == 1.0:
        return image.copy()

    new_size = (
        int(width * scale),
        int(height * scale),
    )

    return cv2.resize(
        image,
        new_size,
        interpolation=cv2.INTER_AREA,
    )


def convert_to_grayscale(
    image: np.ndarray,
) -> np.ndarray:
    """Convert a BGR color image to grayscale."""

    if len(image.shape) == 2:
        return image.copy()

    return cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )


def sharpen_image(
    image: np.ndarray,
) -> np.ndarray:
    """Apply a light sharpening filter that can help some medicine labels."""

    kernel = np.array(
        [
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0],
        ]
    )

    return cv2.filter2D(
        image,
        -1,
        kernel,
    )


def prepare_for_ocr(
    image: np.ndarray,
    max_width: int = 1600,
    grayscale: bool = True,
    denoise: bool = False,
    sharpen: bool = True,
) -> np.ndarray:
    """Prepare an image for OCR with simple, configurable steps.

    max_width is raised to 1600 (from 1000) so that small embossed or
    dot-matrix date/batch stamps — which are often only a few pixels tall
    at 1000 px — are large enough for Tesseract to read reliably.
    sharpening is now on by default for the same reason.
    """

    prepared = resize_with_aspect_ratio(
        image,
        max_width=max_width,
        max_height=max_width,
    )

    if grayscale:
        prepared = convert_to_grayscale(
            prepared
        )

    if denoise:
        prepared = cv2.fastNlMeansDenoising(
            prepared
        )

    if sharpen:
        prepared = sharpen_image(
            prepared
        )

    return prepared