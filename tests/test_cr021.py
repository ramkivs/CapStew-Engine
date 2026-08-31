"""CR-021 — canonical normalization of downstream screener join keys."""
from datetime import date

import pytest

from app.pipeline import run_foundation
from app.symbols import (
    MATCH_AMBIGUOUS,
    MATCH_EXACT_TICKER,
    MATCH_NORMALIZED_SCREENER_NAME,
    MATCH_UNRESOLVED,
    resolve_instrument,
)


PORTFOLIO_HEADER = (
    "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
    "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
)
LEDGER_HEADER = "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
SCREENER_HEADER = "Name,Ticker\n"


def _run_join_case(tmp_path, portfolio_instrument, screener_ticker):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        PORTFOLIO_HEADER
        + f"{portfolio_instrument},1,10,1000,10000,11440,1.1858,14.4,1440,75.04,74,"
          "2026-06-18,2026-06-18\n",
        encoding="utf-8",
    )
    ledger.write_text(
        LEDGER_HEADER
        + f"{portfolio_instrument},10,1000,1144,1440,10000,11440,18-06-2026\n",
        encoding="utf-8",
    )
    screener.write_text(
        SCREENER_HEADER + f"Infosys Limited,{screener_ticker}\n",
        encoding="utf-8",
    )
    return run_foundation(
        portfolio,
        screener,
        ledger,
        as_of=date(2026, 8, 22),
        run_id="cr021_join",
    )


@pytest.mark.parametrize(
    ("case", "portfolio_instrument", "screener_ticker"),
    [
        ("lowercase", "INFY", "infy"),
        ("internal whitespace", "INFY", "I N F Y"),
        ("boundary whitespace", "INFY", " INFY "),
        ("same-format exchange-qualified", "INFY.NS", "INFY.NS"),
    ],
)
def test_downstream_screener_join_uses_canonical_ticker_keys(
    tmp_path, case, portfolio_instrument, screener_ticker
):
    foundation = _run_join_case(tmp_path, portfolio_instrument, screener_ticker)
    position = foundation["positions"][0]

    assert foundation["reconciliation"]["ok"] is True, case
    assert position["ticker"] == screener_ticker.replace(" ", "").upper()
    assert position["in_screener"] is True
    assert not any(
        warning["code"] in {"SYMBOL_UNMATCHED", "PARTIAL_DATA"}
        and warning.get("instrument") == portfolio_instrument
        for warning in foundation["warnings"]
    )


def test_bare_and_exchange_qualified_tickers_remain_distinct(tmp_path):
    foundation = _run_join_case(tmp_path, "INFY", "INFY.NS")
    position = foundation["positions"][0]

    assert position["ticker"] is None
    assert position["in_screener"] is False
    assert any(
        warning["code"] == "SYMBOL_UNMATCHED"
        and warning["instrument"] == "INFY"
        for warning in foundation["warnings"]
    )


def test_missing_screener_row_remains_partial_data(tmp_path):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        PORTFOLIO_HEADER
        + "AGI Greenpac,1,10,1000,10000,11440,1.1858,14.4,1440,75.04,74,"
        + "2026-06-18,2026-06-18\n",
        encoding="utf-8",
    )
    ledger.write_text(
        LEDGER_HEADER
        + "AGI Greenpac,10,1000,1144,1440,10000,11440,18-06-2026\n",
        encoding="utf-8",
    )
    screener.write_text(SCREENER_HEADER, encoding="utf-8")

    foundation = run_foundation(
        portfolio,
        screener,
        ledger,
        as_of=date(2026, 8, 22),
        run_id="cr021_missing_row",
    )
    position = foundation["positions"][0]

    assert position["ticker"] == "AGIGREENPAC"
    assert position["in_screener"] is False
    assert any(
        warning["code"] == "PARTIAL_DATA"
        and warning["instrument"] == "AGI Greenpac"
        for warning in foundation["warnings"]
    )


def test_existing_resolver_paths_remain_unchanged():
    rows = [
        {"name": "Infosys Limited", "ticker": "INFY"},
        {"name": "Collision Name Ltd", "ticker": "AAA"},
        {"name": "Collision Name Limited", "ticker": "BBB"},
    ]

    display_name = resolve_instrument("Infosys Limited", screener_rows=rows)
    explicit = resolve_instrument(
        "Unknown Display", explicit_ticker="INFY", screener_rows=rows
    )
    ambiguous = resolve_instrument("Collision Name", screener_rows=rows)
    unresolved = resolve_instrument("No Such Instrument", screener_rows=rows)
    canonical = resolve_instrument("INFY", screener_rows=rows)

    assert (display_name.ticker, display_name.match_basis) == (
        "INFY",
        MATCH_NORMALIZED_SCREENER_NAME,
    )
    assert (explicit.ticker, explicit.match_basis) == ("INFY", MATCH_EXACT_TICKER)
    assert ambiguous.match_basis == MATCH_AMBIGUOUS
    assert unresolved.match_basis == MATCH_UNRESOLVED
    assert (canonical.ticker, canonical.match_basis) == ("INFY", MATCH_EXACT_TICKER)
