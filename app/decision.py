"""Phase 2 decision engine: FoundationPayload → DecisionPayload.

Order of operations per Freeze: G0 (reconcile, upstream) → G1 → G2 → G3 → G4
(composite, eligibility-capped, hysteresis-gated) → confidence → trim → audit.
No decision logic exists in the browser; this module is the authority.
"""
from datetime import date, timedelta

from . import config
from .behavior import averaging_flag, parse_lots_for_behavior
from .confidence import compute_penalties, confidence_from_penalties
from .determinism import content_hash
from .gates import evaluate_gates
from .hysteresis import Hysteresis
from .policy import load_policy
from .scoring import (
    WEIGHT_KEYS,
    apply_eligibility_caps,
    band_of,
    categorize_quality,
    composite,
    eligibility,
    opportunity_cost,
    position_sizing,
    quality_drift,
    tax_efficiency,
    technical_regime,
    valuation_stretch,
)
from .trim import trim_s, trim_v

PRIORITY = {"EXIT": 0, "TRIM": 1, "HARVEST": 2}


def _merge_policy(base, overrides):
    if not overrides:
        return base
    p = dict(base)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(p.get(k), dict):
            p[k] = {**p[k], **v}
        else:
            p[k] = v
    return p


def _compute_subscores(pos, lots, policy):
    f = pos.get("fundamentals")
    oldest_days_to_ltcg = lots[0]["days_to_ltcg"] if lots else None
    any_ltcg = any(l["ltcg_eligible"] for l in lots)
    subs = {
        "position_sizing": position_sizing(pos.get("alloc_pct"), pos.get("bucket"), policy),
        "valuation_stretch": valuation_stretch(f),
        "quality_drift": quality_drift(f),
        "tax_efficiency": tax_efficiency(oldest_days_to_ltcg, any_ltcg),
        "opportunity_cost": opportunity_cost(f),
        "technical_regime": technical_regime(f),
    }
    quality_score = None
    if subs["quality_drift"] is not None:
        quality_score = 100 - subs["quality_drift"]
    return subs, quality_score, oldest_days_to_ltcg, any_ltcg


def _drivers(gate, subs, weights, decision_path, caps_note):
    drivers = []
    if gate["decision"] is not None:
        if gate["winning_gate"] == "G1":
            drivers.append(f"HARD GATE G1: thesis/governance break — exit regardless of P&L")
        elif gate["winning_gate"] == "G2":
            drivers.append("HARD GATE G2: allocation/rebalance breach — trim to cap (risk caps are never tax-deferred)")
        elif gate["winning_gate"] == "G3":
            drivers.append("G3 tax defer: near LTCG and valuation not stretched — hold until LTCG")
    if gate["tax_defer_suppressed"]:
        drivers.append("G3 defer suppressed: valuation stretched ≥ 85 — do not defer for tax alone")
    ranked = sorted(
        ((k, v) for k, v in subs.items() if v is not None),
        key=lambda kv: kv[1] * weights.get(kv[0], 0), reverse=True,
    )
    for k, v in ranked[:3]:
        label = k.replace("_", " ")
        drivers.append(f"{label}: sub-score {v} (weight {weights.get(k, 0)}%)")
    if caps_note:
        drivers.append(f"Eligibility cap: {caps_note}")
    return drivers


def _review_date(decision, conf, gate_fired, as_of, flag):
    if gate_fired:
        days = 1
    elif decision in ("TRIM", "HARVEST", "EXIT"):
        days = 7
    elif conf is not None and conf >= 70:
        days = 90
    else:
        days = 30
    if flag:
        days = min(days, 14)
    return (as_of + timedelta(days=days)).isoformat()


