"""G2 / EMM-H3 — ACCUMULATE tag tests (CR-030 scope).

Pins the frozen §1.1 six-clause conjunction and the authority-pinned
resolutions (RD-004 U-2=70/policy; RD-007/RD-009 U-3 C-A basis + scale
mapping; RD-009/RD-010-AUTH-001 U-1 carrier fields + Q-i1/Q-i2/Q-i3).
The evaluator consumes DECLARED inputs only and never computes conviction;
high_threshold comes from policy, never code.
"""
import copy
from datetime import date

from app.accumulate import evaluate_accumulate
from app.decision import decide_all
from app.pipeline import run_foundation, decide_on_foundation
from app.policy import load_policy
from app.schema import validate_decision_payload

AS_OF = date(2026, 8, 29)

OK = dict(
    decision="HOLD",
    conviction_score=72.5,
    conviction_present=True,
    conviction_source="QualityGrowth-Engine",
    conviction_effective_date="2026-08-20",
    conviction_version="v3",
    high_threshold=70,
    alloc_pct=3.5,
    band_low=4.0,
    pe_premium=0.9,
    pb_premium=0.9,
    gates_fired=[],
    averaging_flag=None,
)


def ev(**over):
    ctx = dict(OK)
    ctx.update(over)
    return evaluate_accumulate(**ctx)


# ---------- six-clause truth table ----------
def test_eligible_when_all_clauses_true():
    r = ev()
    assert r == {"eligible": True, "reason": None}


def test_decision_not_hold_excludes():
    for d in ("WATCH", "TRIM", "HARVEST", "EXIT", "NO-DECISION"):
        r = ev(decision=d)
        assert r["eligible"] is False and r["reason"] == "decision_not_hold"


def test_high_threshold_unavailable():
    r = ev(high_threshold=None)
    assert r["eligible"] is False and r["reason"] == "high_threshold_unavailable"


def test_conviction_missing():
    r = ev(conviction_present=False, conviction_score=None,
           conviction_source=None, conviction_effective_date=None, conviction_version=None)
    assert r["eligible"] is False and r["reason"] == "conviction_missing"


def test_conviction_malformed_value():
    for bad in (None, "high", True):
        r = ev(conviction_score=bad)  # present marker True, value unusable
        assert r["eligible"] is False and r["reason"] == "conviction_malformed", bad


def test_conviction_provenance_missing():
    for field in ("conviction_source", "conviction_effective_date", "conviction_version"):
        r = ev(**{field: None})
        assert r["eligible"] is False and r["reason"] == "conviction_provenance_missing", field
    r = ev(conviction_source="")
    assert r["reason"] == "conviction_provenance_missing"


def test_conviction_provenance_invalid_date():
    r = ev(conviction_effective_date="29-08-2026")
    assert r["eligible"] is False and r["reason"] == "conviction_provenance_invalid"


def test_threshold_boundary_69_70_71():
    assert ev(conviction_score=69)["reason"] == "conviction_below_threshold"
    assert ev(conviction_score=70)["eligible"] is True   # inclusive: >= threshold
    assert ev(conviction_score=71)["eligible"] is True


def test_allocation_at_or_above_band_low():
    assert ev(alloc_pct=4.0)["reason"] == "allocation_not_under_band"  # strict <
    assert ev(alloc_pct=None)["reason"] == "allocation_not_under_band"
    assert ev(alloc_pct=3.5, band_low=None)["reason"] == "allocation_not_under_band"
    assert ev(alloc_pct=3.99)["eligible"] is True


# ---------- Q-i3 valuation branch (C-A, ratio - 1.0 <= 0) ----------
def test_valuation_pe_only():
    assert ev(pb_premium=None, pe_premium=0.9)["eligible"] is True
    assert ev(pb_premium=None, pe_premium=1.0)["eligible"] is True   # <= 1.0 ok
    r = ev(pb_premium=None, pe_premium=1.01)
    assert r["eligible"] is False and r["reason"] == "valuation_stretched"


def test_valuation_pb_only():
    assert ev(pe_premium=None, pb_premium=1.0)["eligible"] is True
    r = ev(pe_premium=None, pb_premium=1.2)
    assert r["eligible"] is False and r["reason"] == "valuation_stretched"


