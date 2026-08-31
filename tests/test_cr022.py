"""CR-022 — explicit NO-DECISION payload variant contract."""
import csv
import shutil
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.pipeline import run_engine
from app.schema import validate_decision_payload


FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _input_files(tmp_path, blocked_instruments):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for filename in ("portfolio.csv", "screener.csv", "ledger.csv"):
        shutil.copyfile(FIXDIR / filename, input_dir / filename)

    rows = []
    ledger_path = input_dir / "ledger.csv"
    with ledger_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        if row["Instrument"] in blocked_instruments:
            row["Buy Price"] = "999.00"
    with ledger_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return input_dir


def _run_g0_case(tmp_path, blocked_instruments):
    input_dir = _input_files(tmp_path, set(blocked_instruments))
    return run_engine(
        input_dir / "portfolio.csv",
        input_dir / "screener.csv",
        input_dir / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr022_g0",
    )


def test_normal_holdings_keep_complete_data_contract():
    payload = run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr022_normal",
    )

    validate_decision_payload(payload)
    assert all(h["decision"] != "NO-DECISION" for h in payload["holdings"])
    assert all("data_completeness" in h for h in payload["holdings"])
    assert all("data_quality" in h for h in payload["holdings"])

    agi = next(h for h in payload["holdings"] if h["instrument"] == "AGI Greenpac")
    assert agi["decision"] == "WATCH"
    assert agi["data_completeness"]["position_sizing"] is True
    assert agi["data_completeness"]["valuation_stretch"] is False


def test_g0_holding_uses_explicit_minimal_no_decision_variant(tmp_path):
    payload = _run_g0_case(tmp_path, {"Bank of Baroda"})
    validate_decision_payload(payload)

    blocked = next(h for h in payload["holdings"] if h["instrument"] == "Bank of Baroda")
    assert blocked["decision"] == "NO-DECISION"
    assert blocked["stage1"]["winning_gate"] == "G0"
    assert blocked["composite_score"] is None
    assert blocked["confidence"] is None
    assert "data_completeness" not in blocked
    assert "data_quality" not in blocked
    assert "behavioral" not in blocked
    assert "lots" not in blocked

    unaffected = next(h for h in payload["holdings"] if h["instrument"] == "Salasar Techno Engg")
    assert unaffected["decision"] == "TRIM"
    assert "data_completeness" in unaffected
    assert "data_quality" in unaffected


def test_multiple_g0_holdings_are_validated_as_no_decision_variants(tmp_path):
    payload = _run_g0_case(tmp_path, {"Bank of Baroda", "Bharat Coking Coal"})
    validate_decision_payload(payload)

    for instrument in ("Bank of Baroda", "Bharat Coking Coal"):
        holding = next(h for h in payload["holdings"] if h["instrument"] == instrument)
        assert holding["decision"] == "NO-DECISION"
        assert holding["stage1"]["winning_gate"] == "G0"
        assert "data_completeness" not in holding


def test_run_api_returns_canonical_g0_variant(tmp_path, monkeypatch):
    input_dir = _input_files(tmp_path, {"Bank of Baroda"})
    monkeypatch.setattr(config, "STORE_PATH", tmp_path / "engine.db")

    files = {
        "portfolio": ("portfolio.csv", (input_dir / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (input_dir / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (input_dir / "ledger.csv").read_bytes(), "text/csv"),
    }
    response = TestClient(app).post("/api/v1/run", files=files)

    assert response.status_code == 200
    payload = response.json()
    blocked = next(h for h in payload["holdings"] if h["instrument"] == "Bank of Baroda")
    assert blocked["decision"] == "NO-DECISION"
    assert blocked["stage1"]["winning_gate"] == "G0"
    assert "data_completeness" not in blocked
    assert "data_quality" not in blocked
