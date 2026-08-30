"""ACCUMULATE eligibility — EMM-H3 / G2 (CR-030 scope).

Pure evaluator for the frozen §1.1 six-clause conjunction
(methodology-freeze-v1.md "ACCUMULATE trigger rule [FROZEN]"). This module is
EVALUATION-ONLY (ADR-style purity): it never computes conviction, never reads
policy or files, never mutates anything. All inputs are passed in as data.

Authority-pinned contract (verbatim lineage):
- RD-004 / G1: ``high_threshold`` value lives in policy.yaml (70 by authority,
  installed as inert policy-data under G1); it is NEVER hard-coded here.
- RD-009 / Q-i1 (RD-010-AUTH-001): conviction_score is a DECLARED per-holding
  run-input field (carrier = per-holding run-input/holding record) with the
  provenance fields source / effective_date / version. ACCUMULATE consumes the
  declared value only — never computes, defaults, proxies, or infers it.
- Q-i2 (RD-010-AUTH-001): missing/malformed/invalid conviction input or
  provenance => NOT eligible + explicit non-blocking reason.
- Q-i3 (RD-010-AUTH-001): C-A production screener basis only
  (pe_premium_vs_subsector / pb_premium_vs_subsector); the frozen
  "premium <= 0" condition is satisfied iff (ratio - 1.0) <= 0; BOTH
  applicable ratios when both exist; the available one when only one exists;
  FALSE when neither exists. No MOS. No G-04 own-history median.

Reason codes (first failure wins, in frozen clause order):
  decision_not_hold -> high_threshold_unavailable -> conviction_missing ->
  conviction_malformed -> conviction_provenance_missing ->
  conviction_provenance_invalid -> conviction_below_threshold ->
  allocation_not_under_band -> valuation_inputs_missing ->
  valuation_stretched -> stage1_gate_fired -> averaging_flag_present
Eligible iff no clause failed (reason is None).
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from numbers import Real

__all__ = ["evaluate_accumulate"]


def _is_num(v) -> bool:
    """Finite non-bool real number (strings/bools are invalid, not numbers)."""
    return isinstance(v, Real) and not isinstance(v, bool) and isfinite(v)


def _iso_date_ok(v) -> bool:
    if not isinstance(v, str) or not v.strip():
        return False
    try:
        date.fromisoformat(v.strip())
    except ValueError:
        return False
    return True


def evaluate_accumulate(*, decision, conviction_score, conviction_present,
                        conviction_source, conviction_effective_date,
                        conviction_version, high_threshold, alloc_pct, band_low,
                        pe_premium, pb_premium, gates_fired, averaging_flag):
    """Frozen §1.1 six-clause conjunction. Returns {"eligible": bool, "reason": str|None}."""
    fail = None

    # Clause 1 — decision == HOLD (Q: final stabilized decision, never a tag on any other state).
    if decision != "HOLD":
        fail = "decision_not_hold"

    # Clause 2 — conviction_score >= high_threshold (declared input only; threshold = policy-data).
    elif not _is_num(high_threshold):
        # Policy lacks the key/value — never assumed, never hard-coded.
        fail = "high_threshold_unavailable"
    elif not conviction_present:
        fail = "conviction_missing"
    elif not _is_num(conviction_score):
        fail = "conviction_malformed"
    elif any(v is None or (isinstance(v, str) and not v.strip())
             for v in (conviction_source, conviction_effective_date, conviction_version)):
        fail = "conviction_provenance_missing"
    elif not _iso_date_ok(conviction_effective_date):
        fail = "conviction_provenance_invalid"
    elif not (conviction_score >= high_threshold):
        fail = "conviction_below_threshold"

    # Clause 3 — allocation_pct < target_band_low.
    elif band_low is None or not _is_num(alloc_pct) or not (alloc_pct < band_low):
        fail = "allocation_not_under_band"

    else:
        # Clause 4 — valuation not stretched (Q-i3 / RD-009 C-A mapping).
        conds = []
        if _is_num(pe_premium):
            conds.append((pe_premium - 1.0) <= 0)
        if _is_num(pb_premium):
            conds.append((pb_premium - 1.0) <= 0)
        if not conds:
            fail = "valuation_inputs_missing"
        elif not all(conds):
            fail = "valuation_stretched"

        # Clause 5 — no Stage-1 gate fired (any recorded firing counts).
        elif gates_fired:
            fail = "stage1_gate_fired"

        # Clause 6 — no averaging-into-losses flag (any non-None flag excludes).
        elif averaging_flag:
            fail = "averaging_flag_present"

    return {"eligible": fail is None, "reason": fail}
