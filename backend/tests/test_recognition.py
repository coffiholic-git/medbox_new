"""
FR10 confirmation-loop tests — the most important safety behavior in
the spec: nothing gets saved without an explicit confirm, and a
low-confidence read can never be confirmed at all.
"""
from backend.services import ocr_service
from backend.routers import auth


def test_login_rejects_an_incorrect_password(client, monkeypatch):
    # Router behaviour independently of the machine's bcrypt extension.
    monkeypatch.setattr(auth, "hash_password", lambda password: f"hash:{password}")
    monkeypatch.setattr(auth, "verify_password", lambda password, password_hash: password_hash == f"hash:{password}")
    registration = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "correct-password"},
    )
    assert registration.status_code == 200

    failed_login = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "wrong-password"},
    )
    assert failed_login.status_code == 401


def test_scan_returns_pending_result_without_saving(client, monkeypatch):
    fake = ocr_service.RecognitionResult(
        ocr_text="PARACETAMOL 500MG TABLETS",
        matched={"name": "Paracetamol", "strength": "500 mg", "form": "Tablet", "instructions": "Take 1 after meals"},
        confidence=95.0,
        engines_agree=True,
        simulated=True,
    )
    monkeypatch.setattr(ocr_service, "run_recognition", lambda *a, **k: fake)

    res = client.post("/api/recognition/scan", json={"file_name": "para.jpg"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending_confirmation"
    assert body["detectedName"] == "Paracetamol"
    assert body["medicine_name"] == "Paracetamol"
    assert body["expiry_date"] is None
    assert body["date_confidence"] == 0.0
    assert body["ocr_text"] == ["PARACETAMOL", "500MG", "TABLETS"]

    # Nothing should be in the library yet — only /confirm can write it.
    assert client.get("/api/medicines").json() == []


def test_scan_returns_unified_expiry_and_mfg_contract(client, monkeypatch):
    fake = ocr_service.RecognitionResult(
        ocr_text="PARACETAMOL MFG 08/2025 EXP 12/2027",
        matched={"name": "Paracetamol", "strength": "500 mg", "form": "Tablet", "instructions": "Take 1"},
        confidence=95.0,
        engines_agree=True,
        simulated=False,
        exp_date="12/2027",
        mfg_date="08/2025",
        date_confidence=91.0,
        matched_keyword="EXP",
        package_details={"manufacturing_date": "08/2025"},
    )
    monkeypatch.setattr(ocr_service, "run_recognition", lambda *a, **k: fake)

    body = client.post("/api/recognition/scan", json={"file_name": "package.jpg"}).json()

    assert body["expiry_date"] == "12/2027"
    assert body["mfg_date"] == "08/2025"
    assert body["date_confidence"] == 0.91
    assert body["matched_keyword"] == "EXP"
    assert body["ocr_text"] == ["PARACETAMOL", "MFG", "08/2025", "EXP", "12/2027"]


def test_low_confidence_scan_never_guesses_and_cannot_be_confirmed(client, monkeypatch):
    fake = ocr_service.RecognitionResult(
        ocr_text="BLURRY TEXT",
        matched=None,
        confidence=40.0,
        engines_agree=False,
        simulated=True,
    )
    monkeypatch.setattr(ocr_service, "run_recognition", lambda *a, **k: fake)

    res = client.post("/api/recognition/scan", json={"file_name": "blurry.jpg"})
    body = res.json()
    assert body["status"] == "low_confidence"
    assert body["detectedName"] is None
    assert "not confident" in body["spokenResponse"].lower()

    confirm = client.post(
        "/api/recognition/confirm",
        json={"recognitionId": body["recognitionId"], "userAction": "confirm"},
    )
    assert confirm.status_code == 400  # cannot confirm a low-confidence read


def test_confirm_saves_to_library_and_reject_does_not(client, monkeypatch):
    fake = ocr_service.RecognitionResult(
        ocr_text="AMLODIPINE 5MG TABLETS",
        matched={"name": "Amlodipine", "strength": "5 mg", "form": "Tablet", "instructions": "Take every morning"},
        confidence=92.0,
        engines_agree=True,
        simulated=True,
    )
    monkeypatch.setattr(ocr_service, "run_recognition", lambda *a, **k: fake)

    scan = client.post("/api/recognition/scan", json={"file_name": "amlo.jpg"}).json()

    confirm = client.post(
        "/api/recognition/confirm",
        json={"recognitionId": scan["recognitionId"], "userAction": "confirm"},
    )
    assert confirm.status_code == 200
    assert confirm.json()["addedToLibrary"] is True
    assert any(m["name"] == "Amlodipine" for m in client.get("/api/medicines").json())

    # A second confirm on the same recognition must be rejected — already confirmed.
    again = client.post(
        "/api/recognition/confirm",
        json={"recognitionId": scan["recognitionId"], "userAction": "confirm"},
    )
    assert again.status_code == 400


def test_reject_discards_without_saving(client, monkeypatch):
    fake = ocr_service.RecognitionResult(
        ocr_text="VITAMIN D3 1000IU",
        matched={"name": "Vitamin D3", "strength": "1000 IU", "form": "Softgel", "instructions": "Take weekly"},
        confidence=90.0,
        engines_agree=True,
        simulated=True,
    )
    monkeypatch.setattr(ocr_service, "run_recognition", lambda *a, **k: fake)

    scan = client.post("/api/recognition/scan", json={"file_name": "vitd.jpg"}).json()
    confirm = client.post(
        "/api/recognition/confirm",
        json={"recognitionId": scan["recognitionId"], "userAction": "reject"},
    )
    assert confirm.status_code == 200
    assert confirm.json()["addedToLibrary"] is False
    assert client.get("/api/medicines").json() == []


def test_reminder_requires_existing_confirmed_medicine(client):
    res = client.post(
        "/api/reminders",
        json={"medId": "does-not-exist", "medName": "Ghost Med", "time": "9:00 AM"},
    )
    assert res.status_code == 400
