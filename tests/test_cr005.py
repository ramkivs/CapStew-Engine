"""CR-005 regression suite — source roles, delimiter acceptance, NO-DECISION shape.

Locks in the CR-005 contract (docs/CR-005 authority spec):

* Source roles  — Portfolio/XIRR and Raw Trade Ledger are the broad primary
  sources; the screener is optional enrichment with narrower coverage. A
  holding absent from the screener is partial-data only: never an import error,
  never a reconciliation failure, never excluded from analysis, never forced to
  NO-DECISION. No substitute fundamentals may be fabricated.
* Import format — tab-delimited XIRR/Portfolio and Raw Trade Ledger files are
  first-class; comma-delimited paths keep working; delimiter detection is
  deterministic and ambiguous/malformed layouts raise structured IMPORT_ERROR
  diagnostics instead of being silently reinterpreted.
* UI payload    — a valid G0-blocked NO-DECISION holding omits data_completeness
  and data_quality, nulls evidence/subscores, and keeps reason_tree. That shape
  must keep passing payload validation (it is what the Decisions UI renders).

Additive tests only — no methodology, weights, gates, thresholds, reconciliation,
policy, or payload-version behavior is exercised or altered.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingest import (
    IngestError,
    _sniff_delimiter,
    parse_ledger,
    parse_portfolio,
    parse_screener,
)
from app.main import app
from app.pipeline import decide_on_foundation, run_foundation
from app.schema import validate_decision_payload

client = TestClient(app)
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
AS_OF = date(2026, 8, 26)

# --- canonical layouts (spec §3) ---------------------------------------------

PORTFOLIO_COLS = [
    "Instrument", "Transactions", "Qty Held", "Avg Buy Price", "Invested",
    "Current Value", "Allocation %", "Gain/Loss %", "Net Cashflow", "XIRR",
    "Holding Period (Days)", "First Date", "Last Date",
]
LEDGER_COLS = [
    "Instrument", "Qty.", "Buy Price", "LTP", "P&L", "Invested", "Curr value",
    "Trade Date",
]
# Exact fixture-shaped screener header (21 columns as shipped).
SCREENER_COLS = (FIXDIR / "screener.csv").read_text(encoding="utf-8-sig").splitlines()[0].split(",")

ALPHA_PORT = ["Alpha Corp Ltd", "1", "10", "100", "1000", "1200", "2", "20",
              "-1000", "12.5", "329", "01-10-2025", "01-10-2025"]
BETA_PORT = ["Beta Bank Ltd", "1", "5", "200", "1000", "900", "2", "-10",
             "-1000", "-5", "329", "01-10-2025", "01-10-2025"]
ALPHA_LED = ["Alpha Corp Ltd", "10", "100", "120", "200", "1000", "1200", "01-10-2025"]
BETA_LED = ["Beta Bank Ltd", "5", "200", "180", "-100", "1000", "900", "01-10-2025"]
# Beta Bank Ltd deliberately has NO screener row (BFSI-excluded enrichment).
ALPHA_SCR = ["Alpha Corp Ltd", "ALPHA", "IT Services", "50000", "120", "18", "2",
             "1.2", "15", "18", "10", "12", "0.5", "5", "20", "0", "100",
             "1.0", "1.0", "0.1", "0.1"]


def _write(tmp_path, name, header, rows, delimiter):
    p = tmp_path / name
    p.write_text(
        delimiter.join(header) + "\n" + "\n".join(delimiter.join(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    return p


def _upload(name, path):
    return (name, (path.name, path.read_bytes(), "text/csv"))


# --- 1 · delimiter detection is deterministic ---------------------------------


def test_sniff_delimiter_rules():
    assert _sniff_delimiter("a\tb\tc", "f") == "\t"
    assert _sniff_delimiter("a,b,c", "f") == ","
    assert _sniff_delimiter("single", "f") == ","  # single-column header parses
    with pytest.raises(IngestError, match="ambiguous delimiter"):
        _sniff_delimiter("a\tb,c", "f")


# --- 2 · tab-delimited imports -------------------------------------------------


def test_tab_delimited_xirr_portfolio_parse(tmp_path):
    p = _write(tmp_path, "xirr_report.csv", PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], "\t")
    rows = parse_portfolio(p)
    assert [r["instrument"] for r in rows] == ["Alpha Corp Ltd", "Beta Bank Ltd"]
    a = rows[0]
    assert a["qty_held"] == 10
    assert a["avg_buy_price"] == Decimal("100")
    assert a["invested"] == Decimal("1000")
    assert a["current_value"] == Decimal("1200")
    assert a["alloc_pct"] == Decimal("2")
    assert a["xirr"] == Decimal("12.5")
    assert a["holding_period_days"] == 329
    assert a["first_date"] == "01-10-2025" and a["last_date"] == "01-10-2025"


def test_tab_delimited_ledger_parse(tmp_path):
    p = _write(tmp_path, "ledger.csv", LEDGER_COLS, [ALPHA_LED, BETA_LED], "\t")
    rows = parse_ledger(p)
    a, b = rows
    assert a["instrument"] == "Alpha Corp Ltd"
    assert a["qty"] == 10 and a["buy_price"] == Decimal("100")
    assert a["ltp"] == Decimal("120") and a["trade_date"] == "01-10-2025"
    assert b["instrument"] == "Beta Bank Ltd" and b["qty"] == 5


def test_comma_delimited_paths_identical_result(tmp_path):
    """Existing comma inputs keep working and yield byte-identical parse output."""
    p_tab = _write(tmp_path, "p_tab.csv", PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], "\t")
    p_csv = _write(tmp_path, "p_csv.csv", PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], ",")
    l_tab = _write(tmp_path, "l_tab.csv", LEDGER_COLS, [ALPHA_LED, BETA_LED], "\t")
    l_csv = _write(tmp_path, "l_csv.csv", LEDGER_COLS, [ALPHA_LED, BETA_LED], ",")
    assert parse_portfolio(p_tab) == parse_portfolio(p_csv)
    assert parse_ledger(l_tab) == parse_ledger(l_csv)
    # Shipped comma fixtures remain importable.
    assert parse_portfolio(FIXDIR / "portfolio.csv")
    assert parse_ledger(FIXDIR / "ledger.csv")
    assert parse_screener(FIXDIR / "screener.csv")


# --- 3 · malformed / ambiguous layouts never silently reinterpret --------------


def test_ambiguous_delimiter_header_rejected(tmp_path):
    header = ["Instrument", "Transactions", "Qty Held\tAvg Buy Price", "Invested"]
    p = tmp_path / "xirr_report.csv"
    p.write_text(",".join(header) + "\nAlpha Corp Ltd,1,10,100\n", encoding="utf-8")
    with pytest.raises(IngestError, match="ambiguous delimiter"):
        parse_portfolio(p)


def test_row_with_extra_column_rejected(tmp_path):
    bad = ALPHA_PORT + ["stray"]
    p = _write(tmp_path, "xirr_report.csv", PORTFOLIO_COLS, [BETA_PORT, bad], "\t")
    with pytest.raises(IngestError, match=r"line 3: expected 13 column\(s\), found 14"):
        parse_portfolio(p)


def test_row_with_missing_column_rejected(tmp_path):
    bad = ALPHA_PORT[:-1]  # dropped Last Date -> short by one
    p = _write(tmp_path, "xirr_report.csv", PORTFOLIO_COLS, [ALPHA_PORT, bad], ",")
    with pytest.raises(IngestError, match=r"line 3: expected 13 column\(s\), found 12"):
        parse_portfolio(p)


def test_ambiguous_delimiter_api_returns_structured_400(tmp_path):
    p = tmp_path / "portfolio.csv"
    p.write_text("Instrument\tQty Held,Invested\nAlpha Corp Ltd\t10,1000\n", encoding="utf-8")
    l = _write(tmp_path, "ledger.csv", LEDGER_COLS, [ALPHA_LED], ",")
    resp = client.post("/api/v1/reconcile", files=[_upload("portfolio", p), _upload("ledger", l)])
    assert resp.status_code == 400
    err = resp.json()["detail"]["error"]
    assert err["code"] == "IMPORT_ERROR"
    assert err["file"] == "portfolio.csv"
    assert err["stage"] == "parse:portfolio"
    assert "ambiguous delimiter" in err["message"]


# --- 4 · end-to-end: tab trio runs; tab ≡ comma --------------------------------


def _e2e_files(tmp_path, delimiter, screener_rows=None):
    if screener_rows is None:
        screener_rows = [ALPHA_SCR]
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = _write(tmp_path, f"portfolio_{'tab' if delimiter == chr(9) else 'csv'}.csv",
               PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], delimiter)
    s = _write(tmp_path, "screener.csv", SCREENER_COLS, screener_rows, delimiter)
    l = _write(tmp_path, "ledger.csv", LEDGER_COLS, [ALPHA_LED, BETA_LED], delimiter)
    return p, s, l


def _post_run(p, s, l):
    return client.post("/api/v1/run", files=[
        _upload("portfolio", p), _upload("screener", s), _upload("ledger", l),
    ])


def test_tab_delimited_trio_runs_end_to_end(tmp_path):
    resp = _post_run(*_e2e_files(tmp_path, "\t"))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    validate_decision_payload(payload)
    instruments = {h["instrument"] for h in payload["holdings"]}
    assert instruments == {"Alpha Corp Ltd", "Beta Bank Ltd"}


def test_tab_and_comma_runs_are_content_identical(tmp_path):
    """Same logical inputs in either delimiter must decide identically (no
    silent reinterpretation). Run-history effects (previous_run on the second
    persisted /run) are canonicalized away — they are hysteresis state, not
    delimiter behavior."""
    import copy

    def canon(payload):
        c = copy.deepcopy(payload)
        # run_id/content_hash embed hysteresis history; input_hash (the
        # foundation hash) is asserted separately and is history-free.
        c.pop("run_id", None)
        c.pop("content_hash", None)
        for h in c["holdings"]:
            h["previous_run"] = None
        return c

    tab_payload = _post_run(*_e2e_files(tmp_path / "t", "\t")).json()
    csv_payload = _post_run(*_e2e_files(tmp_path / "c", ",")).json()
    assert canon(tab_payload) == canon(csv_payload)
    assert tab_payload["input_hash"] == csv_payload["input_hash"]


def test_header_only_screener_is_not_an_error(tmp_path):
    s = _write(tmp_path, "screener.csv", SCREENER_COLS, [], ",")
    p = _write(tmp_path, "portfolio.csv", PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], ",")
    l = _write(tmp_path, "ledger.csv", LEDGER_COLS, [ALPHA_LED, BETA_LED], ",")
    resp = client.post("/api/v1/run", files=[
        _upload("portfolio", p), _upload("screener", s), _upload("ledger", l),
    ])
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert len(payload["holdings"]) == 2
    assert all(h["decision"] != "NO-DECISION" for h in payload["holdings"])
    # DATE_FORMAT_INFERRED carries no instrument key — use .get.
    codes = {(w["code"], w.get("instrument")) for w in payload["warnings"]}
    assert ("PARTIAL_DATA", "Alpha Corp Ltd") in codes
    assert ("PARTIAL_DATA", "Beta Bank Ltd") in codes


# --- 5 · source roles: screener-absent holding (deterministic as_of) -----------


def _foundation(tmp_path, ledger_rows, screener_rows=None, delimiter=","):
    if screener_rows is None:
        screener_rows = [ALPHA_SCR]
    p = _write(tmp_path, "portfolio.csv", PORTFOLIO_COLS, [ALPHA_PORT, BETA_PORT], delimiter)
    s = _write(tmp_path, "screener.csv", SCREENER_COLS, screener_rows, delimiter)
    l = _write(tmp_path, "ledger.csv", LEDGER_COLS, ledger_rows, delimiter)
    return run_foundation(p, s, l, as_of=AS_OF)


def test_holding_absent_from_screener_proceeds_with_remaining_evidence(tmp_path):
    foundation = _foundation(tmp_path, [ALPHA_LED, BETA_LED])
    assert foundation["reconciliation"]["blocking"] == 0

    positions = {p["instrument"]: p for p in foundation["positions"]}
    beta_pos = positions["Beta Bank Ltd"]
    assert beta_pos["in_screener"] is False
    assert beta_pos["fundamentals"] is None  # no fabricated substitute metrics

    codes = {(w["code"], w.get("instrument")) for w in foundation["warnings"]}
    assert ("PARTIAL_DATA", "Beta Bank Ltd") in codes

    payload = decide_on_foundation(foundation)
    holdings = {h["instrument"]: h for h in payload["holdings"]}
    beta = holdings["Beta Bank Ltd"]

    # Not excluded, not import error, not forced NO-DECISION.
    assert beta["decision"] != "NO-DECISION"
    # Existing evidence-sufficiency rules apply: sizing+tax = 40% of weight ->
    # INSUFFICIENT tier caps the decision at WATCH. Nothing is fabricated.
    assert beta["decision"] == "WATCH"
    assert beta["evidence"]["tier"] == "INSUFFICIENT"
    assert set(beta["evidence"]["critical_categories_missing"]) == {
        "valuation_stretch", "quality_drift",
    }
    assert any("INSUFFICIENT evidence" in d for d in beta["primary_drivers"])
    assert any("Not in fundamentals screener" in f for f in beta["watch_flags"])
    # Screener-derived categories stay missing; primary-source evidence scores.
    subs = beta["subscores"]
    assert subs["valuation_stretch"] is None
    assert subs["quality_drift"] is None
    assert subs["opportunity_cost"] is None
    assert subs["technical_regime"] is None
    assert subs["position_sizing"] is not None
    assert subs["tax_efficiency"] is not None
    assert beta["data_completeness"]["valuation_stretch"] is False
    assert beta["data_quality"]["valuation_stretch"] == "missing"


def test_screener_present_holding_still_uses_fundamentals(tmp_path):
    foundation = _foundation(tmp_path, [ALPHA_LED, BETA_LED])
    positions = {p["instrument"]: p for p in foundation["positions"]}
    alpha_pos = positions["Alpha Corp Ltd"]
    assert alpha_pos["in_screener"] is True
    assert alpha_pos["fundamentals"]["pe_ratio"] == 18.0

    payload = decide_on_foundation(foundation)
    alpha = {h["instrument"]: h for h in payload["holdings"]}["Alpha Corp Ltd"]
    assert alpha["decision"] != "NO-DECISION"
    assert alpha["subscores"]["valuation_stretch"] == 56
    assert alpha["subscores"]["quality_drift"] == 0
    assert alpha["subscores"]["opportunity_cost"] == 38
    assert alpha["evidence"]["tier"] == "NORMAL"


# --- 6 · valid NO-DECISION shape (what the UI must render) ---------------------


def test_g0_blocked_no_decision_shape_is_minimal_and_valid(tmp_path):
    # Beta has no ledger fills -> G0 NO_LOTS blocking for Beta only.
    foundation = _foundation(tmp_path, [ALPHA_LED])
    assert foundation["reconciliation"]["blocking"] == 1
    assert any(i["code"] == "NO_LOTS" and i["instrument"] == "Beta Bank Ltd"
               for i in foundation["reconciliation"]["issues"])

    payload = decide_on_foundation(foundation)
    validate_decision_payload(payload)
    holdings = {h["instrument"]: h for h in payload["holdings"]}
    beta = holdings["Beta Bank Ltd"]

    assert beta["decision"] == "NO-DECISION"
    # Observed valid omissions per CR-005 §4 — the Decisions UI contract surface.
    assert "data_completeness" not in beta
    assert "data_quality" not in beta
    assert beta["evidence"] is None
    assert beta["subscores"] is None
    assert beta["composite_score"] is None
    assert beta["confidence"] is None
    # reason_tree always remains present.
    assert beta["reason_tree"]["decision_path"] == "G0 → NO-DECISION (reconciliation blocked)"
    # The unaffected holding still gets its full analysis.
    alpha = holdings["Alpha Corp Ltd"]
    assert alpha["decision"] != "NO-DECISION"
    assert alpha["subscores"]["valuation_stretch"] == 56
