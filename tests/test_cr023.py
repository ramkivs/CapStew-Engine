"""CR-023 — controlled company and security-series identity resolution."""
from datetime import date

import pytest

from app.pipeline import run_foundation
from app.symbols import (
    MATCH_ALIAS,
    MATCH_AMBIGUOUS,
    MATCH_EXACT_SYMBOL_MAP,
    MATCH_EXACT_TICKER,
    MATCH_NORMALIZED_SCREENER_NAME,
    MATCH_SECURITY_SERIES,
    MATCH_UNRESOLVED,
    canonical_name_key,
    normalize_ticker,
    resolve_instrument,
    strip_security_series_suffix,
)


COMPANY_CASES = [
    ("Kalyan Jewellers", "KALYANKJIL"),
    ("RateGain Travel", "RATEGAIN"),
    ("Shakti Pumps", "SHAKTIPUMP"),
    ("Sharda Motor", "SHARDAMOTR"),
]

SERIES_CASES = [
    ("BIRET-RR", "BIRET"),
    ("EMBASSY-RR", "EMBASSY"),
    ("INDIGRID-IV", "INDIGRID"),
    ("KILITCH-BE", "KILITCH"),
    ("MINDSPACE-RR", "MINDSPACE"),
    ("PGINVIT-IV", "PGINVIT"),
]


@pytest.mark.parametrize("instrument,ticker", COMPANY_CASES)
def test_confirmed_company_name_identities_use_controlled_aliases(instrument, ticker):
    result = resolve_instrument(
        instrument,
        screener_rows=[{"name": "Different Legal Company Name", "ticker": ticker}],
    )

    assert result.matched is True
    assert result.ticker == ticker
    assert result.match_basis == MATCH_ALIAS


@pytest.mark.parametrize("instrument,base_ticker", SERIES_CASES)
def test_confirmed_series_identities_resolve_to_unique_base_ticker(
    instrument, base_ticker
):
    result = resolve_instrument(
        instrument,
        screener_rows=[{"name": "Different Legal Company Name", "ticker": base_ticker}],
    )

    assert result.matched is True
    assert result.ticker == base_ticker
    assert result.match_basis == MATCH_SECURITY_SERIES


@pytest.mark.parametrize(
    ("instrument", "base_ticker"),
    [
        ("biret-rr", "BIRET"),
        ("  EMBASSY - RR ", "EMBASSY"),
        ("indigrid-iv", "INDIGRID"),
        ("kilitch-be", "KILITCH"),
    ],
)
def test_series_rule_uses_conservative_ticker_normalization(instrument, base_ticker):
    assert strip_security_series_suffix(instrument) == base_ticker
    result = resolve_instrument(
        instrument,
        screener_rows=[{"name": "Unrelated Company", "ticker": base_ticker}],
    )
    assert result.ticker == base_ticker
    assert result.match_basis == MATCH_SECURITY_SERIES


@pytest.mark.parametrize("value", ["BIRET-EQ", "BIRET-NS", "BIRET-XYZ", "INFY.NS"])
def test_unsupported_suffixes_and_exchange_qualifiers_are_not_stripped(value):
    assert strip_security_series_suffix(value) is None

    result = resolve_instrument(value, screener_rows=[{"name": "Other", "ticker": "BIRET"}])
    assert result.matched is False
    assert result.ticker is None
    assert result.match_basis == MATCH_UNRESOLVED


def test_series_base_missing_remains_fail_closed():
    result = resolve_instrument(
        "BIRET-RR",
        screener_rows=[{"name": "Another Company", "ticker": "OTHER"}],
    )

    assert result.matched is False
    assert result.ticker is None
    assert result.match_basis == MATCH_UNRESOLVED


def test_company_aliases_do_not_enable_approximate_or_substring_matching():
    for instrument in ("Kalyan Jewellers Group", "RateGain", "Shakti Pump", "Sharda Motors"):
        result = resolve_instrument(
            instrument,
            screener_rows=[{"name": "Unrelated Company", "ticker": "KNOWN"}],
        )
        assert result.matched is False
        assert result.ticker is None
        assert result.match_basis == MATCH_UNRESOLVED


