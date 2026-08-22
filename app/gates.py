"""Stage 1 hard gates with strict precedence G0 > G1 > G2 > G3 > G4 (Freeze §2).

G0 (data integrity) is handled by the caller from reconciliation status. This
module evaluates G1–G3 against a holding's facts and returns the winning gate,
or None so the caller proceeds to G4 (composite).

Frozen rules:
- G1 (thesis/governance break) → EXIT, never partial.
- G2 (allocation/rebalance breach) → TRIM-S. Risk caps are NEVER tax-deferred.
- G3 (near-LTCG tax defer) → HOLD, suppressed when valuation_subscore >= 85.
"""
from .scoring import band_for


def evaluate_gates(alloc_pct, bucket, pledge_pct, quality_score, days_to_ltcg,
                   valuation_subscore, policy):
    band = band_for(bucket, policy)
    cap = policy["max_single_stock_pct"]
    rebal = band[1] * policy["rebalance_trigger_multiple"]

    g1_gov = pledge_pct is not None and pledge_pct > policy["pledge_threshold_pct"]
    g1_qual = quality_score is not None and quality_score < policy["quality_floor"]
    g2 = alloc_pct is not None and (alloc_pct > cap or alloc_pct > rebal)

    near = days_to_ltcg is not None and days_to_ltcg < policy["ltcg_defer_window_days"]
    stretched = valuation_subscore is not None and valuation_subscore >= policy["valuation_extreme_suppress"]
    suppressed = near and stretched
    g3 = near and not stretched and not (g1_gov or g1_qual) and not g2

    gates_fired = []
    if g1_gov:
        gates_fired.append("G1_governance")
    if g1_qual:
        gates_fired.append("G1_quality_break")
    if g2:
        gates_fired.append("G2_allocation")
    if g3:
        gates_fired.append("G3_tax_defer")
    if suppressed:
        gates_fired.append("G3_tax_defer_suppressed")

    result = {
        "gates_fired": gates_fired,
        "winning_gate": None,
        "decision": None,
        "trim_mode": None,
        "tax_defer_suppressed": suppressed,
        "near_ltcg": near,
    }

    if g1_gov or g1_qual:            # G1 wins
        result["winning_gate"] = "G1"
        result["decision"] = "EXIT"
    elif g2:                          # G2 wins (over G3)
        result["winning_gate"] = "G2"
        result["decision"] = "TRIM"
        result["trim_mode"] = "S"
    elif g3:                          # G3 wins (over G4)
        result["winning_gate"] = "G3"
        result["decision"] = "HOLD"
    return result