def _nod(pos, as_of):
    return {
        "instrument": pos["instrument"], "ticker": pos.get("ticker"), "bucket": pos.get("bucket"),
        "decision": "NO-DECISION", "composite_score": None, "confidence": None,
        "confidence_breakdown": None, "subscores": None,
        "stage1": {"fired": False, "gates_fired": [], "winning_gate": "G0", "tax_defer_suppressed": False},
        "evidence": None, "reason_tree": {"decision_path": "G0 → NO-DECISION (reconciliation blocked)"},
        "primary_drivers": ["G0: cost-basis reconciliation failed — no decision on untrusted data"],
        "watch_flags": [], "behavioral_flags": ["none"], "trim": None, "tax_status": None,
        "why_now": {"primary_trigger": "data integrity"}, "previous_run": None,
        "next_review_date": as_of.isoformat(),
    }


def decide_instrument(pos, lots, policy, total_value, as_of, hv, stale_files, blocked, apply_hysteresis):
    instrument = pos["instrument"]
    if instrument in blocked:
        return _nod(pos, as_of)

    subs, quality_score, oldest_days_to_ltcg, any_ltcg = _compute_subscores(pos, lots, policy)
    weights = policy["weights"]

    # Four-state data quality (proxy ≠ missing ≠ stale ≠ authoritative)
    quality = categorize_quality(subs, stale_files)
    proxy_count = sum(1 for v in quality.values() if v == "proxy")
    stale_cat_count = sum(1 for v in quality.values() if v == "stale")

    # Stage 1 gates
    gate = evaluate_gates(
        alloc_pct=pos.get("alloc_pct"), bucket=pos.get("bucket"),
        pledge_pct=pos.get("pledge_pct"), quality_score=quality_score,
        days_to_ltcg=oldest_days_to_ltcg, valuation_subscore=subs["valuation_stretch"],
        policy=policy,
    )

    # Stage 2 composite (computed for reporting even when a gate wins)
    comp = composite(subs, weights)
    ev = eligibility(subs, weights) if comp is not None else None

    prev = hv.get_prev(instrument)
    caps_note = None

    if gate["decision"] is not None:
        decision = hv.bypass(instrument, gate["decision"], comp if comp is not None else 0.0, as_of)
        trim_mode = gate["trim_mode"]
    elif comp is None:
        decision, caps_note = "WATCH", "no scorable categories available"
        trim_mode = None
    else:
        raw_band = band_of(comp)
        decision = raw_band
        if apply_hysteresis:
            decision = hv.apply(instrument, raw_band, comp, as_of)
        decision, caps_note = apply_eligibility_caps(decision, ev["tier"], ev["critical_categories_missing"])
        trim_mode = "V" if decision == "TRIM" else None

    # Trim plan
    trim = None
    if decision == "TRIM" and lots:
        trim = trim_s(pos, lots, policy, total_value) if trim_mode == "S" else trim_v(pos, lots, policy, total_value)

    # Behavioral guardrail
    flag = averaging_flag(parse_lots_for_behavior(lots)) if lots else None

    # Confidence
    conf = None
    breakdown = None
    if comp is not None and ev is not None:
        penalties = compute_penalties(subs, ev["coverage"], comp, stale_cat_count, proxy_count)
        conf = confidence_from_penalties(penalties)
        if ev["tier"] == "ADVISORY":
            conf = min(conf, 55)
        breakdown = {k: v for k, v in penalties.items()}
        breakdown["confidence"] = conf

    gate_fired = gate["decision"] is not None

    decision_path = "G0 → NO-DECISION"
    if gate["decision"] is not None:
        decision_path = f"{gate['winning_gate']} → {decision}" + (f" (mode {trim_mode})" if trim_mode else "")
    elif decision == "HARVEST":
        decision_path = f"G4 → HARVEST (composite {comp})"
    elif decision == "TRIM":
        decision_path = f"G4 → TRIM (composite {comp}, mode V)"
    else:
        decision_path = f"G4 → {decision} (composite {comp})"

    drivers = _drivers(gate, subs, weights, decision_path, caps_note)
    if flag == "averaging_block_adds":
        drivers.append("Behavioral: averaging into losses — re-underwrite thesis before any further add")
        drivers.append("Behavioral: block further adds without written re-underwrite")

    watch_flags = []
    if flag:
        watch_flags.append(f"Averaging-into-losses: {len(lots)} buy lots, net {sum(l['pnl'] for l in lots):.0f} — confirm thesis before adding")
    if not pos.get("in_screener", True):
        watch_flags.append("Not in fundamentals screener — partial-data Stage 2 score")

    data_completeness = {k: subs.get(k) is not None for k in WEIGHT_KEYS}

    return {
        "instrument": instrument,
        "ticker": pos.get("ticker"),
        "bucket": pos.get("bucket"),
        "alloc_pct": pos.get("alloc_pct"),
        "gain_pct": pos.get("gain_pct"),
        "current_value": pos.get("current_value"),
        "qty_held": pos.get("qty_held"),
        "pledge_pct": pos.get("pledge_pct"),
        "decision": decision,
        "composite_score": comp,
        "confidence": conf,
        "confidence_breakdown": breakdown,
        "subscores": subs,
        "stage1": {
            "fired": gate_fired,
            "gates_fired": gate["gates_fired"],
            "winning_gate": gate["winning_gate"],
            "tax_defer_suppressed": gate["tax_defer_suppressed"],
        },
        "evidence": ev,
        "primary_drivers": drivers,
        "watch_flags": watch_flags,
        "behavioral_flags": [flag or "none"],
        "trim": trim,
        "tax_status": {
            "mixed_ltcg": any_ltcg and not all(l["ltcg_eligible"] for l in lots) if lots else False,
            "oldest_lot_days_to_ltcg": oldest_days_to_ltcg,
            "ltcg_eligible_lots": sum(1 for l in lots if l["ltcg_eligible"]),
        },
        "data_completeness": data_completeness,
        "data_quality": quality,
        "lots": lots,
        "behavioral": {
            "flag": flag or "none",
            "requires_reunderwrite": flag == "averaging_block_adds",
            "blocks_adds": flag == "averaging_block_adds",
        },
        "reason_tree": {
            "decision_path": decision_path,
            "stage1": {"gates_fired": gate["gates_fired"], "winning_gate": gate["winning_gate"],
                       "tax_defer_suppressed": gate["tax_defer_suppressed"]},
            "stage2": {"composite_score": comp, "subscores": subs},
        },
        "why_now": {
            "primary_trigger": (f"{gate['winning_gate']} — {gate['gates_fired'][0] if gate['gates_fired'] else ''}"
                               if gate_fired else f"composite {comp} → {band_of(comp) if comp is not None else '—'} band"),
            "contributors": [
                {"label": k.replace("_", " "), "value": v, "weight": weights.get(k, 0)}
                for k, v in sorted(((k, v) for k, v in subs.items() if v is not None),
                                   key=lambda kv: kv[1] * weights.get(kv[0], 0), reverse=True)[:3]
            ],
        },
        "previous_run": prev,
        "next_review_date": _review_date(decision, conf, gate_fired, as_of, flag),
    }


