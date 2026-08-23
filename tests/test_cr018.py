"""CR-018 — G2 rebalance base is target_top, not midpoint.

These are characterization tests for the V1.1-A A1 authority decision. They
lock the disagreement windows where the rejected A2 midpoint rule would have
fired earlier than the accepted target_top rule.
"""
from datetime import date
from pathlib import Path

from app.gates import evaluate_gates
from app.pipeline import run_engine
from app.policy import load_policy
from app.scoring import ASSUMED_SMALL_MICRO_BASIS, band_for

POLICY = load_policy()
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _gates(alloc_pct, bucket, days_to_ltcg=240, pledge_pct=0.0, valuation_subscore=50):
    return evaluate_gates(
        alloc_pct=alloc_pct,
        bucket=bucket,
        pledge_pct=pledge_pct,
        quality_score=100,
        days_to_ltcg=days_to_ltcg,
        valuation_subscore=valuation_subscore,
        policy=POLICY,
    )


def _run():
    return run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr018",
    )


def _h(payload, instrument):
    return next(h for h in payload["holdings"] if h["instrument"] == instrument)


def _assert_no_g2(alloc_pct, bucket):
    result = _gates(alloc_pct, bucket)
    assert result["decision"] is None
    assert result["winning_gate"] is None
    assert "G2_allocation" not in result["gates_fired"]


def _assert_g2_trim_s(alloc_pct, bucket):
    result = _gates(alloc_pct, bucket)
    assert result["decision"] == "TRIM"
    assert result["winning_gate"] == "G2"
    assert result["trim_mode"] == "S"
    assert "G2_allocation" in result["gates_fired"]


def test_large_bucket_uses_target_top_not_midpoint():
    # large band [4, 8]: accepted A1 threshold is 1.5 × target_top = 12.
    # D-03 absolute cap at 10 binds before the band-leg can fire.
    assert band_for("large", POLICY) == (4.0, 8.0)
    assert POLICY["max_single_stock_pct"] == 10.0
    assert 1.5 * band_for("large", POLICY)[1] == 12.0

    _assert_no_g2(9.0, "large")
    _assert_no_g2(9.5, "large")
    _assert_no_g2(10.0, "large")
    _assert_g2_trim_s(10.0001, "large")


def test_mid_bucket_disagreement_window_is_not_g2_until_target_top_threshold():
    # mid band [2, 5]: rejected midpoint threshold would be 5.25;
    # accepted A1 threshold is 1.5 × target_top = 7.5.
    assert band_for("mid", POLICY) == (2.0, 5.0)
    assert 1.5 * ((2.0 + 5.0) / 2.0) == 5.25
    assert 1.5 * band_for("mid", POLICY)[1] == 7.5

    _assert_no_g2(5.25, "mid")
    _assert_no_g2(6.0, "mid")
    _assert_no_g2(7.5, "mid")
    _assert_g2_trim_s(7.5001, "mid")


def test_small_and_micro_disagreement_window_is_not_g2_until_target_top_threshold():
    # small/micro band [1, 3]: rejected midpoint threshold would be 3.0;
    # accepted A1 threshold is 1.5 × target_top = 4.5.
    assert band_for("small", POLICY) == (1.0, 3.0)
    assert band_for("micro", POLICY) == (1.0, 3.0)
    assert 1.5 * ((1.0 + 3.0) / 2.0) == 3.0
    assert 1.5 * band_for("micro", POLICY)[1] == 4.5

    for bucket in ("small", "micro"):
        _assert_no_g2(3.0, bucket)
        _assert_no_g2(4.0, bucket)
        _assert_no_g2(4.5, bucket)
        _assert_g2_trim_s(4.5001, bucket)


def test_unknown_bucket_uses_cr009_fallback_band_without_relabeling():
    # CR-009 supplies the approved small/micro sizing basis for bucket=None;
    # CR-018 verifies that A1 target_top boundaries apply to that fallback band.
    assert band_for(None, POLICY) == (1.0, 3.0)

    _assert_no_g2(3.0, None)
    _assert_no_g2(4.5, None)
    _assert_g2_trim_s(4.5001, None)

    agi = _h(_run(), "AGI Greenpac")
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["band_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["reason_tree"]["stage2"]["position_sizing"]["band"] == [1.0, 3.0]


def test_g2_precedence_remains_unchanged():
    g1_plus_g2 = _gates(11.0, None, days_to_ltcg=12, pledge_pct=12.4, valuation_subscore=40)
    assert g1_plus_g2["decision"] == "EXIT"
    assert g1_plus_g2["winning_gate"] == "G1"
    assert g1_plus_g2["trim_mode"] is None
    assert "G2_allocation" in g1_plus_g2["gates_fired"]

    g2_plus_g3 = _gates(11.0, None, days_to_ltcg=12, pledge_pct=0.0, valuation_subscore=40)
    assert g2_plus_g3["decision"] == "TRIM"
    assert g2_plus_g3["winning_gate"] == "G2"
    assert g2_plus_g3["trim_mode"] == "S"
    assert "G3_tax_defer" not in g2_plus_g3["gates_fired"]

    g3_only = _gates(2.0, "large", days_to_ltcg=12, pledge_pct=0.0, valuation_subscore=40)
    assert g3_only["decision"] == "HOLD"
    assert g3_only["winning_gate"] == "G3"


def test_salasar_trim_s_quantity_and_target_remain_unchanged():
    salasar = _h(_run(), "Salasar Techno Engg")

    assert salasar["decision"] == "TRIM"
    assert salasar["stage1"]["winning_gate"] == "G2"
    assert salasar["trim"]["mode"] == "S"
    assert salasar["trim"]["target_alloc_pct"] == 3.0
    assert salasar["trim"]["suggested_qty"] == 120.0
    assert salasar["trim"]["suggested_value"] == 9180.0
    assert salasar["trim"]["fifo_lots_to_sell"] == [{"lot_id": 1, "qty": 120.0}]


def test_golden_trilogy_and_agi_remain_unchanged_under_cr018():
    payload = _run()
    salasar = _h(payload, "Salasar Techno Engg")
    ashoka = _h(payload, "Ashoka Buildcon")
    lt = _h(payload, "Larsen & Toubro")
    agi = _h(payload, "AGI Greenpac")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"], salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["band_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["data_quality"]["position_sizing"] == "proxy"
