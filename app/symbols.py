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
MATCH_UNRESOLVED = "unresolved"
MATCH_AMBIGUOUS = "ambiguous"

# Intentionally empty until a named authorization adds real aliases. The resolver
# supports a controlled alias map and tests its collision behavior with synthetic
# data, but no real portfolio names are embedded here.
CONTROLLED_ALIAS_MAP: tuple[tuple[str, str], ...] = ()

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

    # 5. Exact normalized ticker match only when explicit ticker is supplied.
    normalized_ticker = normalize_ticker(explicit_ticker)
    if normalized_ticker:
        ticker, ambiguous, candidates = _unique_or_ambiguous(screener_ticker_index.get(normalized_ticker))
        if ticker:
            return SymbolResolution(ticker, True, MATCH_EXACT_TICKER)
        if ambiguous:
            return SymbolResolution(None, False, MATCH_AMBIGUOUS, True, candidates)

    # 6. Fail closed.
    return SymbolResolution(None, False, MATCH_UNRESOLVED)


def map_name_to_ticker(name):
    """Backward-compatible exact configured symbol-map lookup."""
    result = resolve_instrument(name, screener_rows=None, alias_map=())
    if result.match_basis == MATCH_EXACT_SYMBOL_MAP:
        return (result.ticker, True)
    return (None, False)
