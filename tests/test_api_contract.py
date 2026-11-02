"""API contract tests — the documented endpoints must actually do what §11.6 says.

The audit found five documented parameters/fields that did not exist and two that
were silently ignored. Each is pinned here so the contract cannot drift again.

Every test performs its own run: conftest isolates the run store per test, so
state cannot be shared across test functions.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _files(with_sold=False):
    files = {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }
    if with_sold:
        files["sold"] = ("sold.csv", (FIXDIR / "sold_sample.csv").read_bytes(), "text/csv")
    return files


def _run(data=None, with_sold=False):
    r = client.post("/api/v1/run", files=_files(with_sold), data=data or {})
    assert r.status_code == 200, r.text
    return r.json()


# ---- /health ----------------------------------------------------------------

def test_health_reports_data_as_of_of_last_run():
    _run({"as_of": "2026-08-22"})
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["data_as_of"]
    assert body["last_run_id"]


# ---- /run + /ingest accept as_of and data_as_of -----------------------------

def test_run_honours_declared_as_of():
    assert _run({"as_of": "2026-08-22"})["as_of"] == "2026-08-22"


def test_run_rejects_malformed_as_of():
    r = client.post("/api/v1/run", files=_files(), data={"as_of": "22/08/2026"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "DATE_AMBIGUOUS"


def test_run_honours_declared_data_as_of_and_reports_staleness():
    """/run returns a DecisionPayload: data dates surface under provenance.sources."""
    payload = _run({"as_of": "2026-08-22", "data_as_of_ledger": "2026-07-01"})
    ledger = payload["provenance"]["sources"]["ledger"]
    assert ledger["as_of"] == "2026-07-01"
    assert ledger["days_behind"] == 52
    assert "STALENESS" in [w["code"] for w in payload["warnings"]]
    # the other sources stay current
    assert payload["provenance"]["sources"]["portfolio"]["days_behind"] == 0


def test_ingest_accepts_data_as_of():
    r = client.post("/api/v1/ingest", files=_files(),
                    data={"data_as_of_screener": "2026-08-01"})
    assert r.status_code == 200
    assert r.json()["data_as_of"]["screener"] == "2026-08-01"


# ---- /runs ------------------------------------------------------------------

def test_runs_lists_documented_fields():
    _run({"as_of": "2026-08-22"})
    rows = client.get("/api/v1/runs").json()
    assert rows
    row = rows[0]
    for field in ("run_id", "as_of", "engine_version", "policy_version",
                  "input_hash", "content_hash", "holdings_count", "gates_fired"):
        assert field in row, f"{field} missing from /runs"
    assert row["holdings_count"] == 9
    assert "G1" in row["gates_fired"] and "G2" in row["gates_fired"]


# ---- /holdings honours run_id ----------------------------------------------

def test_holdings_honours_run_id():
    first = _run({"as_of": "2026-08-20"})
    _run({"as_of": "2026-08-22"})
    r = client.get("/api/v1/holdings/Salasar Techno Engg",
                   params={"run_id": first["run_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["instrument"] == "Salasar Techno Engg"


def test_holdings_rejects_unknown_run_id():
    """Used to return 200 with the latest run regardless of the run_id given."""
    _run({"as_of": "2026-08-22"})
    r = client.get("/api/v1/holdings/Salasar Techno Engg",
                   params={"run_id": "NONEXISTENT_RUN_999"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_holdings_accepts_ticker_as_well_as_name():
    _run({"as_of": "2026-08-22"})
    assert client.get("/api/v1/holdings/SALASAR").status_code == 200


def test_lots_accepts_ticker_as_well_as_name():
    client.post("/api/v1/ingest", files=_files())
    assert client.get("/api/v1/lots/SALASAR").status_code == 200
    assert client.get("/api/v1/lots/Salasar Techno Engg").status_code == 200


# ---- /tax-tracker honours fy ------------------------------------------------

def test_tax_tracker_returns_computed_fy():
    _run({"as_of": "2026-08-22"}, with_sold=True)
    r = client.get("/api/v1/tax-tracker", params={"fy": "2026-27"})
    assert r.status_code == 200
    assert r.json()["summary"]["fy"] == "2026-27"


@pytest.mark.parametrize("bad", ["garbage!!", "2026", "26-27", ""])
def test_tax_tracker_rejects_malformed_fy(bad):
    """Used to accept any string and silently return the last computed year."""
    _run({"as_of": "2026-08-22"}, with_sold=True)
    r = client.get("/api/v1/tax-tracker", params={"fy": bad})
    assert r.status_code == 422, f"fy={bad!r} returned {r.status_code}"


def test_tax_tracker_rejects_uncomputed_fy():
    """Asking for a different FY must not silently return another year's numbers."""
    _run({"as_of": "2026-08-22"}, with_sold=True)
    r = client.get("/api/v1/tax-tracker", params={"fy": "1999-00"})
    assert r.status_code == 404
    assert r.json()["error"]["details"]["available_fy"] == "2026-27"


# ---- /decisions -------------------------------------------------------------

def test_decisions_by_run_id_matches_run():
    payload = _run({"as_of": "2026-08-22"})
    by_id = client.get("/api/v1/decisions",
                       params={"run_id": payload["run_id"]}).json()
    assert by_id["run_id"] == payload["run_id"]
    assert by_id["content_hash"] == payload["content_hash"]


def test_what_if_is_not_persisted():
    _run({"as_of": "2026-08-22"})
    before = len(client.get("/api/v1/runs").json())
    r = client.post("/api/v1/what-if",
                    json={"policy_overrides": {"max_single_stock_pct": 50.0}})
    assert r.status_code == 200
    assert r.json()["run_id"].startswith("whatif_")
    assert len(client.get("/api/v1/runs").json()) == before


def test_run_and_decisions_are_identical():
    """Audit item J — the persisted payload must equal what /run returned."""
    payload = _run({"as_of": "2026-08-22"})
    assert client.get("/api/v1/decisions").json()["content_hash"] == payload["content_hash"]
