"""Phase 1 pipeline: parsers → normalize → reconcile → per-lot FIFO → canonical payload.

This is the contract-tested output boundary. It deliberately contains NO
decision logic (gates/scoring/trim are Phase 2); the foundation payload is
what Phase 2 consumes and what the UI will eventually render.

CR-022 (F2-D1…D10): run_foundation additionally archives the raw input bytes,
the policy document snapshot and the canonical normalized foundation corpus
into the content-addressed snapshot archive (data/archive, gitignored) and
embeds a deterministic archive identity in payload provenance. Archiving
alters no computed value; separately, F2-D3 dual-timestamp resolution
introduces caller-declared data-age semantics (explicit/filename dates win
over the labelled mtime fallback), with staleness thresholds unchanged.
decide_all() remains a pure function of its inputs.
"""
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import archive, config
from .determinism import content_hash
from .ingest import parse_ledger, parse_portfolio, parse_screener
from .lot_engine import build_lots, derive_positions
from .symbols import build_portfolio_ledger_link, resolve_instrument
from .policy import get_ltcg_period_days, get_recon_tolerance, load_policy
from .reconcile import reconcile
from .schema import validate_decision_payload


def _f2(d: Decimal) -> float:
    return float(d.quantize(Decimal("0.01"))) if d is not None else None


def _file_as_of(path):
    import os
    from datetime import datetime as _dt
    mtime = os.path.getmtime(path)
    return _dt.fromtimestamp(mtime).strftime("%Y-%m-%d")


# CR-022 / F2-D3 — declared source-date extraction from filenames.
# Deterministic, documented conventions only (no fuzzy/heuristic inference):
#   YMD:  ..._2026-08-26... or ..._2026_08_26...
#   DMY:  ..._26-08-2026... or ..._26_08_2026...   (day-first export convention)
_YMD_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])(?!\d)")
_DMY_RE = re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])[-_](0[1-9]|1[0-2])[-_]((?:19|20)\d{2})(?!\d)")


def declared_as_of_from_filename(filename: str):
    """Return a date declared by the filename, or None when none is present."""
    m = _YMD_RE.search(filename)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DMY_RE.search(filename)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def resolve_slot_as_of(slot: str, path, declared: dict | None) -> dict:
    """F2-D3 dual-timestamp resolution for one source slot.

    Precedence: explicit user declaration > filename-declared date >
    upload-copy mtime (labelled fallback, never silently authoritative).
    Returns {"as_of": iso, "declared_source_as_of": iso|None, "as_of_source": ...}.
    Staleness thresholds are untouched; only the data-age INPUT changes.
    """
    declared_date = None
    source = None
    if declared and declared.get(slot):
        raw = declared[slot]
        declared_date = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        source = "declared_explicit"
    if declared_date is None:
        declared_date = declared_as_of_from_filename(Path(path).name)
        if declared_date is not None:
            source = "declared_filename"
    if declared_date is None:
        return {"as_of": _file_as_of(path), "declared_source_as_of": None,
                "as_of_source": "fallback_upload_mtime"}
    return {"as_of": declared_date.isoformat(),
            "declared_source_as_of": declared_date.isoformat(),
            "as_of_source": source}


