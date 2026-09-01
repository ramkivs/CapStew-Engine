"""Authorized AGI → AGIGREENPAC controlled screener crosswalk regression tests."""
from datetime import date

from app.pipeline import run_foundation
from app.symbols import (
    MATCH_CONTROLLED_SCREENER_CROSSWALK,
    MATCH_EXACT_SYMBOL_MAP,
    MATCH_UNRESOLVED,
    resolve_instrument,
    resolve_screener_ticker,
)


PORTFOLIO_HEADER = (
    "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
    "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
)
LEDGER_HEADER = "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
SCREENER_HEADER = "Name,Ticker\n"


def _write_case(tmp_path, portfolio_rows, ledger_rows, screener_rows):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        PORTFOLIO_HEADER + "".join(portfolio_rows), encoding="utf-8"
    )
    ledger.write_text(LEDGER_HEADER + "".join(ledger_rows), encoding="utf-8")
    screener.write_text(
        SCREENER_HEADER + "".join(screener_rows), encoding="utf-8"
    )
    return run_foundation(
        portfolio,
        screener,
        ledger,
        as_of=date(2026, 8, 31),
        run_id="agi_crosswalk",
    )


def _agi_portfolio_row():
    return (
        "AGI Greenpac,2,2,589.65,1179.30,1549.60,1.0,31.41,370.30,0,"
        "100,2026-07-01,2026-07-02\n"
    )


def _agi_ledger_rows():
    return (
        "AGI Greenpac,1,588.30,774.80,186.50,588.30,774.80,01-07-2026\n"
        "AGI Greenpac,1,591.00,774.80,183.80,591.00,774.80,02-07-2026\n"
    )


def test_agi_screener_ticker_resolves_through_explicit_crosswalk():
    result = resolve_screener_ticker(" AGI ")

    assert result.matched is True
    assert result.ticker == "AGIGREENPAC"
    assert result.match_basis == MATCH_CONTROLLED_SCREENER_CROSSWALK


def test_agi_portfolio_and_screener_share_one_canonical_identity():
    rows = [{"name": "AGI Greenpac Ltd", "ticker": "AGI"}]

    portfolio = resolve_instrument("AGI Greenpac", screener_rows=rows)
    ticker = resolve_instrument("AGI", screener_rows=rows)
    screener = resolve_screener_ticker("AGI")

    assert (portfolio.ticker, portfolio.match_basis) == (
        "AGIGREENPAC",
        MATCH_EXACT_SYMBOL_MAP,
    )
    assert (ticker.ticker, ticker.match_basis) == (
        "AGIGREENPAC",
        MATCH_CONTROLLED_SCREENER_CROSSWALK,
    )
    assert (screener.ticker, screener.match_basis) == (
        "AGIGREENPAC",
        MATCH_CONTROLLED_SCREENER_CROSSWALK,
    )
    assert portfolio.ticker == ticker.ticker == screener.ticker


def test_agi_screener_row_joins_without_partial_data_warning(tmp_path):
    foundation = _write_case(
        tmp_path,
        [_agi_portfolio_row()],
        [_agi_ledger_rows()],
        ["AGI Greenpac Ltd,AGI\n"],
    )
    position = foundation["positions"][0]

    assert foundation["reconciliation"]["ok"] is True
    assert position["instrument"] == "AGI Greenpac"
    assert position["ticker"] == "AGIGREENPAC"
    assert position["in_screener"] is True
    assert position["fundamentals"] is not None
    assert not any(
        warning.get("instrument") == "AGI Greenpac"
        and warning["code"] in {"SYMBOL_UNMATCHED", "PARTIAL_DATA"}
        for warning in foundation["warnings"]
    )


def test_unrelated_ticker_is_not_resolved_through_agi_crosswalk(tmp_path):
    result = resolve_screener_ticker("OTHER")

    assert result.matched is True
    assert result.ticker == "OTHER"
    assert result.match_basis != MATCH_CONTROLLED_SCREENER_CROSSWALK

    foundation = _write_case(
        tmp_path,
        [
            _agi_portfolio_row(),
            "Unrelated Industries,1,1,100,100,120,1.0,20,20,0,30,2026-07-01,2026-07-01\n",
        ],
        [
            _agi_ledger_rows(),
            "Unrelated Industries,1,100,120,20,100,120,01-07-2026\n",
        ],
        [
            "AGI Greenpac Ltd,AGI\n",
            "Unrelated Industries Ltd,OTHER\n",
        ],
    )
    positions = {position["instrument"]: position for position in foundation["positions"]}

    assert positions["AGI Greenpac"]["ticker"] == "AGIGREENPAC"
    assert positions["AGI Greenpac"]["in_screener"] is True
    assert positions["Unrelated Industries"]["ticker"] == "OTHER"
    assert positions["Unrelated Industries"]["in_screener"] is True
    assert not any(
        warning.get("instrument") == "Unrelated Industries"
        and warning["code"] in {"SYMBOL_UNMATCHED", "PARTIAL_DATA"}
        for warning in foundation["warnings"]
    )


def test_cubextub_still_fails_closed(tmp_path):
    foundation = _write_case(
        tmp_path,
        ["CUBEXTUB,1,1,100,100,120,1.0,20,20,0,30,2026-07-01,2026-07-01\n"],
        ["CUBEXTUB,1,100,120,20,100,120,01-07-2026\n"],
        ["AGI Greenpac Ltd,AGI\n"],
    )
    position = foundation["positions"][0]

    assert position["ticker"] is None
    assert position["in_screener"] is False
    assert any(
        warning["code"] == "SYMBOL_UNMATCHED"
        and warning["instrument"] == "CUBEXTUB"
        for warning in foundation["warnings"]
    )
    assert any(
        warning["code"] == "PARTIAL_DATA"
        and warning["instrument"] == "CUBEXTUB"
        for warning in foundation["warnings"]
    )
    assert resolve_instrument(
        "CUBEXTUB",
        screener_rows=[{"name": "AGI Greenpac Ltd", "ticker": "AGI"}],
    ).match_basis == MATCH_UNRESOLVED


def test_existing_static_portfolio_mapping_remains_unchanged():
    result = resolve_instrument("Salasar Techno Engg")

    assert result.ticker == "SALASAR"
    assert result.match_basis == MATCH_EXACT_SYMBOL_MAP
