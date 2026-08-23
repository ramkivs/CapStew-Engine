"""CR-019 — deterministic real-holdings symbol/screener join hardening."""
import csv
from datetime import date
from pathlib import Path

import pytest

from app.pipeline import run_foundation, run_engine
from app.symbols import (
    MATCH_ALIAS,
    MATCH_AMBIGUOUS,
    MATCH_EXACT_SYMBOL_MAP,
    MATCH_EXACT_TICKER,
    MATCH_NORMALIZED_SCREENER_NAME,
    MATCH_UNRESOLVED,
    build_alias_indexes,
    canonical_name_key,
    normalize_ticker,
    resolve_instrument,
)

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _screener(name="Example Industries Ltd", ticker="EXAMPLE"):
    return [{"name": name, "ticker": ticker}]


def test_existing_exact_symbol_map_still_wins_first():
    result = resolve_instrument(
        "Salasar Techno Engg",
        screener_rows=_screener("Salasar Techno Engineers Limited", "OTHER"),
        alias_map=[("Salasar Techno Engg", "ALIAS")],
    )

    assert result.matched is True
    assert result.ticker == "SALASAR"
    assert result.match_basis == MATCH_EXACT_SYMBOL_MAP


def test_exact_miss_fails_closed_without_screener_or_alias():
    result = resolve_instrument("Synthetic Unknown")

    assert result.matched is False
    assert result.ticker is None
    assert result.match_basis == MATCH_UNRESOLVED


def test_case_whitespace_punctuation_and_legal_suffix_normalization():
    rows = _screener("Alpha-Beta & Company Limited", "ALPHABETA")

    variants = [
        "alpha beta and company",
        "  ALPHA   BETA & CO  ",
        "Alpha.Beta and Company Ltd",
        "Alpha Beta & Company Private Limited",
    ]
    for name in variants:
        result = resolve_instrument(name, screener_rows=rows)
        assert result.matched is True
        assert result.ticker == "ALPHABETA"
        assert result.match_basis == MATCH_NORMALIZED_SCREENER_NAME


def test_canonical_name_key_is_deterministic():
    assert canonical_name_key("Alpha-Beta & Company Limited") == canonical_name_key(" alpha beta and co ")
    assert canonical_name_key("J. Kumar Infraprojects Ltd") == canonical_name_key("J Kumar Infraprojects")


def test_ticker_normalization_is_conservative():
    assert normalize_ticker(" nse:abc.ns ") == "NSE:ABC.NS"
    assert normalize_ticker(" A B C ") == "ABC"
    # Exchange suffixes are preserved, not stripped.
    assert normalize_ticker("ABC.NS") != "ABC"


def test_controlled_alias_resolution_exact_and_canonical():
    alias_map = [("Old Display Name", "NEWTICK"), ("Legacy & Co Ltd", "LEGACY")]

    exact = resolve_instrument("Old Display Name", alias_map=alias_map)
    canonical = resolve_instrument("legacy and company", alias_map=alias_map)

    assert exact.matched is True
    assert exact.ticker == "NEWTICK"
    assert exact.match_basis == MATCH_ALIAS
    assert canonical.matched is True
    assert canonical.ticker == "LEGACY"
    assert canonical.match_basis == MATCH_ALIAS


def test_duplicate_alias_key_fails_validation():
    with pytest.raises(ValueError):
        build_alias_indexes([("Duplicate Name", "AAA"), ("Duplicate Name", "AAA")])


def test_alias_canonical_collision_fails_validation():
    with pytest.raises(ValueError):
        build_alias_indexes([("Foo Ltd", "AAA"), ("Foo Limited", "BBB")])


def test_normalized_screener_name_collision_is_ambiguous():
    result = resolve_instrument(
        "Collision Name",
        screener_rows=[
            {"name": "Collision Name Ltd", "ticker": "AAA"},
            {"name": "Collision Name Limited", "ticker": "BBB"},
        ],
    )

    assert result.matched is False
    assert result.ticker is None
    assert result.match_basis == MATCH_AMBIGUOUS
    assert result.ambiguous is True
    assert result.candidates == ("AAA", "BBB")


def test_explicit_ticker_match_only_when_ticker_is_supplied():
    no_ticker = resolve_instrument("Not The Company Name", screener_rows=_screener("Other Name", "ABC"))
    with_ticker = resolve_instrument(
        "Not The Company Name",
        explicit_ticker=" A B C ",
        screener_rows=_screener("Other Name", "ABC"),
    )

    assert no_ticker.matched is False
    assert no_ticker.match_basis == MATCH_UNRESOLVED
    assert with_ticker.matched is True
    assert with_ticker.ticker == "ABC"
    assert with_ticker.match_basis == MATCH_EXACT_TICKER


