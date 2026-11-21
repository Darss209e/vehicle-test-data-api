import os
import tempfile

os.environ["VEHICLE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main.init_db()
client = TestClient(main.app)

SAMPLE = {
    "vehicle_model": "Maruti Swift",
    "vehicle_type": "passenger",
    "test_type": "emission",
    "test_date": "2026-11-01",
    "measured_value": 0.85,
    "unit": "g/km",
    "limit_value": 1.0,
    "remarks": "BS6 CO test",
}


def test_create_pass_and_fail():
    r = client.post("/tests", json=SAMPLE)
    assert r.status_code == 201
    assert r.json()["result"] == "pass"

    failing = {**SAMPLE, "measured_value": 1.4}
    r = client.post("/tests", json=failing)
    assert r.json()["result"] == "fail"


def test_get_update_delete():
    created = client.post("/tests", json=SAMPLE).json()
    tid = created["id"]
    assert client.get(f"/tests/{tid}").status_code == 200

    updated = client.put(f"/tests/{tid}", json={**SAMPLE, "measured_value": 2.0}).json()
    assert updated["result"] == "fail"

    assert client.delete(f"/tests/{tid}").status_code == 204
    assert client.get(f"/tests/{tid}").status_code == 404


def test_filters():
    client.post("/tests", json={**SAMPLE, "test_type": "braking", "vehicle_model": "Tata Nexon"})
    r = client.get("/tests", params={"test_type": "braking"})
    assert r.status_code == 200
    assert all(t["test_type"] == "braking" for t in r.json())
    r = client.get("/tests", params={"vehicle_model": "Nexon", "result": "pass"})
    assert len(r.json()) >= 1


def test_stats_and_export():
    stats = client.get("/tests/stats/summary").json()
    assert stats["total_tests"] == stats["passed"] + stats["failed"]
    csv_resp = client.get("/tests/export")
    assert csv_resp.status_code == 200
    assert csv_resp.text.startswith("id,vehicle_model")


def test_validation_error():
    bad = {**SAMPLE, "test_type": "unknown"}
    assert client.post("/tests", json=bad).status_code == 422