def decide_all(foundation, policy_overrides=None, hysteresis=None, apply_hysteresis=True, history=None):
    policy = _merge_policy(load_policy(), policy_overrides)
    as_of = date.fromisoformat(foundation["as_of"])
    positions = foundation["positions"]
    lots_by = {}
    for lot in foundation["lots"]:
        lots_by.setdefault(lot["instrument"], []).append(lot)
    total_value = sum(p["current_value"] for p in positions)
    blocked = {
        i.get("instrument") for i in foundation["reconciliation"]["issues"]
        if i.get("severity") == "blocking"
    }
    stale_files = foundation.get("data_as_of", {}).get("stale_files", [])
    hv = hysteresis or Hysteresis()
    if history:
        for inst, st in history.items():
            hv.seed(inst, st.get("decision"), st.get("composite_score"), st.get("as_of"))

    holdings = [
        decide_instrument(pos, lots_by.get(pos["instrument"], []), policy, total_value, as_of,
                          hv, stale_files, blocked, apply_hysteresis)
        for pos in positions
    ]

    dist = {}
    for h in holdings:
        dist[h["decision"]] = dist.get(h["decision"], 0) + 1

    def reason(h):
        if h["decision"] == "EXIT":
            return "RISK"
        if h["decision"] == "TRIM":
            return "SIZING" if (h["trim"] and h["trim"].get("mode") == "S") else "VALUATION"
        return "VALUATION"

    queue = [
        {"rank": i + 1, "instrument": h["instrument"], "decision": h["decision"],
         "reason": reason(h), "score": h["composite_score"]}
        for i, h in enumerate(sorted(
            (h for h in holdings if h["decision"] in ("EXIT", "TRIM", "HARVEST")),
            key=lambda h: (PRIORITY.get(h["decision"], 9), -(h["composite_score"] or 0)),
        ))
    ]

    theme = {}
    for p in positions:
        f = p.get("fundamentals")
        sub = (f or {}).get("sub_sector") or "Unknown"
        theme[sub] = theme.get(sub, 0.0) + (p.get("alloc_pct") or 0.0)
    theme_conc = [
        {"theme": k, "alloc_pct": round(v, 2), "status": "breach" if v > 20 else "ok"}
        for k, v in sorted(theme.items(), key=lambda kv: -kv[1])
    ]

    # Tax-aware sequencing (Phase 3A): rank TRIM/HARVEST candidates by tax drag.
    from .tax import rank_candidates
    tax_sequencing = rank_candidates(
        [h for h in holdings if h["decision"] in ("TRIM", "HARVEST")], lots_by)

    payload = {
        "run_id": foundation["run_id"],
        "as_of": foundation["as_of"],
        "engine_version": config.ENGINE_VERSION,
        "policy_version": policy.get("policy_version"),
        "input_hash": foundation["content_hash"],
        "provenance": {
            "engine_version": config.ENGINE_VERSION,
            "normalization_version": config.NORMALIZATION_VERSION,
            "calculation_version": config.CALCULATION_VERSION,
            "policy_version": policy.get("policy_version"),
            "sources": {
                key: {"as_of": value,
                      "days_behind": (as_of - date.fromisoformat(value)).days}
                for key, value in foundation.get("data_as_of", {}).items()
                if key != "stale_files"
            },
        },
        "provenance": {
            "engine_version": config.ENGINE_VERSION,
            "normalization_version": config.NORMALIZATION_VERSION,
            "calculation_version": config.CALCULATION_VERSION,
            "policy_version": policy.get("policy_version"),
            "sources": {
                key: {"as_of": value,
                      "days_behind": (as_of - date.fromisoformat(value)).days}
                for key, value in foundation.get("data_as_of", {}).items()
                if key != "stale_files"
            },
        },
        "portfolio_summary": {
            "total_value": round(total_value, 2),
            "holdings_count": len(holdings),
            "decision_distribution": dist,
            "stage1_gates_fired": sum(1 for h in holdings if h["stage1"]["fired"]),
            "tax": {
                "fy": "2026-27", "provisional": True,
                "ltcg_booked": 0.0, "ltcg_exemption": 125000.0, "ltcg_headroom": 125000.0,
                "stcg_booked": 0.0, "stcl_harvestable": 0.0,
                "note": "open positions only — realized-gains export is a gap (spec §9.3)",
            },
        },
        "holdings": holdings,
        "portfolio_layer": {
            "action_queue": queue,
            "theme_concentration": theme_conc,
            "tax_sequencing": tax_sequencing,
        },
        "warnings": foundation["warnings"],
    }
    payload["content_hash"] = content_hash({k: v for k, v in payload.items() if k != "run_id"})
    return payload
