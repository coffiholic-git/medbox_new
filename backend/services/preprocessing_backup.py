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

    img = image.copy()
    img = auto_rotate_if_needed(img)
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)

    if max(sharpened.shape[:2]) < 1200:
        scale = 1200 / max(sharpened.shape[:2])
        width = int(sharpened.shape[1] * scale)
        height = int(sharpened.shape[0] * scale)
        sharpened = cv2.resize(sharpened, (width, height), interpolation=cv2.INTER_CUBIC)

    return sharpened
