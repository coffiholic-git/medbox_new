import cv2
import numpy as np


def auto_rotate_if_needed(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image

    height, width = image.shape[:2]

    if height > width:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

    return image


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("Empty image passed to OCR preprocessing")

    img = auto_rotate_if_needed(image.copy())

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    gray = cv2.bilateralFilter(gray, 5, 45, 45)

    # Upscale small labels conservatively; very large synthetic frames make
    # PaddleOCR's document-preprocessing models unstable on small source photos.
    h, w = gray.shape[:2]
    longest_side = max(h, w)
    if longest_side < 600:
        scale = min(2.0, 600 / longest_side)
        gray = cv2.resize(
            gray,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    # Improve local contrast.
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    )
    enhanced = clahe.apply(gray)

    thresholded = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    combined = cv2.addWeighted(enhanced, 0.75, thresholded, 0.25, 0)

    denoised = cv2.GaussianBlur(combined, (3, 3), 0)

    sharpened = cv2.addWeighted(
        combined,
        1.2,
        denoised,
        -0.2,
        0,
    )

    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