def run_foundation(portfolio_path, screener_path, ledger_path, as_of=None, run_id=None,
                   declared_as_of=None):
    """Foundation payload for one ingestion event. Also archives (CR-022):

    raw bytes of all three slots + policy document snapshot are captured
    BEFORE parsing (idempotent content-addressed blobs), and one append-only
    manifest entry records the full provenance/linkage for the event.
    ``declared_as_of``: optional {slot: "YYYY-MM-DD"} explicit declarations
    (F2-D3 precedence: explicit > filename > labelled mtime fallback).
    """
    policy = load_policy()
    ltcg_days = get_ltcg_period_days(policy)
    tolerance = Decimal(str(get_recon_tolerance(policy)))
    as_of = as_of or date.today()
    run_id = run_id or f"run_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # CR-022 — snapshot archive hook: capture the exact received bytes and the
    # policy document BEFORE any parsing/normalization. Content-addressed and
    # idempotent: re-capturing identical bytes never mutates existing blobs.
    policy_record = archive.capture_policy()
    slot_paths = {"portfolio": portfolio_path, "screener": screener_path,
                  "ledger": ledger_path}
    slot_dates = {slot: resolve_slot_as_of(slot, path, declared_as_of)
                  for slot, path in slot_paths.items()}
    records = {slot: archive.capture_file(
        slot, path,
        declared_source_as_of=slot_dates[slot]["declared_source_as_of"],
        as_of_source=slot_dates[slot]["as_of_source"])
        for slot, path in slot_paths.items()}

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
            resolution = resolve_instrument(name, screener_rows=screener_rows)
            tickers[name] = resolution.ticker
            if not resolution.matched:
                warnings.append({
                    "code": "SYMBOL_UNMATCHED", "instrument": name,
                    "message": f"no ticker mapping for {name!r} — will not join to screener (partial-data path)",
                })

    # 3 — reconcile (G0)
    # CR-006: build the deterministic Portfolio↔Ledger identity link ONCE from
    # the raw names and share it with every G0 consumer (reconcile here,
    # derive_positions below). decide_all() rebuilds the identical link from
    # the raw names preserved in this payload — same builder, same result.
    name_link = build_portfolio_ledger_link(
        [p["instrument"] for p in portfolio_rows],
        [r["instrument"] for r in ledger_rows],
    )
    recon = reconcile(portfolio_rows, ledger_rows, tolerance, link=name_link)
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
    positions = derive_positions(portfolio_rows, lots, tickers, screener_by_ticker,
                                 policy, link=name_link)
    for p in positions:
        if not p["in_screener"]:
            warnings.append({
                "code": "PARTIAL_DATA", "instrument": p["instrument"],
                "message": f"{p['instrument']!r} not in screener universe — valuation/quality inputs unavailable",
            })

    # 6 — staleness (files older than N days vs as_of)
    # CR-022 / F2-D3: data-age comes from the resolved dual-timestamp
    # semantics (declared if available, else labelled mtime fallback).
    # Staleness THRESHOLDS are unchanged by CR-022.
    data_as_of = {
        "portfolio": slot_dates["portfolio"]["as_of"],
        "screener": slot_dates["screener"]["as_of"],
        "ledger": slot_dates["ledger"]["as_of"],
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
                key: {"as_of": slot_dates[key]["as_of"],
                      "declared_source_as_of": slot_dates[key]["declared_source_as_of"],
                      "as_of_source": slot_dates[key]["as_of_source"]}
                for key in ("portfolio", "screener", "ledger")
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

    # CR-022 — archive the canonical normalized FoundationPayload corpus
    # (F2-D5). The corpus deliberately contains NO hashes (engine input only),
    # so foundation_sha256 can feed the payload archive block with no
    # self-reference cycle; the payload content hash then covers the archive
    # block exactly like every other field ("sha256 of payload minus run_id").
    corpus = {
        "archive_blob_kind": "foundation",
        **{k: v for k, v in payload.items() if k != "run_id"},
    }
    foundation_sha = archive.store_foundation(corpus)
    payload["provenance"]["archive"] = archive.archive_identity(
        foundation_sha, policy_record["sha256"],
    )
    content = {k: v for k, v in payload.items() if k != "run_id"}
    payload["content_hash"] = content_hash(content)

    # CR-022 — finalize per-slot records and append the ingest manifest entry
    # (linkage: run_id ↔ raw blobs ↔ normalized foundation ↔ policy snapshot).
    row_counts = {"portfolio": len(portfolio_rows), "screener": len(screener_rows),
                  "ledger": len(ledger_rows)}
    warn_attr = _attribute_warning_codes(warnings)
    for slot, rec in records.items():
        rec["rows"] = row_counts[slot]
        rec["parse_status"] = "ok"
        rec["parse_warnings"] = warn_attr.get(slot, [])
    archive.append_ingest(
        run_id=run_id, run_as_of=as_of.isoformat(),
        input_hash=payload["content_hash"],
        files=[records["portfolio"], records["screener"], records["ledger"]],
        foundation_sha256=foundation_sha,
        policy_sha256=policy_record["sha256"],
        policy_version=policy.get("policy_version"),
    )
    return payload


def _attribute_warning_codes(warnings):
    """Documented per-slot attribution of engine warning codes for archive
    records (bookkeeping only — no new warnings are raised).

    STALENESS:       the slot named in the warning message.
    DATE_FORMAT_INFERRED: ledger (datetimes are normalized from ledger rows).
    SYMBOL_UNMATCHED: portfolio + ledger (raw names originate in either).
    PARTIAL_DATA:    portfolio (positions roll up from the portfolio file).
    Everything else (G0 recon codes): portfolio + ledger.
    """
    attr = {slot: [] for slot in ("portfolio", "screener", "ledger")}

    def add(slot, code):
        if code not in attr[slot]:
            attr[slot].append(code)

    for w in warnings:
        code = w["code"]
        if code == "DATE_FORMAT_INFERRED":
            add("ledger", code)
        elif code == "STALENESS":
            for slot in ("portfolio", "screener", "ledger"):
                if w.get("message", "").startswith(f"{slot} is "):
                    add(slot, code)
        elif code in ("SYMBOL_UNMATCHED", "PARTIAL_DATA"):
            add("portfolio", code)
            if code == "SYMBOL_UNMATCHED":
                add("ledger", code)
        else:
            add("portfolio", code)
            add("ledger", code)
    return attr


def run_engine(portfolio_path, screener_path, ledger_path, as_of=None, run_id=None,
               policy_overrides=None, hysteresis=None, declared_as_of=None):
    """Foundation + Phase 2 decision engine → DecisionPayload."""
    foundation = run_foundation(portfolio_path, screener_path, ledger_path,
                                as_of=as_of, run_id=run_id,
                                declared_as_of=declared_as_of)
    return decide_on_foundation(foundation, policy_overrides=policy_overrides,
                                hysteresis=hysteresis, apply_hysteresis=True)


def decide_on_foundation(foundation_payload, policy_overrides=None, hysteresis=None,
                         apply_hysteresis=False, history=None):
    """Recompute decisions on an existing foundation payload (what-if / run path)."""
    from .decision import decide_all
    payload = decide_all(foundation_payload, policy_overrides=policy_overrides,
                         hysteresis=hysteresis, apply_hysteresis=apply_hysteresis,
                         history=history)
    return validate_decision_payload(payload)


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
