import numpy as np

from backend.perception.preprocessing import convert_to_grayscale, resize_with_aspect_ratio


def test_resize_with_aspect_ratio_does_not_stretch_image():
    image = np.zeros((100, 200, 3), dtype=np.uint8)

    resized = resize_with_aspect_ratio(image, max_width=100, max_height=100)

    assert resized.shape == (50, 100, 3)


def test_convert_to_grayscale_returns_single_channel_image():
    image = np.zeros((20, 30, 3), dtype=np.uint8)

    gray = convert_to_grayscale(image)

    assert gray.shape == (20, 30)
