"""CR-009 — explicit small/micro fallback disclosure for unknown buckets."""
from datetime import date
from pathlib import Path

from app.decision import decide_instrument
from app.hysteresis import Hysteresis
from app.pipeline import run_engine
from app.policy import load_policy
from app.scoring import ASSUMED_SMALL_MICRO_BASIS, CLASSIFIED_BUCKET_BASIS, band_for, position_sizing

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
POLICY = load_policy()


def _run():
    return run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr009",
    )


def _h(payload, name):
    return next(h for h in payload["holdings"] if h["instrument"] == name)


def _lot(days_to_ltcg=240):
    return {
        "lot_id": 1,
        "instrument": "SYNTH",
        "ticker": "SYNTH",
        "trade_date": "2026-04-15",
        "qty": 100,
        "buy_price": 80.0,
        "ltp": 100.0,
        "invested": 8000.0,
        "value": 10000.0,
        "pnl": 2000.0,
        "pnl_pct": 25.0,
        "days_held": 125,
        "days_to_ltcg": days_to_ltcg,
        "ltcg_eligible": False,
    }


def _unknown_pos(alloc_pct, pledge_pct=0.0):
    return {
        "instrument": "SYNTH",
        "ticker": "SYNTH",
        "bucket": None,
        "alloc_pct": alloc_pct,
        "gain_pct": 25.0,
        "current_value": alloc_pct / 100.0 * 100000.0,
        "qty_held": 100,
        "pledge_pct": pledge_pct,
        "fundamentals": None,
        "in_screener": False,
    }


def _decide_unknown(alloc_pct, pledge_pct=0.0, days_to_ltcg=240):
    return decide_instrument(
        _unknown_pos(alloc_pct, pledge_pct=pledge_pct),
        [_lot(days_to_ltcg=days_to_ltcg)],
        POLICY,
        total_value=100000.0,
        as_of=date(2026, 8, 22),
        hv=Hysteresis(),
        stale_files=[],
        blocked=set(),
        apply_hysteresis=False,
    )


def test_agi_unknown_bucket_fallback_is_disclosed_without_relabeling():
    agi = _h(_run(), "AGI Greenpac")

    assert agi["bucket"] is None
    assert agi["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["band_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["data_quality"]["position_sizing"] == "proxy"

    sizing = agi["reason_tree"]["stage2"]["position_sizing"]
    assert sizing["bucket"] is None
    assert sizing["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert sizing["band_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert sizing["band"] == [1.0, 3.0]
    assert sizing["cap_pct"] == 3.0


def test_agi_remains_watch_insufficient_and_b6_not_critical_sizing_failure():
    agi = _h(_run(), "AGI Greenpac")

    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"
    assert "position_sizing" not in agi["evidence"]["critical_categories_missing"]
    assert set(agi["evidence"]["critical_categories_missing"]) == {"valuation_stretch", "quality_drift"}


def test_known_classified_holdings_remain_authoritative():
    salasar = _h(_run(), "Salasar Techno Engg")

    assert salasar["bucket"] == "micro"
    assert salasar["bucket_basis"] == CLASSIFIED_BUCKET_BASIS
    assert salasar["band_basis"] == CLASSIFIED_BUCKET_BASIS
    assert salasar["data_quality"]["position_sizing"] == "authoritative"
    assert salasar["reason_tree"]["stage2"]["position_sizing"]["band"] == [1.0, 3.0]


def test_position_sizing_math_uses_existing_small_micro_fallback():
    assert band_for(None, POLICY) == band_for("micro", POLICY)
    assert position_sizing(5.0, None, POLICY) == position_sizing(5.0, "micro", POLICY)
    assert position_sizing(11.0, None, POLICY) == position_sizing(11.0, "micro", POLICY)


def test_unknown_bucket_g2_uses_fallback_without_relabeling_or_rule_change():
    h = _decide_unknown(alloc_pct=5.0)

    assert h["bucket"] is None
    assert h["decision"] == "TRIM"
    assert h["stage1"]["winning_gate"] == "G2"
    assert h["trim"]["mode"] == "S"
    assert h["band_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert h["data_quality"]["position_sizing"] == "proxy"
    assert h["reason_tree"]["stage1"]["g2_allocation"] == {
        "fired": True,
        "band_basis": ASSUMED_SMALL_MICRO_BASIS,
        "band": [1.0, 3.0],
        "alloc_pct": 5.0,
        "cap_pct": 3.0,
    }


def test_g1_still_overrides_g2_for_unknown_bucket():
    h = _decide_unknown(alloc_pct=11.0, pledge_pct=12.4, days_to_ltcg=12)

    assert h["bucket"] is None
    assert h["decision"] == "EXIT"
    assert h["stage1"]["winning_gate"] == "G1"
    assert h["trim"] is None
    assert "G2_allocation" in h["stage1"]["gates_fired"]


def test_g2_still_overrides_g3_for_unknown_bucket():
    h = _decide_unknown(alloc_pct=11.0, pledge_pct=0.0, days_to_ltcg=12)

    assert h["bucket"] is None
    assert h["decision"] == "TRIM"
    assert h["stage1"]["winning_gate"] == "G2"
    assert h["trim"]["mode"] == "S"
    assert "G2_allocation" in h["stage1"]["gates_fired"]
    assert "G3_tax_defer" not in h["stage1"]["gates_fired"]


def test_golden_trilogy_unchanged_under_cr009():
    p = _run()
    salasar = _h(p, "Salasar Techno Engg")
    ashoka = _h(p, "Ashoka Buildcon")
    lt = _h(p, "Larsen & Toubro")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"], salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
