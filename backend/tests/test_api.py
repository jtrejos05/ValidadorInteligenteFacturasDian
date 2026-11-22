import pytest
from fastapi.testclient import TestClient

from app.main import app, get_store
from app.store import SQLiteReportStore


@pytest.fixture
def client(tmp_path):
    store = SQLiteReportStore(tmp_path / "test.db")
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_upload_xml(client):
    xml = client.get("/api/samples/valid_office_supplies/xml").content
    r = client.post("/api/validate", files={"xml": ("f.xml", xml, "application/xml")})
    assert r.status_code == 200
    assert r.json()["decision"] == "approved"


def test_upload_requires_a_file(client):
    assert client.post("/api/validate").status_code == 400


def test_rejects_unsupported_attachment(client):
    r = client.post(
        "/api/validate", files={"attachment": ("a.exe", b"MZ", "application/x-msdownload")}
    )
    assert r.status_code == 415


def test_human_review_flow(client):
    report = client.post("/api/samples/ai_medicine_full_iva/validate").json()
    assert report["decision"] == "needs_review"
    pending = client.get("/api/reports", params={"review_status": "pending"}).json()
    assert [p["id"] for p in pending] == [report["id"]]

    r = client.post(
        f"/api/reports/{report['id']}/review", json={"decision": "approved", "note": "ok"}
    )
    assert r.json()["review_status"] == "approved"
    assert client.get("/api/reports", params={"review_status": "pending"}).json() == []


def test_cannot_review_an_auto_decided_invoice(client):
    report = client.post("/api/samples/cufe_tampered/validate").json()
    r = client.post(f"/api/reports/{report['id']}/review", json={"decision": "approved"})
    assert r.status_code == 409


def test_metrics(client):
    client.post("/api/samples/valid_office_supplies/validate")
    client.post("/api/samples/cufe_tampered/validate")
    m = client.get("/api/metrics").json()
    assert m["invoices"] == 2
    assert m["auto_resolution_rate"] == 1.0
    assert m["business_case"]["estimated_hours_saved"] > 0
