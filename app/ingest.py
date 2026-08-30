"""Delimited-value parsers for the three exports (Phase 1).

Each parser normalizes column names to a canonical lowercased alphanumeric key
so it tolerates the exports' quirks: "Qty." (trailing dot), "Curr value"
(lowercase v), "Allocation %", "Holding Period (Days)", etc.

CR-005: both comma- and tab-delimited exports are accepted. The delimiter is
detected deterministically from the header row (TAB only when tabs are the sole
separator present); a header mixing TAB and comma is ambiguous and rejected
with a structured IMPORT_ERROR instead of being silently reinterpreted. Data
rows whose column count differs from the header are likewise rejected — the
parsers never guess at a column layout.
"""
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .normalize import parse_date


class IngestError(ValueError):
    """CSV content the engine cannot ingest, carrying the offending token/cell.

    Diagnostic surface only — parsing semantics are unchanged. The API layer maps
    this to a structured 400 (IMPORT_ERROR) instead of an opaque 500.
    """


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (key or "").strip().lower())


def _dec(value):
    s = (value or "").strip().replace(",", "")
    if s in ("", "-", "—", "N/A", "NA", "null", "None"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise IngestError(f"invalid numeric value {value!r}") from exc


def _int(value):
    d = _dec(value)
    return None if d is None else int(d)


# Sentinels for csv.DictReader row-width validation (CR-005). Using unique
# objects (not None) so a genuinely empty cell ("") is never confused with a
# short row, and extra cells can never collide with a real header name.
_MISSING_CELL = object()  # restval: row had fewer columns than the header
_EXTRA_CELLS = object()   # restkey: row had more columns than the header


def _sniff_delimiter(header_line: str, source: str) -> str:
    """Pick the delimiter deterministically from the header row.

    Rules (CR-005 §3):
    * TAB        — header contains TAB and no comma;
    * comma      — header contains comma and no TAB, or neither separator
                   (single-column file: parses, downstream column checks apply);
    * ambiguous  — header contains BOTH — rejected. Mixing separators in the
                   header means no deterministic column layout exists; guessing
                   would silently reinterpret the data.
    """
    has_tab = "\t" in header_line
    has_comma = "," in header_line
    if has_tab and has_comma:
        raise IngestError(
            f"{source}: ambiguous delimiter — the header row contains both TAB and comma "
            "characters, so no deterministic column layout exists. Re-export the file with a "
            "single consistent separator (tab or comma)."
        )
    return "\t" if has_tab else ","


def _read(path):
    source = Path(path).name
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header_line = None
        for line in fh:
            if line.strip():
                header_line = line
                break
        if header_line is None:
            return []
        delimiter = _sniff_delimiter(header_line, source)

    with open(path, newline="", encoding="utf-8-sig") as fh:
        # Skip leading blank lines so the row DictReader treats as the header is
        # exactly the row the delimiter was sniffed from.
        pos = fh.tell()
        line = fh.readline()
        while line and not line.strip():
            pos = fh.tell()
            line = fh.readline()
        fh.seek(pos)

        reader = csv.DictReader(
            fh, delimiter=delimiter, restkey=_EXTRA_CELLS, restval=_MISSING_CELL,
        )
        if not reader.fieldnames:
            return []
        norm = {orig: _norm_key(orig) for orig in reader.fieldnames}
        width = len(reader.fieldnames)
        rows = []
        for lineno, row in enumerate(reader, start=2):
            if _EXTRA_CELLS in row:
                found = width + len(row[_EXTRA_CELLS])
                raise IngestError(
                    f"{source} line {lineno}: expected {width} column(s), found {found} — "
                    "the data row contains an extra separator; fix the export rather than "
                    "letting the importer guess."
                )
            missing = sum(1 for v in row.values() if v is _MISSING_CELL)
            if missing:
                raise IngestError(
                    f"{source} line {lineno}: expected {width} column(s), found {width - missing} — "
                    "the data row is missing separator(s); fix the export rather than letting "
                    "the importer guess."
                )
            rows.append({norm[k]: v for k, v in row.items() if k in norm})
        return rows


def parse_ledger(path):
    """Trade ledger: Instrument, Qty., Buy Price, LTP, P&L, Invested, Curr value, Trade Date."""
    rows = []
    for line, r in enumerate(_read(path), start=2):
        try:
            rows.append({
                "instrument": (r.get("instrument") or "").strip(),
                "qty": _int(r.get("qty")),
                "buy_price": _dec(r.get("buyprice")),
                "ltp": _dec(r.get("ltp")),
                "invested": _dec(r.get("invested")),
                "curr_value": _dec(r.get("currvalue")),
                "trade_date": (r.get("tradedate") or "").strip(),
            })
        except IngestError as exc:
            raise IngestError(f"line {line}: {exc}") from exc
    return rows


def _conviction_carrier(r):
    """Optional declared-conviction passthrough for portfolio rows (EMM-H3/G2).

    Column headers arrive normalized (``_norm_key``: lowercase alphanumeric),
    e.g. ``conviction_score`` -> ``convictionscore``. Values are carried under
    the exact contract field names. ``conviction_score_present`` distinguishes
    "column absent / empty cell" (False) from "text present" (True); a text
    present value that does not parse stays None and equals the Q-i2
    malformed/invalid case downstream — ingestion must not fail on it.
    """
    raw = (r.get("convictionscore") or "").strip()
    value = None
    if raw:
        try:
            d = Decimal(raw.replace(",", ""))
            value = float(d) if d.is_finite() else None
        except InvalidOperation:
            value = None  # malformed — non-blocking; diagnosed by accumulate evidence
    present = bool(raw)
    return {
        "conviction_score": value,
        "conviction_score_present": present,
        "conviction_score_source": (r.get("convictionscoresource") or "").strip() or None,
        "conviction_score_effective_date": (r.get("convictionscoreeffectivedate") or "").strip() or None,
        "conviction_score_version": (r.get("convictionscoreversion") or "").strip() or None,
    }


def parse_portfolio(path):
    """Portfolio: Instrument, Transactions, Qty Held, Avg Buy Price, Invested,
    Current Value, Allocation %, Gain/Loss %, Net Cashflow, XIRR,
    Holding Period (Days), First Date, Last Date."""
    rows = []
    for line, r in enumerate(_read(path), start=2):
        try:
            rows.append({
                "instrument": (r.get("instrument") or "").strip(),
                "transactions": _int(r.get("transactions")),
                "qty_held": _int(r.get("qtyheld")),
                "avg_buy_price": _dec(r.get("avgbuyprice")),
                "invested": _dec(r.get("invested")),
                "current_value": _dec(r.get("currentvalue")),
                "alloc_pct": _dec(r.get("allocation")),
                "gain_loss_pct": _dec(r.get("gainloss")),
                "net_cashflow": _dec(r.get("netcashflow")),
                "xirr": _dec(r.get("xirr")),
                "holding_period_days": _int(r.get("holdingperioddays")),
                "first_date": (r.get("firstdate") or "").strip(),
                "last_date": (r.get("lastdate") or "").strip(),
                # EMM-H3 / G2 (Q-i1, RD-010-AUTH-001) — optional DECLARED
                # conviction carrier pass-through. These columns may be absent
                # entirely (steady state until the Quality/Growth producer
                # supplies them). Defensive: a malformed numeric is carried as
                # present-but-None (diagnosed downstream, never raised here),
                # because Q-i2 requires a NON-BLOCKING diagnostic, not an
                # ingest failure. Exact contract field names are preserved.
                **_conviction_carrier(r),
            })
        except IngestError as exc:
            raise IngestError(f"line {line}: {exc}") from exc
    return rows


def parse_screener(path):
    """Fundamentals/valuation screener (subset of columns used by later phases)."""
    rows = []
    for line, r in enumerate(_read(path), start=2):
        try:
            rows.append({
                "name": (r.get("name") or "").strip(),
                "ticker": (r.get("ticker") or "").strip(),
                "sub_sector": (r.get("subsector") or "").strip(),
                "market_cap_cr": _dec(r.get("marketcap")),
                "close_price": _dec(r.get("closeprice")),
                "pe_ratio": _dec(r.get("peratio")),
                "pb_ratio": _dec(r.get("pbratio")),
                "peg_ratio": _dec(r.get("pegratio")),
                "roe": _dec(r.get("roe")),
                "roce": _dec(r.get("roce")),
                "eps_growth_1y_hist": _dec(r.get("1yhistoricalepsgrowth")),
                "eps_growth_1y_fwd": _dec(r.get("1yforwardepsgrowth")),
                "debt_equity": _dec(r.get("debttoequity")),
                "interest_coverage": _dec(r.get("interestcoverageratio")),
                "price_fcf": _dec(r.get("pricefcf")),
                "pledged_promoter_pct": _dec(r.get("pledgedpromoterholdings")),
                "sma_200": _dec(r.get("200dsma")),
                "pe_premium_vs_subsector": _dec(r.get("pepremiumvssubsector")),
                "pb_premium_vs_subsector": _dec(r.get("pbpremiumvssubsector")),
                "dii_change_3m": _dec(r.get("diiholdingchange3m")),
                "fii_change_3m": _dec(r.get("fiiholdingchange3m")),
            })
        except IngestError as exc:
            raise IngestError(f"line {line}: {exc}") from exc
    return rows


def parse_sold(path):
    """Sold-transactions ledger: Instrument, Qty, Sell Price, Sell Date.

    Closes the realized-gains gap (spec §9.3 / §8.4). Each row is a discrete sell
    fill, matched to buy lots FIFO by the tax module.
    """
    rows = []
    for line, r in enumerate(_read(path), start=2):
        try:
            rows.append({
                "instrument": (r.get("instrument") or "").strip(),
                "qty": _int(r.get("qty")),
                "sell_price": _dec(r.get("sellprice")),
                "sell_date": (r.get("selldate") or "").strip(),
            })
        except IngestError as exc:
            raise IngestError(f"line {line}: {exc}") from exc
    return rows