def test_ambiguous_company_name_remains_fail_closed():
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


def test_existing_identity_paths_remain_intact():
    rows = [
        {"name": "Infosys Limited", "ticker": "INFY"},
        {"name": "Other Company", "ticker": "OTHER"},
    ]

    static = resolve_instrument("Salasar Techno Engg", screener_rows=rows)
    display_name = resolve_instrument("Infosys Limited", screener_rows=rows)
    explicit = resolve_instrument(
        "Unknown Display", explicit_ticker="INFY", screener_rows=rows
    )
    canonical = resolve_instrument("INFY", screener_rows=rows)

    assert (static.ticker, static.match_basis) == ("SALASAR", MATCH_EXACT_SYMBOL_MAP)
    assert (display_name.ticker, display_name.match_basis) == (
        "INFY",
        MATCH_NORMALIZED_SCREENER_NAME,
    )
    assert (explicit.ticker, explicit.match_basis) == ("INFY", MATCH_EXACT_TICKER)
    assert (canonical.ticker, canonical.match_basis) == ("INFY", MATCH_EXACT_TICKER)


def test_bare_and_exchange_qualified_tickers_remain_distinct():
    bare_against_qualified = resolve_instrument(
        "INFY", screener_rows=[{"name": "Infosys Limited", "ticker": "INFY.NS"}]
    )
    qualified_against_bare = resolve_instrument(
        "INFY.NS", screener_rows=[{"name": "Infosys Limited", "ticker": "INFY"}]
    )

    assert bare_against_qualified.match_basis == MATCH_UNRESOLVED
    assert qualified_against_bare.match_basis == MATCH_UNRESOLVED
    assert normalize_ticker("INFY.NS") == "INFY.NS"
    assert normalize_ticker("INFY") != normalize_ticker("INFY.NS")


PORTFOLIO_HEADER = (
    "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
    "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date\n"
)
LEDGER_HEADER = "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"


def _run_join_case(tmp_path, instrument, screener_ticker, screener_name="Unrelated Legal Name"):
    portfolio = tmp_path / "portfolio.csv"
    ledger = tmp_path / "ledger.csv"
    screener = tmp_path / "screener.csv"

    portfolio.write_text(
        PORTFOLIO_HEADER
        + f"{instrument},1,10,1000,10000,12000,1.0,20.0,2000,,60,2026-07-01,2026-07-01\n",
        encoding="utf-8",
    )
    ledger.write_text(
        LEDGER_HEADER
        + f"{instrument},10,1000,1200,2000,10000,12000,01-07-2026\n",
        encoding="utf-8",
    )
    screener.write_text(
        "Name,Ticker\n" + f"{screener_name},{screener_ticker}\n",
        encoding="utf-8",
    )

    return run_foundation(
        portfolio,
        screener,
        ledger,
        as_of=date(2026, 8, 31),
        run_id="cr023_join",
    )


@pytest.mark.parametrize("instrument,ticker", COMPANY_CASES + SERIES_CASES)
def test_confirmed_cases_join_to_screener_without_identity_warnings(
    tmp_path, instrument, ticker
):
    foundation = _run_join_case(tmp_path, instrument, ticker)
    position = foundation["positions"][0]

    assert position["ticker"] == ticker
    assert position["in_screener"] is True
    assert not any(
        warning.get("instrument") == instrument
        and warning["code"] in {"SYMBOL_UNMATCHED", "PARTIAL_DATA"}
        for warning in foundation["warnings"]
    )


def test_cubextub_remains_unresolved_and_partial_when_screener_row_is_absent(tmp_path):
    foundation = _run_join_case(
        tmp_path,
        "CUBEXTUB",
        "NOT_USED",
        screener_name="Different Company",
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


def test_company_name_key_behavior_remains_deterministic():
    assert canonical_name_key("Kalyan Jewellers") == canonical_name_key(
        "kalyan jewellers"
    )
    assert canonical_name_key("RateGain Travel") != canonical_name_key("RateGain")
