"""CR-020 — canonical portfolio ticker identity join."""
from datetime import date

from app.pipeline import run_foundation
from app.symbols import MATCH_EXACT_TICKER, resolve_instrument


SCREENER_HEADER = (
    "Name,Ticker,Sub-Sector,Market Cap,Close Price,PE Ratio,PB Ratio,PEGRATIO,"
    "ROE,ROCE,1Y Historical EPS Growth,1Y Forward EPS Growth,Debt to Equity,"
    "Interest Coverage Ratio,Price/FCF,Pledged Promoter Holdings,200D SMA,"
    "PE Premium vs Sub-sector,PB Premium vs Sub-sector,DII Holding Change 3M,"
    "FII Holding Change 3M\n"
)


def test_canonical_ticker_resolves_against_unique_screener_ticker():
    result = resolve_instrument(
        "INFY",
        screener_rows=[{"name": "Infosys Limited", "ticker": "INFY"}],
    )

    assert result.matched is True
    assert result.ticker == "INFY"
    assert result.match_basis == MATCH_EXACT_TICKER


def test_pipeline_joins_canonical_ticker_instrument_to_screener(tmp_path):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
        "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
        "INFY,1,10,1000,10000,11440,1.185836981,14.4,1440,75.04055828,74,"
        "2026-06-18,2026-06-18\n",
        encoding="utf-8",
    )
    ledger.write_text(
        "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
        "INFY,10,1000,1144,1440,10000,11440,18-06-2026\n",
        encoding="utf-8",
    )
    screener.write_text(
        SCREENER_HEADER
        + "Infosys Limited,INFY,IT Services & Consulting,600000,1144,15.42001683,"
        "4.865808069,1.2,31.07124011,39.63183806,10,12,0.098352573,97.14182692,"
        "20,0,1322.513,-18.45270201,-4.812364415,0,0\n",
        encoding="utf-8",
    )

    foundation = run_foundation(
        portfolio,
        screener,
        ledger,
        as_of=date(2026, 8, 22),
        run_id="cr020_infy_join",
    )
    position = foundation["positions"][0]
    infy_symbol_warnings = [
        warning
        for warning in foundation["warnings"]
        if warning.get("instrument") == "INFY"
        and warning["code"] in {"SYMBOL_UNMATCHED", "PARTIAL_DATA"}
    ]

    assert foundation["reconciliation"]["ok"] is True
    assert infy_symbol_warnings == []
    assert position["instrument"] == "INFY"
    assert position["ticker"] == "INFY"
    assert position["in_screener"] is True
    assert position["fundamentals"]["pe_ratio"] == 15.42001683
    assert position["fundamentals"]["roe"] == 31.07124011