def test_valuation_both_rule():
    r = ev(pe_premium=0.9, pb_premium=1.2)   # BOTH must be <= 1.0
    assert r["eligible"] is False and r["reason"] == "valuation_stretched"
    assert ev(pe_premium=1.0, pb_premium=1.0)["eligible"] is True


def test_valuation_neither_available():
    r = ev(pe_premium=None, pb_premium=None)
    assert r["eligible"] is False and r["reason"] == "valuation_inputs_missing"


def test_stage1_gate_excludes():
    r = ev(gates_fired=["G3_tax_defer"])
    assert r["eligible"] is False and r["reason"] == "stage1_gate_fired"


def test_averaging_flag_excludes():
    for flag in ("averaging_warn", "averaging_block_adds"):
        r = ev(averaging_flag=flag)
        assert r["eligible"] is False and r["reason"] == "averaging_flag_present", flag
    assert ev(averaging_flag=None)["eligible"] is True


# ---------- integration: fixture run (carrier absent => Q-i2 fail-safe) ----------
_PINS = {
    # pre-G2 (020f3ba..3d9dd8a code) fixture outcomes at as_of 2026-08-29,
    # captured verbatim before G2. Order = portfolio input order.
    "Salasar Techno Engg":    ("TRIM", 66.3, 5.2,   "micro", ["G2_allocation"], "none"),
    "Ashoka Buildcon":        ("EXIT", 69.2, 25.82, "small", ["G1_governance", "G1_quality_break", "G2_allocation"], "averaging_block_adds"),
    "Larsen & Toubro":        ("HOLD", 48.9, 9.64,  "large", ["G3_tax_defer"], "none"),
    "AGI Greenpac":           ("WATCH", 45.5, 2.0,  None,   [], "none"),
    "Bajaj Finance":          ("TRIM", 54.8, 18.48, "large", ["G2_allocation"], "none"),
    "HDFC Bank":              ("TRIM", 54.5, 20.6,  "large", ["G2_allocation"], "none"),
    "Bank of Baroda":         ("TRIM", 44.8, 10.67, "large", ["G2_allocation"], "none"),
    "DAM Capital Advisors":   ("WATCH", 43.9, 1.04, "small", [], "none"),
    "Bharat Coking Coal":     ("WATCH", 39.4, 6.55, "mid",   [], "none"),
}


def _fixture_run():
    f = run_foundation("fixtures/portfolio.csv", "fixtures/screener.csv",
                       "fixtures/ledger.csv", as_of=AS_OF)
    return decide_on_foundation(f)


def test_integration_fixture_tags_empty_and_reasons():
    d = _fixture_run()
    assert len(d["holdings"]) == 9
    for h in d["holdings"]:
        assert h["tags"] == []
        ae = h["accumulate_evidence"]
        assert ae["eligible"] is False
        expected = "conviction_missing" if h["instrument"] == "Larsen & Toubro" else "decision_not_hold"
        assert ae["reason"] == expected, h["instrument"]
        # provenance echo = all None (fixtures carry no declared conviction input)
        assert ae["conviction_score"] is None and ae["conviction_score_source"] is None


def test_isolation_vs_pre_g2_pins():
    d = _fixture_run()
    from collections import Counter
    assert dict(Counter(h["decision"] for h in d["holdings"])) == {
        "TRIM": 4, "EXIT": 1, "HOLD": 1, "WATCH": 3}
    for h in d["holdings"]:
        dec, comp, alloc, bucket, gates, beh = _PINS[h["instrument"]]
        assert (h["decision"], h["composite_score"], h["alloc_pct"], h["bucket"],
                h["stage1"]["gates_fired"], h["behavioral_flags"][0]) == (
                dec, comp, alloc, bucket, gates, beh), h["instrument"]
    # additive fields must not break the shipped payload validator
    validate_decision_payload(d)


