"""Stage 2 scoring, eligibility, and band mapping (Freeze §3)."""
from app.policy import load_policy
from app.scoring import (
    apply_eligibility_caps,
    band_of,
    composite,
    eligibility,
    opportunity_cost,
    position_sizing,
    quality_drift,
    technical_regime,
    valuation_stretch,
)

POLICY = load_policy()


def test_valuation_stretch_high_for_salasar_like():
    f = {"pe_ratio": 55.0, "pe_premium_vs_subsector": 1.85, "pb_premium_vs_subsector": 1.6}
    assert valuation_stretch(f) >= 85


def test_valuation_stretch_below_85_for_lt_like():
    f = {"pe_ratio": 26.0, "pe_premium_vs_subsector": 1.10, "pb_premium_vs_subsector": 1.05}
    assert valuation_stretch(f) < 85


def test_valuation_falls_back_to_pb_when_pe_negative():
    f = {"pe_ratio": -8.5, "pe_premium_vs_subsector": 0.4, "pb_premium_vs_subsector": 0.38}
    v = valuation_stretch(f)
    assert v is not None and v < 50


def test_quality_drift_flags_ashoka_like():
    f = {"sub_sector": "Engineering", "roe": -3.4, "roce": 2.1, "debt_equity": 2.1,
         "interest_coverage": 1.1, "eps_growth_1y_hist": -15.0, "eps_growth_1y_fwd": -8.0,
         "pe_ratio": -8.5}
    assert quality_drift(f) == 100


def test_quality_banks_exempt_from_leverage_penalties():
    f = {"sub_sector": "Banks - Private", "roe": 15.8, "roce": 1.9, "debt_equity": 6.8,
         "interest_coverage": 1.4, "eps_growth_1y_hist": 16.0, "eps_growth_1y_fwd": 15.0,
         "pe_ratio": 19.5}
    assert quality_drift(f) == 0


def test_position_sizing_breach_scores_high():
    assert position_sizing(9.8, "micro", POLICY) == 90
    assert position_sizing(11.0, "micro", POLICY) == 100


def test_position_sizing_in_band_neutral():
    assert position_sizing(2.0, "micro", POLICY) == 35


def test_composite_renormalizes_over_available():
    subs = {"position_sizing": 90, "valuation_stretch": 100, "quality_drift": None,
            "tax_efficiency": 60, "opportunity_cost": None, "technical_regime": None}
    # weights 25/25/15 available = 65 → (90*25 + 100*25 + 60*15)/65
    c = composite(subs, POLICY["weights"])
    assert c == round((90 * 25 + 100 * 25 + 60 * 15) / 65, 1)


def test_eligibility_tiers():
    full = {k: 50 for k in POLICY["weights"]}
    assert eligibility(full, POLICY["weights"])["tier"] == "NORMAL"
    advisory = {k: 50 for k in ("position_sizing", "valuation_stretch", "tax_efficiency", "opportunity_cost")}
    assert eligibility(advisory, POLICY["weights"])["tier"] == "ADVISORY"   # 75%
    sparse = {k: 50 for k in ("position_sizing", "tax_efficiency", "opportunity_cost")}
    assert eligibility(sparse, POLICY["weights"])["tier"] == "INSUFFICIENT"  # 50%


def test_eligibility_coverage_math():
    subs = {k: 50 for k in ("position_sizing", "valuation_stretch", "tax_efficiency",
                            "opportunity_cost", "technical_regime")}
    ev = eligibility(subs, POLICY["weights"])
    assert ev["coverage"] == 0.8   # 80% → NORMAL
    assert ev["tier"] == "NORMAL"


def test_bands():
    assert band_of(30) == "HOLD"
    assert band_of(55) == "WATCH"
    assert band_of(75) == "TRIM"
    assert band_of(76) == "HARVEST"


def test_eligibility_caps():
    d, note = apply_eligibility_caps("HARVEST", "INSUFFICIENT", ["valuation_stretch", "quality_drift"])
    assert d == "WATCH" and note
    d, note = apply_eligibility_caps("HARVEST", "NORMAL", ["valuation_stretch"])
    assert d == "WATCH" and "HARVEST requires valuation" in note
    d, note = apply_eligibility_caps("TRIM", "NORMAL", ["valuation_stretch", "quality_drift"])
    assert d == "WATCH"
    d, note = apply_eligibility_caps("TRIM", "NORMAL", ["quality_drift"])
    assert d == "TRIM" and note is None


def test_opportunity_cost_and_technical_are_bounded():
    assert 0 <= opportunity_cost({"peg_ratio": 2.9}) <= 100
    assert 0 <= technical_regime({"close_price": 100, "sma_200": 50}) <= 100
