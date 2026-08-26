"""Additive diagnostics tests — structured IMPORT_ERROR responses.

Covers only the new error surface: unusable CSV content must return HTTP 400 with
{"detail": {"error": {code, stage, file, message}}} naming the offending file,
line, and token. No engine/methodology behavior is exercised or altered.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingest import IngestError, _dec, parse_portfolio
from app.main import app

client = TestClient(app)
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"

_PORTFOLIO_HEADER = (
    "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
    "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date"
)


def _base_files(**overrides):
    files = {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }
    files.update(overrides)
    return files


def test_dec_reports_offending_token():
    with pytest.raises(IngestError, match="invalid numeric value"):
        _dec("14.2%")


def test_parser_reports_csv_line(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(
        _PORTFOLIO_HEADER + "\n"
        "X Co,1,10,100.0,1000.0,1200.0,1.5,20.0,100.0,25%,30,2026-05-26,2026-05-26\n"
    )
    with pytest.raises(IngestError) as exc:
        parse_portfolio(p)
    assert "line 2" in str(exc.value)
    assert "25%" in str(exc.value)


def test_run_returns_structured_400_for_bad_number():
    bad_portfolio = (
        _PORTFOLIO_HEADER + "\n"
        "X Co,1,10,100.0,1000.0,1200.0,1.5,20.0,100.0,25%,30,2026-05-26,2026-05-26\n"
    ).encode()
    files = _base_files(portfolio=("broken.csv", bad_portfolio, "text/csv"))
    r = client.post("/api/v1/run", files=files)
    assert r.status_code == 400, r.text
    err = r.json()["detail"]["error"]
    assert err["code"] == "IMPORT_ERROR"
    assert err["stage"] == "parse:portfolio"
    assert err["file"] == "broken.csv"
    assert "25%" in err["message"]
    assert "line 2" in err["message"]


def test_run_returns_structured_400_for_bad_ledger_date():
    bad_ledger = (
        "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
        "X Co,10,100.0,110.0,100.0,1000.0,1100.0,27/05/2026\n"
    ).encode()
    files = _base_files(ledger=("ledger.csv", bad_ledger, "text/csv"))
    r = client.post("/api/v1/run", files=files)
    assert r.status_code == 400, r.text
    err = r.json()["detail"]["error"]
    assert err["code"] == "IMPORT_ERROR"
    assert err["stage"] == "run"
    assert "unrecognized date format" in err["message"]
    assert "27/05/2026" in err["message"]
    assert "X Co" in err["message"]


def test_run_returns_structured_400_for_total_row():
    with_total = (FIXDIR / "portfolio.csv").read_bytes() + b"Total,,,,,,1234567.89,,,,,,\n"
    files = _base_files(portfolio=("portfolio.csv", with_total, "text/csv"))
    r = client.post("/api/v1/run", files=files)
    assert r.status_code == 400, r.text
    err = r.json()["detail"]["error"]
    assert err["code"] == "IMPORT_ERROR"
    assert err["stage"] == "run"
    assert "TOTAL" in err["message"]
    assert "Total" in err["message"]


def test_reconcile_attributes_bad_file_to_its_slot():
    bad_portfolio = b"Instrument,Invested\nFoo,25%\n"
    files = {
        "portfolio": ("p.csv", bad_portfolio, "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }
    r = client.post("/api/v1/reconcile", files=files)
    assert r.status_code == 400
    err = r.json()["detail"]["error"]
    assert err["code"] == "IMPORT_ERROR"
    assert err["stage"] == "parse:portfolio"
    assert err["file"] == "p.csv"
