from backend.perception.ocr import parse_paddleocr_results


def test_parse_paddleocr_legacy_result_shape():
    raw = [[[[0, 0], [10, 0], [10, 10], [0, 10]], ("PARACETAMOL", 0.94)]]

    results = parse_paddleocr_results(raw)

    assert results[0].text == "PARACETAMOL"
    assert results[0].confidence == 0.94
    assert results[0].bbox == [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_parse_paddleocr_newer_result_shape():
    raw = {
        "res": {
            "rec_texts": ["PARACETAMOL"],
            "rec_scores": [0.91],
            "rec_boxes": [[1, 2, 3, 4]],
        }
    }

    results = parse_paddleocr_results(raw)

    assert results[0].text == "PARACETAMOL"
    assert results[0].confidence == 0.91
    assert results[0].bbox == [1, 2, 3, 4]
