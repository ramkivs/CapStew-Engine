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
    sizing_band_evidence,
    eligibility,
    opportunity_cost_evidence,
    position_sizing,
    quality_drift,
    tax_efficiency,
    technical_regime,
    valuation_stretch,
)
from .symbols import build_portfolio_ledger_link
from .trim import trim_s, trim_v

PRIORITY = {"EXIT": 0, "TRIM": 1, "HARVEST": 2}

# CR-023 / G-14 (H2-D4-A, authority-confirmed): informational breach when the
# summed allocation of a theme group is STRICTLY greater than 20%. Exactly 20%
# is NOT a breach. No per-theme bands; threshold is a module constant, not a
# new policy item.
THEME_BREACH_THRESHOLD_PCT = 20.0


def _theme_status(theme_alloc_pct):
    return "breach" if theme_alloc_pct > THEME_BREACH_THRESHOLD_PCT else "ok"


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
    sizing_evidence = sizing_band_evidence(pos.get("bucket"), policy, pos.get("alloc_pct"))
    opportunity_evidence = opportunity_cost_evidence(f)
    subs = {
        "position_sizing": position_sizing(pos.get("alloc_pct"), pos.get("bucket"), policy),
        "valuation_stretch": valuation_stretch(f),
        "quality_drift": quality_drift(f),
        "tax_efficiency": tax_efficiency(oldest_days_to_ltcg, any_ltcg),
        "opportunity_cost": opportunity_evidence["score"],
        "technical_regime": technical_regime(f),
    }
    quality_score = None
    if subs["quality_drift"] is not None:
        quality_score = 100 - subs["quality_drift"]
    return subs, quality_score, oldest_days_to_ltcg, any_ltcg, sizing_evidence, opportunity_evidence


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

    subs, quality_score, oldest_days_to_ltcg, any_ltcg, sizing_evidence, opportunity_evidence = _compute_subscores(pos, lots, policy)
    weights = policy["weights"]

    # Four-state data quality (proxy ≠ missing ≠ stale ≠ authoritative)
    quality = categorize_quality(subs, stale_files, position_sizing_basis=sizing_evidence["band_basis"])
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
            # CR-006 remediation: a persisted G0 NO-DECISION is an audit
            # status, not an established G4 hysteresis state. It stays visible
            # via `previous_run` (hv.get_prev above), but a holding that is no
            # longer G0-blocked must not spend N=2 persistence "leaving" G0 —
            # the current raw band establishes the current G4 state directly.
            # Ordinary G4↔G4 transitions (HOLD/WATCH/TRIM/HARVEST) still go
            # through the frozen asymmetric/N=2 state machine unchanged.
            if prev and prev.get("decision") == "NO-DECISION":
                hv.state[instrument] = {"decision": raw_band, "score": comp,
                                        "as_of": as_of.isoformat(), "pending": None}
            else:
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
        "bucket_basis": sizing_evidence["bucket_basis"],
        "band_basis": sizing_evidence["band_basis"],
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
            "stage1": {
                "gates_fired": gate["gates_fired"],
                "winning_gate": gate["winning_gate"],
                "tax_defer_suppressed": gate["tax_defer_suppressed"],
                "g2_allocation": {
                    "fired": "G2_allocation" in gate["gates_fired"],
                    "band_basis": sizing_evidence["band_basis"],
                    "band": sizing_evidence["band"],
                    "alloc_pct": sizing_evidence["alloc_pct"],
                    "cap_pct": sizing_evidence["cap_pct"],
                },
            },
            "stage2": {
                "composite_score": comp,
                "subscores": subs,
                "position_sizing": sizing_evidence,
                "opportunity_cost": opportunity_evidence,
            },
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
    # CR-006: rebuild the deterministic Portfolio↔Ledger identity link from the
    # preserved raw names in the foundation payload — the same shared builder
    # used by reconcile()/derive_positions(), so the join is identical.
    link = build_portfolio_ledger_link(
        [p.get("instrument") for p in positions],
        [l.get("instrument") for l in foundation["lots"]],
    )
    p2l = link["portfolio_to_ledger"]
    lots_by = {}
    for lot in foundation["lots"]:
        lots_by.setdefault(lot["instrument"], []).append(lot)
    # Expose canonically linked lots under their Portfolio name as well, so
    # consumers keyed by position name (e.g. tax.rank_candidates) use the same
    # identity link. Exact matches already share one key; only canonical links
    # with differing raw names need an alias entry.
    for p_name, l_name in p2l.items():
        if p_name != l_name and l_name in lots_by:
            lots_by[p_name] = lots_by[l_name]
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

    holdings = []
    for pos in positions:
        ledger_name = p2l.get(pos["instrument"])
        pos_lots = lots_by.get(ledger_name, []) if ledger_name is not None else []
        holdings.append(
            decide_instrument(pos, pos_lots, policy, total_value, as_of,
                              hv, stale_files, blocked, apply_hysteresis)
        )

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
    theme_row_src = {}
    for p in positions:
        # CR-023 / H2-D2/D3: group by the resolved per-position theme (manual
        # tag where assigned, else the sub_sector fallback). Legacy foundation
        # payloads (pre-CR-023) carry no theme fields — derive the historical
        # sub_sector key exactly as before. fundamentals.sub_sector itself is
        # never read as a substitute for a manual tag.
        t = p.get("theme")
        src = p.get("theme_source")
        if t is None:
            f = p.get("fundamentals")
            t = (f or {}).get("sub_sector") or "Unknown"
            src = "fallback_sub_sector"
        theme[t] = theme.get(t, 0.0) + (p.get("alloc_pct") or 0.0)
        theme_row_src.setdefault(t, set()).add(src or "fallback_sub_sector")
    theme_conc = [
        {"theme": k, "alloc_pct": round(v, 2), "status": _theme_status(v),
         # CR-023 additive: a row is 'manual' iff any member carried a manual
         # tag; fallback rows are labelled 'fallback_sub_sector' (H2-D3/D7).
         "source": "manual" if "manual" in theme_row_src.get(k, set())
                   else "fallback_sub_sector"}
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
        # NOTE (CR-022 discovery, reported not fixed): the "provenance" key is
        # duplicated in this dict literal (pre-existing latent defect; Python
        # keeps the second occurrence). Both occurrences are updated
        # IDENTICALLY so behavior cannot depend on which wins; removing the
        # duplication is left to a separate hygiene CR.
        "provenance": {
            "engine_version": config.ENGINE_VERSION,
            "normalization_version": config.NORMALIZATION_VERSION,
            "calculation_version": config.CALCULATION_VERSION,
            "policy_version": policy.get("policy_version"),
            "sources": {
                # CR-022 / F2-D3: declared-source-date labels pass through from
                # the foundation payload; legacy foundations default to the
                # historical mtime semantics, labelled as such.
                key: {"as_of": value,
                      "days_behind": (as_of - date.fromisoformat(value)).days,
                      "declared_source_as_of": foundation.get("provenance", {}).get("sources", {}).get(key, {}).get("declared_source_as_of"),
                      "as_of_source": foundation.get("provenance", {}).get("sources", {}).get(key, {}).get("as_of_source", "fallback_upload_mtime")}
                for key, value in foundation.get("data_as_of", {}).items()
                if key != "stale_files"
            },
            # CR-022 / F2-D4: payload-visible archive identity (content-derived).
            "archive": foundation.get("provenance", {}).get("archive"),
        },
        "provenance": {
            "engine_version": config.ENGINE_VERSION,
            "normalization_version": config.NORMALIZATION_VERSION,
            "calculation_version": config.CALCULATION_VERSION,
            "policy_version": policy.get("policy_version"),
            "sources": {
                key: {"as_of": value,
                      "days_behind": (as_of - date.fromisoformat(value)).days,
                      "declared_source_as_of": foundation.get("provenance", {}).get("sources", {}).get(key, {}).get("declared_source_as_of"),
                      "as_of_source": foundation.get("provenance", {}).get("sources", {}).get(key, {}).get("as_of_source", "fallback_upload_mtime")}
                for key, value in foundation.get("data_as_of", {}).items()
                if key != "stale_files"
            },
            "archive": foundation.get("provenance", {}).get("archive"),
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
