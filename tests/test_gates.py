"""Stage 1 gate tests — the golden trilogy at DECISION level + precedence (Freeze §2, §11)."""
import pytest

from app.gates import evaluate_gates
from app.policy import load_policy

POLICY = load_policy()


def _gates(alloc_pct=None, bucket="micro", pledge_pct=0.0, quality_score=100,
           days_to_ltcg=None, valuation_subscore=50):
    return evaluate_gates(alloc_pct=alloc_pct, bucket=bucket, pledge_pct=pledge_pct,
                          quality_score=quality_score, days_to_ltcg=days_to_ltcg,
                          valuation_subscore=valuation_subscore, policy=POLICY)


# ---------------- golden trilogy ----------------

def test_golden_g2_salasar_trim_s():
    # GOLDEN-G2-TRIM-S-SALASAR: pledge 4 (<10), alloc 9.8 (> 1.5×3), composite 87
    r = _gates(alloc_pct=9.8, bucket="micro", pledge_pct=4.0, days_to_ltcg=240, valuation_subscore=97)
    assert r["decision"] == "TRIM"
    assert r["winning_gate"] == "G2"
    assert r["trim_mode"] == "S"
    assert "G2_allocation" in r["gates_fired"]
    assert "G1_governance" not in r["gates_fired"]


def test_golden_g1_ashoka_exit():
    # GOLDEN-G1-EXIT-ASHOKA: pledge 12.4 (>10), composite 48
    r = _gates(alloc_pct=2.4, bucket="small", pledge_pct=12.4, quality_score=100,
               days_to_ltcg=200, valuation_subscore=30)
    assert r["decision"] == "EXIT"
    assert r["winning_gate"] == "G1"


def test_golden_g3_lt_hold():
    # GOLDEN-G3-HOLD-LT: 22 days to LTCG, valuation 40 (<85), no breach
    r = _gates(alloc_pct=2.4, bucket="large", pledge_pct=0.0, quality_score=100,
               days_to_ltcg=22, valuation_subscore=40)
    assert r["decision"] == "HOLD"
    assert r["winning_gate"] == "G3"
    assert "G3_tax_defer" in r["gates_fired"]


def test_g3_suppressed_when_valuation_extreme():
    r = _gates(alloc_pct=2.4, bucket="large", pledge_pct=0.0, quality_score=100,
               days_to_ltcg=22, valuation_subscore=90)
    assert r["decision"] is None  # falls through to G4
    assert r["tax_defer_suppressed"] is True
    assert "G3_tax_defer_suppressed" in r["gates_fired"]


# ---------------- precedence combinations ----------------

def test_g1_wins_over_everything():
    # pledge > 10 AND alloc > cap AND near LTCG AND composite 88 → EXIT
    r = _gates(alloc_pct=11.0, bucket="micro", pledge_pct=12.4, quality_score=100,
               days_to_ltcg=12, valuation_subscore=90)
    assert r["decision"] == "EXIT" and r["winning_gate"] == "G1"


def test_g1_quality_break_wins():
    r = _gates(alloc_pct=2.0, bucket="large", pledge_pct=0.0, quality_score=30,
               days_to_ltcg=300, valuation_subscore=50)
    assert r["decision"] == "EXIT" and r["winning_gate"] == "G1"
    assert "G1_quality_break" in r["gates_fired"]


def test_g2_beats_g3_risk_caps_never_tax_deferred():
    # THE critical rule: allocation breach + 12 days to LTCG → TRIM-S, NOT HOLD
    r = _gates(alloc_pct=11.0, bucket="micro", pledge_pct=0.0, quality_score=100,
               days_to_ltcg=12, valuation_subscore=40)
    assert r["decision"] == "TRIM" and r["winning_gate"] == "G2"


def test_g3_beats_g4():
    r = _gates(alloc_pct=2.0, bucket="large", pledge_pct=0.0, quality_score=100,
               days_to_ltcg=10, valuation_subscore=40)
    assert r["decision"] == "HOLD" and r["winning_gate"] == "G3"


def test_g4_only_no_gate_fires():
    r = _gates(alloc_pct=4.0, bucket="large", pledge_pct=0.0, quality_score=100,
               days_to_ltcg=300, valuation_subscore=50)
    assert r["decision"] is None
    assert r["gates_fired"] == []


def test_governance_never_partial():
    # pledge breach → EXIT, not TRIM, even with allocation breach present
    r = _gates(alloc_pct=11.0, bucket="micro", pledge_pct=10.5, quality_score=100,
               days_to_ltcg=200, valuation_subscore=50)
    assert r["decision"] == "EXIT" and r["trim_mode"] is None
