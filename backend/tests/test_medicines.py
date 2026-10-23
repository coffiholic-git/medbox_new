def test_health_check(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"


def test_add_and_list_medicine(client):
    res = client.post(
        "/api/medicines",
        json={"name": "Ibuprofen", "strength": "400 mg", "form": "Tablet"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["medicine"]["name"] == "Ibuprofen"
    assert "advisory" in body

    res = client.get("/api/medicines")
    assert res.status_code == 200
    assert any(m["name"] == "Ibuprofen" for m in res.json())


def test_interaction_advisory_flags_duplicate_ingredient(client):
    client.post("/api/medicines", json={"name": "Paracetamol", "strength": "500 mg"})
    res = client.post("/api/medicines", json={"name": "Paracetamol", "strength": "650 mg"})
    advisory = res.json()["advisory"]
    assert advisory["hasConflict"] is True
    assert "pharmacist" in advisory["advisoryMessage"].lower()


def test_refill_medicine(client):
    add = client.post("/api/medicines", json={"name": "Amlodipine", "strength": "5 mg", "stock": 2, "maxStock": 30})
    med_id = add.json()["medicine"]["id"]

    res = client.patch(f"/api/medicines/{med_id}/refill", json={"amount": 10})
    assert res.status_code == 200
    assert res.json()["stock"] == 12


def test_delete_missing_medicine_404s(client):
    res = client.delete("/api/medicines/does-not-exist")
    assert res.status_code == 404


def test_dose_log_roundtrip(client):
    res = client.post("/api/logs", json={"dateKey": "2026-09-03", "medId": "m-1", "status": "taken"})
    assert res.status_code == 200

    res = client.get("/api/logs", params={"date_key": "2026-09-03"})
    assert len(res.json()) == 1


def test_vitals_roundtrip(client):
    res = client.post(
        "/api/vitals",
        json={"bpSystolic": 118, "bpDiastolic": 76, "glucose": 92, "pulse": 70},
    )
    assert res.status_code == 200

    res = client.get("/api/vitals")
    assert len(res.json()) == 1