def test_carrier_fields_flow_through():
    """Q-i1 wiring: declared fields on the position reach the evaluator."""
    f = run_foundation("fixtures/portfolio.csv", "fixtures/screener.csv",
                       "fixtures/ledger.csv", as_of=AS_OF)
    f2 = copy.deepcopy(f)
    for p in f2["positions"]:
        if p["instrument"] == "Larsen & Toubro":
            p.update(conviction_score=85.0, conviction_score_present=True,
                     conviction_score_source="QG-Engine",
                     conviction_score_effective_date="2026-08-20",
                     conviction_score_version="v3")
    d = decide_on_foundation(f2)
    lt = next(h for h in d["holdings"] if h["instrument"] == "Larsen & Toubro")
    ae = lt["accumulate_evidence"]
    # conviction no longer the blocker: allocation clause (9.64 >= 4.0) now reports first
    assert ae["reason"] == "allocation_not_under_band"
    # provenance echo visible with the declared value (VP-1 / gate item 7)
    assert ae["conviction_score"] == 85.0
    assert (ae["conviction_score_source"], ae["conviction_score_effective_date"],
            ae["conviction_score_version"]) == ("QG-Engine", "2026-08-20", "v3")
    assert lt["tags"] == []  # still not eligible — no inference beyond the contract


def _synthetic_foundation():
    pos = {
        "instrument": "Synthetic Growth Co", "ticker": "SYN", "bucket": "large",
        "qty_held": 10, "avg_buy_price": 100.0, "invested": 1000.0,
        "current_value": 51.0, "alloc_pct": 0.51, "gain_pct": -94.9,
        "net_cashflow": 1000.0, "first_date": "2025-01-10", "last_date": "2025-01-10",
        "lot_count": 0, "in_screener": True, "pledge_pct": 0.0,
        "fundamentals": {
            "pe_ratio": 15.0, "pb_ratio": 2.0, "peg_ratio": 1.0, "roe": 15.0,
            "roce": 12.0, "eps_growth_1y_hist": 10.0, "eps_growth_1y_fwd": 10.0,
            "debt_equity": 0.2, "interest_coverage": 5.0, "price_fcf": 10.0,
            "pe_premium_vs_subsector": 0.9, "pb_premium_vs_subsector": 0.9,
            "dii_change_3m": 0.0, "fii_change_3m": 0.0, "sma_200": 90.0,
            "close_price": 35.0, "market_cap_cr": 50000.0,
            "sub_sector": "Capital Markets",
        },
        "conviction_score": 75.0, "conviction_score_present": True,
        "conviction_score_source": "QualityGrowth-Engine",
        "conviction_score_effective_date": "2026-08-20", "conviction_score_version": "v3",
    }
    return {"as_of": AS_OF.isoformat(), "run_id": "run_synth", "engine_version": "test",
            "positions": [pos], "lots": [], "reconciliation": {"issues": []},
            "data_as_of": {"stale_files": []}, "warnings": [],
            "provenance": {}, "content_hash": "synthetic"}


def test_synthetic_foundation_tag_attached_decision_unchanged():
    d = decide_all(_synthetic_foundation())
    h = d["holdings"][0]
    assert h["decision"] == "HOLD"                       # ACCUMULATE never alters the decision
    assert h["tags"] == ["ACCUMULATE"]
    assert h["accumulate_evidence"] == {
        "eligible": True, "reason": None,
        "conviction_score": 75.0,
        "conviction_score_source": "QualityGrowth-Engine",
        "conviction_score_effective_date": "2026-08-20",
        "conviction_score_version": "v3",
    }


def test_injection_isolation():
    """Conviction injection changes ONLY tags/evidence — nothing else."""
    f = run_foundation("fixtures/portfolio.csv", "fixtures/screener.csv",
                       "fixtures/ledger.csv", as_of=AS_OF)
    d0 = decide_on_foundation(copy.deepcopy(f))
    f2 = copy.deepcopy(f)
    for p in f2["positions"]:
        p.update(conviction_score=99.0, conviction_score_present=True,
                 conviction_score_source="QG", conviction_score_effective_date="2026-08-20",
                 conviction_score_version="v9")
    d1 = decide_on_foundation(f2)
    strip = lambda d: [{k: h[k] for k in h if k not in ("tags", "accumulate_evidence")}
                       for h in d["holdings"]]
    assert strip(d0) == strip(d1)
