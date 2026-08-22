"""Phase 1 pipeline: parsers → normalize → reconcile → per-lot FIFO → canonical payload.

This is the contract-tested output boundary. It deliberately contains NO
decision logic (gates/scoring/trim are Phase 2); the foundation payload is
what Phase 2 consumes and what the UI will eventually render.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from . import config
from .determinism import content_hash
from .ingest import parse_ledger, parse_portfolio, parse_screener
from .lot_engine import build_lots, derive_positions
from .normalize import map_name_to_ticker
from .policy import get_ltcg_period_days, get_recon_tolerance, load_policy
from .reconcile import reconcile


def _f2(d: Decimal) -> float:
    return float(d.quantize(Decimal("0.01"))) if d is not None else None


def _file_as_of(path):
    import os
    from datetime import datetime as _dt
    mtime = os.path.getmtime(path)
    return _dt.fromtimestamp(mtime).strftime("%Y-%m-%d")


def run_foundation(portfolio_path, screener_path, ledger_path, as_of=None, run_id=None):
    policy = load_policy()
    ltcg_days = get_ltcg_period_days(policy)
    tolerance = Decimal(str(get_recon_tolerance(policy)))
    as_of = as_of or date.today()
    run_id = run_id or f"run_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 1 — ingest
    ledger_rows = parse_ledger(ledger_path)
    portfolio_rows = parse_portfolio(portfolio_path)
    screener_rows = parse_screener(screener_path)

    # 2 — normalize (symbol map; dates are normalized during lot building)
    tickers = {}
    warnings = []
    for r in ledger_rows + portfolio_rows:
        name = r["instrument"]
        if name not in tickers:
            ticker, matched = map_name_to_ticker(name)
            tickers[name] = ticker
            if not matched:
                warnings.append({
                    "code": "SYMBOL_UNMATCHED", "instrument": name,
                    "message": f"no ticker mapping for {name!r} — will not join to screener (partial-data path)",
                })

    # 3 — reconcile (G0)
    recon = reconcile(portfolio_rows, ledger_rows, tolerance)
    for issue in recon["issues"]:
        if issue["severity"] == "blocking":
            warnings.append({
                "code": issue["code"], "instrument": issue.get("instrument"),
                "message": issue["message"],
            })

    # 4 — per-lot FIFO engine
    inferred = []
    lots = build_lots(ledger_rows, as_of, ltcg_days, inferred_notes=inferred)
    for lot in lots:
        lot["ticker"] = tickers.get(lot["instrument"])
    if inferred:
        warnings.append({"code": "DATE_FORMAT_INFERRED", "message": "; ".join(inferred[:5])})

    # 5 — positions (roll-up, screener join)
    screener_by_ticker = {s["ticker"]: s for s in screener_rows}
    positions = derive_positions(portfolio_rows, lots, tickers, screener_by_ticker, policy)
    for p in positions:
        if not p["in_screener"]:
            warnings.append({
                "code": "PARTIAL_DATA", "instrument": p["instrument"],
                "message": f"{p['instrument']!r} not in screener universe — valuation/quality inputs unavailable",
            })

    # 6 — staleness (files older than N days vs as_of)
    data_as_of = {
        "portfolio": _file_as_of(portfolio_path),
        "screener": _file_as_of(screener_path),
        "ledger": _file_as_of(ledger_path),
    }
    stale_files = []
    for key, file_as_of in data_as_of.items():
        days_behind = (as_of - date.fromisoformat(file_as_of)).days
        threshold = config.STALENESS_DAYS_LEDGER if key == "ledger" else config.STALENESS_DAYS_VALUATION
        if days_behind > threshold:
            stale_files.append(key)
            warnings.append({
                "code": "STALENESS", "instrument": None,
                "message": f"{key} is {days_behind} days behind as-of ({threshold}+ allowed)",
            })
    data_as_of["stale_files"] = stale_files

    # 7 — canonical payload + determinism hash
    payload = {
        "run_id": run_id,
        "engine_version": config.ENGINE_VERSION,
        "as_of": as_of.isoformat(),
        "provenance": {
            "engine_version": config.ENGINE_VERSION,
            "normalization_version": config.NORMALIZATION_VERSION,
            "calculation_version": config.CALCULATION_VERSION,
            "policy_version": policy.get("policy_version"),
            "sources": {
                key: {"as_of": file_as_of}
                for key, file_as_of in data_as_of.items() if key != "stale_files"
            },
        },
        "data_as_of": data_as_of,
        "reconciliation": {
            "ok": recon["ok"],
            "blocking": recon["blocking"],
            "warnings": recon["warnings"],
            "checks": recon["checks"],
            "issues": recon["issues"],
        },
        "positions": positions,
        "lots": [
            {
                "lot_id": l["lot_id"],
                "instrument": l["instrument"],
                "ticker": l["ticker"],
                "trade_date": l["trade_date"].isoformat(),
                "qty": l["qty"],
                "buy_price": float(l["buy_price"]),
                "ltp": float(l["ltp"]),
                "invested": _f2(l["invested"]),
                "value": _f2(l["value"]),
                "pnl": _f2(l["pnl"]),
                "pnl_pct": l["pnl_pct"],
                "days_held": l["days_held"],
                "days_to_ltcg": l["days_to_ltcg"],
                "ltcg_eligible": l["ltcg_eligible"],
            }
            for l in lots
        ],
        "warnings": warnings,
    }
    content = {k: v for k, v in payload.items() if k != "run_id"}
    payload["content_hash"] = content_hash(content)
    return payload


def run_engine(portfolio_path, screener_path, ledger_path, as_of=None, run_id=None,
               policy_overrides=None, hysteresis=None):
    """Foundation + Phase 2 decision engine → DecisionPayload."""
    foundation = run_foundation(portfolio_path, screener_path, ledger_path,
                                as_of=as_of, run_id=run_id)
    return decide_on_foundation(foundation, policy_overrides=policy_overrides,
                                hysteresis=hysteresis, apply_hysteresis=True)


def decide_on_foundation(foundation_payload, policy_overrides=None, hysteresis=None,
                         apply_hysteresis=False, history=None):
    """Recompute decisions on an existing foundation payload (what-if / run path)."""
    from .decision import decide_all
    return decide_all(foundation_payload, policy_overrides=policy_overrides,
                      hysteresis=hysteresis, apply_hysteresis=apply_hysteresis,
                      history=history)


def compute_tax_year(foundation_payload, sold_path, fy="2026-27"):
    """Phase 3A: realise a sold-transactions ledger against the open lots (FIFO).

    Returns {"realized": [...], "summary": {...}, "open_positions": {...}}.
    The summary is authoritative once a sold ledger exists; open_positions is the
    unrealised LTCG/STCG/LTCL/STCL split of the current book.
    """
    from datetime import date as _date

    from .ingest import parse_sold
    from .normalize import parse_date
    from .tax import LTCG_EXEMPTION, match_sells_fifo, tax_year_summary, unrealized_split

    sells_raw = parse_sold(sold_path)
    lots_by = {}
    for l in foundation_payload["lots"]:
        lots_by.setdefault(l["instrument"], []).append({
            "lot_id": l["lot_id"], "qty": l["qty"],
            "buy_price": l["buy_price"], "ltp": l["ltp"],
            "trade_date": _date.fromisoformat(l["trade_date"]),
            "ltcg_eligible": l["ltcg_eligible"],
        })

    sells_by = {}
    for s in sells_raw:
        sells_by.setdefault(s["instrument"], []).append({
            "instrument": s["instrument"], "qty": s["qty"],
            "sell_price": s["sell_price"],
            "sell_date": parse_date(s["sell_date"]),
        })

    realized = []
    for inst, sells in sells_by.items():
        realized += match_sells_fifo(lots_by.get(inst, []), sells)

    summary = tax_year_summary(realized, exemption=LTCG_EXEMPTION, fy=fy)

    open_positions = {}
    for inst, lots in lots_by.items():
        open_positions[inst] = unrealized_split(lots)

    realized_clean = [
        {"instrument": r["instrument"], "lot_id": r["lot_id"],
         "sell_date": r["sell_date"].isoformat(), "qty": float(r["qty"]),
         "buy_price": float(r["buy_price"]), "sell_price": float(r["sell_price"]),
         "gain": float(r["gain"].quantize(Decimal("0.01"))),
         "holding_days": r["holding_days"], "type": r["type"]}
        for r in realized
    ]
    return {"realized": realized_clean, "summary": summary,
            "open_positions": open_positions}
