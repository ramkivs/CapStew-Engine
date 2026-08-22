"""Trim sizing — constrained optimisation (Freeze §5)."""
from app.policy import load_policy
from app.trim import sell_plan, trim_s, trim_v

POLICY = load_policy()


def _lots(n=3, ltp=100.0, buys=(90.0, 95.0, 100.0), qty=100, ltcg=(False, False, False)):
    return [
        {"lot_id": i + 1, "qty": qty, "buy_price": buys[i % len(buys)], "ltp": ltp,
         "ltcg_eligible": ltcg[i % len(ltcg)]}
        for i in range(n)
    ]


def _pos(alloc_pct, qty_held, current_value, bucket="micro"):
    return {"alloc_pct": alloc_pct, "qty_held": qty_held,
            "current_value": current_value, "bucket": bucket}


def test_sell_plan_is_fifo_oldest_first():
    plan = sell_plan(_lots(qty=100), 250.0, POLICY, 0.35)
    assert [l["lot_id"] for l in plan["fifo_lots_to_sell"]] == [1, 2, 3]
    assert plan["fifo_lots_to_sell"][2]["qty"] == 50.0  # partial last lot


def test_trim_s_reaches_band_top_when_uncapped():
    # micro band [1,3]; alloc 8% of 1,000,000 = 80,000; ltp 100 → 800 shares
    pos = _pos(alloc_pct=8.0, qty_held=800, current_value=80000.0)
    policy = {**POLICY, "participation_position_pct": 100}  # remove cap for this test
    plan = trim_s(pos, _lots(n=8, ltp=100.0, buys=[80.0] * 8, qty=100), policy, 1_000_000.0)
    # sell to 3% → 30,000 value → 500 shares
    assert plan["suggested_qty"] == 500.0
    assert plan["alloc_after_pct"] == 3.0


def test_trim_s_caps_at_participation():
    pos = _pos(alloc_pct=8.0, qty_held=800, current_value=80000.0)
    policy = {**POLICY, "participation_position_pct": 25}
    plan = trim_s(pos, _lots(n=8, ltp=100.0, buys=[80.0] * 8, qty=100), policy, 1_000_000.0)
    assert plan["suggested_qty"] == 200.0   # 25% of 800
    assert plan["participation_capped"] is True


def test_trim_v_sells_quarter():
    pos = _pos(alloc_pct=4.0, qty_held=400, current_value=40000.0)
    policy = {**POLICY, "participation_position_pct": 100}
    plan = trim_v(pos, _lots(n=4, ltp=100.0, buys=[90.0] * 4, qty=100), policy, 1_000_000.0)
    assert plan["mode"] == "V"
    assert plan["suggested_qty"] == 100.0  # rho 0.25 × 400


def test_tax_breakdown_splits_ltcg_stcg():
    lots = [
        {"lot_id": 1, "qty": 100, "buy_price": 50.0, "ltp": 100.0, "ltcg_eligible": True},
        {"lot_id": 2, "qty": 100, "buy_price": 80.0, "ltp": 100.0, "ltcg_eligible": False},
    ]
    plan = sell_plan(lots, 200.0, POLICY, 0.35)
    tb = plan["tax_breakdown"]
    assert tb["ltcg_gain"] == 5000.0   # 100 × (100-50)
    assert tb["stcg_gain"] == 2000.0   # 100 × (100-80)
    assert tb["ltcg_tax"] == 0.0       # within ₹1.25L headroom
    assert tb["stcg_tax"] == 400.0     # 20%


def test_trim_respects_dust_floor():
    # position smaller than the dust floor → no trim (would leave dust)
    pos = _pos(alloc_pct=8.0, qty_held=40, current_value=4000.0)  # value < ₹5,000 floor
    policy = {**POLICY, "participation_position_pct": 100}
    plan = trim_s(pos, _lots(n=1, ltp=100.0, buys=[80.0], qty=40), policy, 1_000_000.0)
    assert plan["suggested_qty"] == 0.0