def test_genuine_unknown_remains_unresolved():
    result = resolve_instrument("Unknown Instrument", screener_rows=_screener("Known Instrument Ltd", "KNOWN"))

    assert result.matched is False
    assert result.ticker is None
    assert result.match_basis == MATCH_UNRESOLVED


def test_pipeline_uses_unique_normalized_screener_name_fallback(tmp_path):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
        "Example Industries,1,10,100,1000,1200,2.0,20,200,12,30,2026-07-01,2026-07-01\n",
        encoding="utf-8",
    )
    ledger.write_text(
        "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
        "Example Industries,10,100,120,200,1000,1200,01-07-2026\n",
        encoding="utf-8",
    )
    screener.write_text(
        "Name,Ticker,Sub-Sector,Market Cap,Close Price,PE Ratio,PB Ratio,PEGRATIO,Return on Equity,ROCE,Debt to Equity,Interest Coverage Ratio,Price / Free Cash Flow,Pledged Promoter Holdings,200D SMA,PE Premium vs Sub-sector,PB Premium vs Sub-sector,DII Holding Change – 3M,FII Holding Change – 3M\n"
        "Example Industries Ltd,EXAMPLE,Industrials,6000,120,20,2,1.2,15,14,0.1,8,25,0,100,0,0,0,0\n",
        encoding="utf-8",
    )

    foundation = run_foundation(portfolio, screener, ledger, as_of=date(2026, 8, 22), run_id="cr019_join")
    position = foundation["positions"][0]

    assert foundation["reconciliation"]["ok"] is True
    assert [w for w in foundation["warnings"] if w["code"] == "SYMBOL_UNMATCHED"] == []
    assert position["instrument"] == "Example Industries"
    assert position["ticker"] == "EXAMPLE"
    assert position["in_screener"] is True
    assert position["bucket"] == "mid"


def test_ambiguous_pipeline_resolution_preserves_unknown_bucket(tmp_path):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
        "Collision Name,1,10,100,1000,1200,2.0,20,200,0,30,2026-07-01,2026-07-01\n",
        encoding="utf-8",
    )
    ledger.write_text(
        "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
        "Collision Name,10,100,120,200,1000,1200,01-07-2026\n",
        encoding="utf-8",
    )
    screener.write_text(
        "Name,Ticker,Sub-Sector,Market Cap,Close Price,PE Ratio,PB Ratio,PEGRATIO,Return on Equity,ROCE,Debt to Equity,Interest Coverage Ratio,Price / Free Cash Flow,Pledged Promoter Holdings,200D SMA,PE Premium vs Sub-sector,PB Premium vs Sub-sector,DII Holding Change – 3M,FII Holding Change – 3M\n"
        "Collision Name Ltd,AAA,Industrials,6000,120,20,2,1.2,15,14,0.1,8,25,0,100,0,0,0,0\n"
        "Collision Name Limited,BBB,Industrials,7000,120,20,2,1.2,15,14,0.1,8,25,0,100,0,0,0,0\n",
        encoding="utf-8",
    )

    foundation = run_foundation(portfolio, screener, ledger, as_of=date(2026, 8, 22), run_id="cr019_ambiguous")
    position = foundation["positions"][0]

    assert foundation["reconciliation"]["ok"] is True
    assert any(w["code"] == "SYMBOL_UNMATCHED" for w in foundation["warnings"])
    assert position["ticker"] is None
    assert position["in_screener"] is False
    assert position["bucket"] is None


def test_existing_realistic_goldens_and_unknown_bucket_regression_remain_intact():
    payload = run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr019_regression",
    )
    salasar = next(h for h in payload["holdings"] if h["instrument"] == "Salasar Techno Engg")
    ashoka = next(h for h in payload["holdings"] if h["instrument"] == "Ashoka Buildcon")
    lt = next(h for h in payload["holdings"] if h["instrument"] == "Larsen & Toubro")
    agi = next(h for h in payload["holdings"] if h["instrument"] == "AGI Greenpac")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"], salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
    assert agi["decision"] == "WATCH"
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == "assumed_small_micro"
    assert agi["band_basis"] == "assumed_small_micro"
    assert agi["data_quality"]["position_sizing"] == "proxy"


def test_repeated_resolution_is_deterministic():
    rows = _screener("Stable Name Ltd", "STABLE")
    first = resolve_instrument("stable name", screener_rows=rows)
    second = resolve_instrument("stable name", screener_rows=rows)
    assert first == second
