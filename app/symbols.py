"""Deterministic symbol/name resolution for portfolio, ledger, and screener joins.

CR-019 hardens the join path without changing methodology: exact configured
symbols still win, controlled aliases are explicit, normalized screener-name
fallback is allowed only when unique, and ambiguous/unknown inputs fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from collections.abc import Iterable, Mapping

from .config import SYMBOL_MAP

MATCH_EXACT_SYMBOL_MAP = "exact_symbol_map"
MATCH_ALIAS = "alias"
MATCH_NORMALIZED_SCREENER_NAME = "normalized_screener_name"
MATCH_EXACT_TICKER = "exact_ticker"
MATCH_NORMALIZED_TICKER = "normalized_ticker"
MATCH_CONTROLLED_SCREENER_CROSSWALK = "controlled_screener_crosswalk"
MATCH_SECURITY_SERIES = "security_series"
MATCH_UNRESOLVED = "unresolved"
MATCH_AMBIGUOUS = "ambiguous"

# CR-023: these are evidence-backed company-name identities from the latest
# full-holdings reconciliation. They are controlled aliases, not fuzzy matches.
CONTROLLED_ALIAS_MAP: tuple[tuple[str, str], ...] = (
    ("Kalyan Jewellers", "KALYANKJIL"),
    ("RateGain Travel", "RATEGAIN"),
    ("Shakti Pumps", "SHAKTIPUMP"),
    ("Sharda Motor", "SHARDAMOTR"),
)

# Explicit screener-to-canonical identity authority. This is deliberately kept
# separate from CONTROLLED_ALIAS_MAP: the source side is a confirmed screener
# ticker, not a portfolio/display-name alias. Do not infer additional pairs.
CONTROLLED_SCREENER_TICKER_CROSSWALK: tuple[tuple[str, str], ...] = (
    ("AGI", "AGIGREENPAC"),
)

# CR-023 permits only these terminal portfolio security-series suffixes. They
# are intentionally not part of normalize_ticker(): bare and qualified ticker
# identities, and all unsupported suffixes, remain distinct.
_SECURITY_SERIES_SUFFIXES = ("-RR", "-IV", "-BE")

_LEGAL_SUFFIXES = {"ltd", "limited", "pvt", "private", "co", "company"}
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SymbolResolution:
    ticker: str | None
    matched: bool
    match_basis: str
    ambiguous: bool = False
    candidates: tuple[str, ...] = ()


def normalize_ticker(value: str | None) -> str | None:
    """Conservative ticker normalization: trim, uppercase, remove whitespace."""
    if value is None:
        return None
    ticker = "".join(str(value).strip().upper().split())
    return ticker or None


def resolve_screener_ticker(value: str | None) -> SymbolResolution:
    """Resolve a screener ticker to the established canonical ticker.

    The only semantic crosswalk currently authorized is the exact AGI pair. All
    other screener tickers receive conservative normalization only; they are not
    matched by name resemblance, substring, or ticker similarity.
    """
    ticker = normalize_ticker(value)
    if not ticker:
        return SymbolResolution(None, False, MATCH_UNRESOLVED)

    for source, canonical in CONTROLLED_SCREENER_TICKER_CROSSWALK:
        if ticker == source:
            return SymbolResolution(
                canonical,
                True,
                MATCH_CONTROLLED_SCREENER_CROSSWALK,
            )
    return SymbolResolution(ticker, True, MATCH_NORMALIZED_TICKER)


def strip_security_series_suffix(value: str | None) -> str | None:
    """Return a base ticker for an explicitly authorized portfolio series form.

    Only terminal ``-RR``, ``-IV``, and ``-BE`` are recognized. This helper is
    deliberately separate from ``normalize_ticker`` so unsupported suffixes and
    bare-versus-exchange-qualified identities remain distinct.
    """
    ticker = normalize_ticker(value)
    if not ticker:
        return None
    for suffix in _SECURITY_SERIES_SUFFIXES:
        if ticker.endswith(suffix) and len(ticker) > len(suffix):
            return ticker[:-len(suffix)]
    return None


def canonical_name_key(value: str | None) -> str:
    """Return a deterministic comparison key for company/instrument names.

    The key is used only for matching. It never replaces the displayed
    instrument name in payloads.
    """
    text = unicodedata.normalize("NFKC", value or "").strip().casefold()
    text = text.replace("&", " and ")
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return ""
    tokens = text.split(" ")
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def _alias_items(alias_map=None):
    alias_map = CONTROLLED_ALIAS_MAP if alias_map is None else alias_map
    if isinstance(alias_map, Mapping):
        return list(alias_map.items())
    if isinstance(alias_map, Iterable):
        return list(alias_map)
    raise TypeError("alias_map must be a mapping or iterable of (alias, ticker) pairs")


def build_alias_indexes(alias_map=None):
    """Validate and index controlled aliases.

    Duplicate raw aliases and canonical collisions are rejected because they would
    make matching non-auditable.
    """
    exact = {}
    canonical = {}
    seen_raw = set()
    for raw_alias, raw_ticker in _alias_items(alias_map):
        alias = (raw_alias or "").strip()
        ticker = normalize_ticker(raw_ticker)
        if not alias or not ticker:
            raise ValueError("alias entries require non-empty alias and ticker")
        if alias in seen_raw:
            raise ValueError(f"duplicate alias key {alias!r}")
        seen_raw.add(alias)
        key = canonical_name_key(alias)
        if key in canonical and canonical[key] != ticker:
            raise ValueError(f"alias canonical key {key!r} maps to multiple tickers")
        exact[alias] = ticker
        canonical[key] = ticker
    return exact, canonical


def build_screener_indexes(screener_rows=None):
    """Build deterministic name/ticker indexes from parsed screener rows."""
    name_index = {}
    ticker_index = {}
    for row in screener_rows or []:
        ticker = normalize_ticker(row.get("ticker"))
        if not ticker:
            continue
        ticker_index.setdefault(ticker, set()).add(ticker)
        key = canonical_name_key(row.get("name"))
        if key:
            name_index.setdefault(key, set()).add(ticker)
    return name_index, ticker_index


def _unique_or_ambiguous(candidates):
    ordered = tuple(sorted(candidates or ()))
    if len(ordered) == 1:
        return ordered[0], False, ordered
    if len(ordered) > 1:
        return None, True, ordered
    return None, False, ()


def resolve_instrument(name, *, screener_rows=None, alias_map=None, explicit_ticker=None):
    """Resolve an instrument to a ticker using fail-closed precedence."""
    raw_name = (name or "").strip()

    # 1. Preserve existing exact SYMBOL_MAP behavior as first precedence.
    if raw_name in SYMBOL_MAP:
        return SymbolResolution(SYMBOL_MAP[raw_name], True, MATCH_EXACT_SYMBOL_MAP)

    # 2/3. Controlled alias map: exact raw, then canonical normalized alias.
    exact_alias, canonical_alias = build_alias_indexes(alias_map)
    if raw_name in exact_alias:
        return SymbolResolution(exact_alias[raw_name], True, MATCH_ALIAS)
    canonical_key = canonical_name_key(raw_name)
    if canonical_key in canonical_alias:
        return SymbolResolution(canonical_alias[canonical_key], True, MATCH_ALIAS)

    screener_name_index, screener_ticker_index = build_screener_indexes(screener_rows)

    # 4. Unique normalized screener-name fallback.
    ticker, ambiguous, candidates = _unique_or_ambiguous(screener_name_index.get(canonical_key))
    if ticker:
        return SymbolResolution(ticker, True, MATCH_NORMALIZED_SCREENER_NAME)
    if ambiguous:
        return SymbolResolution(None, False, MATCH_AMBIGUOUS, True, candidates)

    # 5. Exact normalized ticker match when explicit ticker is supplied.
    normalized_ticker = normalize_ticker(explicit_ticker)
    if normalized_ticker:
        ticker, ambiguous, candidates = _unique_or_ambiguous(screener_ticker_index.get(normalized_ticker))
        if ticker:
            return SymbolResolution(ticker, True, MATCH_EXACT_TICKER)
        if ambiguous:
            return SymbolResolution(None, False, MATCH_AMBIGUOUS, True, candidates)

    # 6. CR-020: a portfolio Instrument may itself be a canonical ticker.
    # Keep display-name and explicit-ticker precedence above; only treat the
    # instrument value as a ticker when no explicit ticker was supplied.
    if not normalized_ticker:
        normalized_instrument = normalize_ticker(raw_name)
        if normalized_instrument:
            controlled = resolve_screener_ticker(normalized_instrument)
            if controlled.match_basis == MATCH_CONTROLLED_SCREENER_CROSSWALK:
                return controlled

            ticker, ambiguous, candidates = _unique_or_ambiguous(
                screener_ticker_index.get(normalized_instrument)
            )
            if ticker:
                return SymbolResolution(ticker, True, MATCH_EXACT_TICKER)
            if ambiguous:
                return SymbolResolution(None, False, MATCH_AMBIGUOUS, True, candidates)

        # 7. CR-023: strip only an explicitly authorized terminal security-series
        # suffix from a portfolio instrument and resolve its unique base ticker.
        series_base = strip_security_series_suffix(raw_name)
        if series_base:
            ticker, ambiguous, candidates = _unique_or_ambiguous(
                screener_ticker_index.get(series_base)
            )
            if ticker:
                return SymbolResolution(ticker, True, MATCH_SECURITY_SERIES)
            if ambiguous:
                return SymbolResolution(None, False, MATCH_AMBIGUOUS, True, candidates)

    # 8. Fail closed.
    return SymbolResolution(None, False, MATCH_UNRESOLVED)


def map_name_to_ticker(name):
    """Backward-compatible exact configured symbol-map lookup."""
    result = resolve_instrument(name, screener_rows=None, alias_map=())
    if result.match_basis == MATCH_EXACT_SYMBOL_MAP:
        return (result.ticker, True)
    return (None, False)
