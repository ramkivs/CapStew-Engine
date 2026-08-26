"""CSV parsers for the three exports (Phase 1).

Each parser normalizes column names to a canonical lowercased alphanumeric key
so it tolerates the exports' quirks: "Qty." (trailing dot), "Curr value"
(lowercase v), "Allocation %", "Holding Period (Days)", etc.
"""
import csv
import re
from decimal import Decimal, InvalidOperation

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


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        norm = {orig: _norm_key(orig) for orig in reader.fieldnames}
        return [{norm[k]: v for k, v in row.items() if k in norm} for row in reader]


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
