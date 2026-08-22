from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _files():
    return {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "phase 3" in body["phase"].lower()


def test_ingest_roundtrip():
    r = client.post("/api/v1/ingest", files=_files())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reconciliation"]["ok"] is True
    assert data["content_hash"]
    assert len(data["positions"]) == 9
    assert len(data["lots"]) == 30  # 3+16+2+2+1+1+2+1+2


def test_ingest_rejects_non_csv():
    files = {
        "portfolio": ("portfolio.txt", b"nope", "text/plain"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }
    r = client.post("/api/v1/ingest", files=files)
    assert r.status_code == 400


def test_reconcile_dry_run():
    files = {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }
    r = client.post("/api/v1/reconcile", files=files)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_lots_endpoint_after_ingest():
    client.post("/api/v1/ingest", files=_files())
    r = client.get(f"/api/v1/lots/{quote('Salasar Techno Engg')}")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_lots_endpoint_missing():
    client.post("/api/v1/ingest", files=_files())
    r = client.get(f"/api/v1/lots/{quote('Does Not Exist')}")
    assert r.status_code == 404
