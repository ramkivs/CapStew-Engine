"""Trim sizing — constrained optimisation (Freeze §5).

Sell plan is a FIFO prefix of lots (oldest first), matching Indian tax matching.
Two modes:
  TRIM-S (sizing):  sell enough to bring allocation back to the band top.
  TRIM-V (valuation): sell rho of quantity (rho in [0.25, 0.50]; default 0.25).
Hard constraints: FIFO prefix; remaining >= min meaningful position; sell <=
participation cap (ADV unknown in v1 → 25% of quantity); allocation-after <= band.
"""
from .scoring import band_for

RHO = 0.25  # Freeze §5: rho ∈ [0.25, 0.50] (policy range; default = lower bound)
HEADROOM = 125000.0  # Freeze §5: ₹1.25L LTCG headroom (emergent in the tax-cost objective).
# CR-020 (2026-08-27) comment-only correction: supersedes the stale "(spec §9.3)" pointer —
# the realized-gains export remains a recorded data gap (E2E register). Constant unchanged.


def sell_plan(lots, qty_to_sell, policy, txn_pct):
    plan, remaining = [], qty_to_sell
    stcg_gain = ltcg_gain = realized_loss = sell_value = 0.0
    for lot in lots:
        if remaining <= 0:
            break
        take = min(float(lot["qty"]), remaining)
        if take <= 0:
            continue
        gain = (lot["ltp"] - lot["buy_price"]) * take
        if gain >= 0:
            if lot["ltcg_eligible"]:
                ltcg_gain += gain
            else:
                stcg_gain += gain
        else:
            realized_loss += -gain
        sell_value += lot["ltp"] * take
        plan.append({"lot_id": lot["lot_id"], "qty": round(take, 2)})
        remaining -= take

    ltcg_tax = 0.125 * max(0.0, ltcg_gain - HEADROOM)
    stcg_tax = 0.20 * stcg_gain
    return {
        "fifo_lots_to_sell": plan,
        "suggested_qty": round(qty_to_sell - remaining, 2),
        "suggested_value": round(sell_value, 2),
        "tax_breakdown": {
            "stcg_gain": round(stcg_gain, 2),
            "ltcg_gain": round(ltcg_gain, 2),
            "stcg_tax": round(stcg_tax, 2),
            "ltcg_tax": round(ltcg_tax, 2),
            "realized_loss": round(realized_loss, 2),
        },
        "est_transaction_cost": round(sell_value * txn_pct / 100.0, 2),
    }


def _min_qty(policy, total_value, ltp):
    by_alloc = policy["min_position_alloc_pct"] / 100.0 * total_value / ltp
    by_value = policy["min_position_value"] / ltp
    return max(by_alloc, by_value)


def _cap_qty(policy, qty_held):
    # ADV unknown in v1 → 25% of quantity (Freeze §5 C3)
    return qty_held * policy["participation_position_pct"] / 100.0


def trim_s(pos, lots, policy, total_value):
    band = band_for(pos["bucket"], policy)
    ltp = lots[0]["ltp"]
    qty_held = float(pos["qty_held"])
    target_top = band[1]
    sell_value_target = max(0.0, (pos["alloc_pct"] - target_top) / 100.0 * total_value)
    qty_target = sell_value_target / ltp
    qty = min(qty_target, _cap_qty(policy, qty_held))
    if qty_held - qty < _min_qty(policy, total_value, ltp):
        qty = max(0.0, qty_held - _min_qty(policy, total_value, ltp))
    txn = policy["txn_cost_microcap_pct"] if pos["bucket"] == "micro" else policy["txn_cost_liquid_pct"]
    plan = sell_plan(lots, qty, policy, txn)
    plan["mode"] = "S"
    plan["target_alloc_pct"] = target_top
    plan["alloc_after_pct"] = round((pos["current_value"] - plan["suggested_value"]) / total_value * 100, 2)
    plan["participation_capped"] = qty_target > _cap_qty(policy, qty_held)
    return plan


def trim_v(pos, lots, policy, total_value):
    ltp = lots[0]["ltp"]
    qty_held = float(pos["qty_held"])
    qty = min(qty_held * RHO, _cap_qty(policy, qty_held))
    if qty_held - qty < _min_qty(policy, total_value, ltp):
        qty = max(0.0, qty_held - _min_qty(policy, total_value, ltp))
    txn = policy["txn_cost_microcap_pct"] if pos["bucket"] == "micro" else policy["txn_cost_liquid_pct"]
    plan = sell_plan(lots, qty, policy, txn)
    plan["mode"] = "V"
    plan["rho"] = RHO
    plan["alloc_after_pct"] = round((pos["current_value"] - plan["suggested_value"]) / total_value * 100, 2)
    plan["participation_capped"] = qty_held * RHO > _cap_qty(policy, qty_held)
    return plan
