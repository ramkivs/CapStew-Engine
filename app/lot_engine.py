"""Per-lot FIFO engine (Phase 1 core).

Indian capital-gains tax is per-lot, FIFO. Each buy fill is a discrete tax lot
with its own trade date, cost basis, days-held, and days-to-LTCG clock.

LTCG eligibility: a listed-equity lot is long-term when held **more than**
12 months — i.e. days_held > ltcg_period_days (365). Exactly 365 days is STCG.
"""
from decimal import Decimal

from .ingest import IngestError
from .normalize import parse_date
from .symbols import build_portfolio_ledger_link


def build_lots(ledger_rows, as_of, ltcg_period_days=365, inferred_notes=None):
    lots = []
    for seq, r in enumerate(ledger_rows):
        try:
            trade_date = parse_date(r["trade_date"], inferred_notes=inferred_notes)
            days_held = (as_of - trade_date).days
            qty = r["qty"]
            buy = r["buy_price"]
            ltp = r["ltp"]
            lots.append({
                "_seq": seq,
                "instrument": r["instrument"],
                "trade_date": trade_date,
                "qty": qty,
                "buy_price": buy,
                "ltp": ltp,
                "invested": qty * buy,
                "value": qty * ltp,
                "pnl": qty * (ltp - buy),
                "days_held": days_held,
                "days_to_ltcg": max(0, ltcg_period_days - days_held),
            })
        except IngestError:
            raise
        except (ValueError, TypeError) as exc:
            raise IngestError(
                f"ledger row {seq + 1} ({r.get('instrument') or 'unnamed'}): {exc}"
            ) from exc

    # Canonical order (determinism): instrument, then trade_date asc, buy_price asc,
    # then original row order. lot_id is PER-INSTRUMENT — a tax lot belongs to one
    # stock, so the oldest unsold lot of a holding is always its lot #1.
    lots.sort(key=lambda l: (l["instrument"], l["trade_date"], l["buy_price"], l["_seq"]))
    counter = {}
    for lot in lots:
        n = counter.get(lot["instrument"], 0) + 1
        counter[lot["instrument"]] = n
        lot["lot_id"] = n
        lot["pnl_pct"] = float(
            (lot["pnl"] / lot["invested"] * 100).quantize(Decimal("0.01"))
            if lot["invested"] else Decimal("0.0"))
        lot["ltcg_eligible"] = lot["days_held"] > ltcg_period_days
        lot.pop("_seq")
    return lots


def derive_positions(portfolio_rows, lots, tickers, screener_by_ticker, policy, link=None):
    """Roll lots up into positions, carrying portfolio-file fields through.

    `tickers`: name → ticker (or None). `screener_by_ticker`: ticker → screener row.

    CR-006: the position↔lots identity join uses the shared deterministic
    Portfolio↔Ledger link (exact match first, canonical 1↔1, collisions fail
    closed). When not supplied by the caller it is built here from the same
    raw names. Raw names are preserved: positions keep Portfolio names, lots
    keep Ledger names.
    """
    if link is None:
        link = build_portfolio_ledger_link(
            [p.get("instrument") for p in portfolio_rows],
            [l.get("instrument") for l in lots],
        )
    p2l = link["portfolio_to_ledger"]
    lots_by_name = {}
    for lot in lots:
        lots_by_name.setdefault(lot["instrument"], []).append(lot)

    def classify_bucket(mcap_cr):
        if mcap_cr is None:
            return None
        b = policy["buckets"]
        if mcap_cr >= b["large_cap_min_mcap_cr"]:
            return "large"
        if mcap_cr >= b["mid_cap_min_mcap_cr"]:
            return "mid"
        if mcap_cr >= b["small_cap_min_mcap_cr"]:
            return "small"
        return "micro"

    positions = []
    for i, pre in enumerate(portfolio_rows):
        missing = [k for k in ("avg_buy_price", "invested", "current_value") if pre.get(k) is None]
        if missing:
            raise IngestError(
                f"portfolio row {i + 1} ({pre.get('instrument') or 'unnamed'}): missing "
                f"{', '.join(missing)} — broker summary/TOTAL rows and column mismatches "
                "are not importable; remove them and keep one data row per holding"
            )
    for p in portfolio_rows:
        name = p["instrument"]
        ledger_name = p2l.get(name)
        name_lots = lots_by_name.get(ledger_name, []) if ledger_name is not None else []
        ticker = tickers.get(name)
        screener = screener_by_ticker.get(ticker) if ticker else None
        first = min((l["trade_date"] for l in name_lots), default=None)
        last = max((l["trade_date"] for l in name_lots), default=None)
        fundamentals = None
        if screener is not None:
            fundamentals = {k: (float(screener[k]) if screener.get(k) is not None else None)
                            for k in (
                                "pe_ratio", "pb_ratio", "peg_ratio", "roe", "roce",
                                "eps_growth_1y_hist", "eps_growth_1y_fwd", "debt_equity",
                                "interest_coverage", "price_fcf", "pe_premium_vs_subsector",
                                "pb_premium_vs_subsector", "dii_change_3m", "fii_change_3m",
                                "sma_200", "close_price", "market_cap_cr",
                            )}
            fundamentals["sub_sector"] = screener.get("sub_sector")
        positions.append({
            "instrument": name,
            "ticker": ticker,
            "bucket": classify_bucket(screener["market_cap_cr"]) if screener else None,
            "qty_held": p["qty_held"],
            "avg_buy_price": float(p["avg_buy_price"].quantize(Decimal("0.0001"))),
            "invested": float(p["invested"].quantize(Decimal("0.01"))),
            "current_value": float(p["current_value"].quantize(Decimal("0.01"))),
            "alloc_pct": float(p["alloc_pct"].quantize(Decimal("0.01"))) if p["alloc_pct"] is not None else None,
            "gain_pct": float(p["gain_loss_pct"].quantize(Decimal("0.01"))) if p["gain_loss_pct"] is not None else None,
            "net_cashflow": float(p["net_cashflow"].quantize(Decimal("0.01"))) if p["net_cashflow"] is not None else None,
            "first_date": first.isoformat() if first else (p["first_date"] or None),
            "last_date": last.isoformat() if last else (p["last_date"] or None),
            "lot_count": len(name_lots),
            "in_screener": screener is not None,
            "pledge_pct": float(screener["pledged_promoter_pct"]) if screener and screener["pledged_promoter_pct"] is not None else None,
            "fundamentals": fundamentals,
        })
    return positions
