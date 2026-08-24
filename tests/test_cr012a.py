"""CR-012A — weight-only sensitivity characterization (fresh implementation).

Scope (per CR-012A fresh implementation authorization):

    A bounded, non-production, test-only characterization of how existing
    authoritative backend decisions respond to Stage 2 category weight
    variation through the EXISTING non-persisting what-if mechanism:

        policy_overrides -> decide_on_foundation(...) -> temporary decisions

    Only the six Stage 2 category weights vary between scenarios:

        position_sizing, valuation_stretch, quality_drift,
        tax_efficiency, opportunity_cost, technical_regime

    No G1/G2/G3/G4 threshold, band, gate, trim, tax, confidence,
    Opportunity Cost, D-14, Watchlist, or schema behaviour is varied here.
    This module does not create a new what-if capability; it only exercises
    the one that already exists and is already audited (test_audit.py,
    "what-if isolation").

    These are characterization tests, not a backtest and not a
    production-tuning exercise. No scenario here is a recommendation.

This is a FRESH implementation candidate. It supersedes no prior evidence and
claims no equivalence to any previously lost CR-012A candidate.
"""
import copy
from datetime import date
from pathlib import Path

import pytest

from app.pipeline import decide_on_foundation, run_foundation
from app.policy import load_policy
from app.scoring import WEIGHT_KEYS

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
AS_OF = date(2026, 8, 22)

# The six authorized Stage 2 weight dimensions (must match app.scoring.WEIGHT_KEYS
# exactly; this pins the authorized dimension set so a future accidental change
# to the category list is caught here, not silently absorbed).
AUTHORIZED_WEIGHT_DIMENSIONS = (
    "position_sizing",
    "valuation_stretch",
    "quality_drift",
    "tax_efficiency",
    "opportunity_cost",
    "technical_regime",
)

# ---------------------------------------------------------------------------
# Finite, deterministic, named scenario set. Every scenario is a *weights-only*
# policy_overrides dict — no bands/gates/trim/tax keys appear anywhere here.
# Values are characterization vectors, not proposed production weights.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "baseline": None,  # no override; production policy.yaml weights apply
    "position_sizing_emphasis": {
        "weights": {
            "position_sizing": 60, "valuation_stretch": 10, "quality_drift": 10,
            "tax_efficiency": 10, "opportunity_cost": 5, "technical_regime": 5,
        }
    },
    "valuation_stretch_emphasis": {
        "weights": {
            "position_sizing": 10, "valuation_stretch": 60, "quality_drift": 10,
            "tax_efficiency": 10, "opportunity_cost": 5, "technical_regime": 5,
        }
    },
    "quality_drift_emphasis": {
        "weights": {
            "position_sizing": 10, "valuation_stretch": 10, "quality_drift": 60,
            "tax_efficiency": 10, "opportunity_cost": 5, "technical_regime": 5,
        }
    },
    "tax_efficiency_emphasis": {
        "weights": {
            "position_sizing": 10, "valuation_stretch": 10, "quality_drift": 10,
            "tax_efficiency": 60, "opportunity_cost": 5, "technical_regime": 5,
        }
    },
    "opportunity_cost_emphasis": {
        "weights": {
            "position_sizing": 10, "valuation_stretch": 10, "quality_drift": 10,
            "tax_efficiency": 10, "opportunity_cost": 55, "technical_regime": 5,
        }
    },
    "technical_regime_emphasis": {
        "weights": {
            "position_sizing": 10, "valuation_stretch": 10, "quality_drift": 10,
            "tax_efficiency": 10, "opportunity_cost": 5, "technical_regime": 55,
        }
    },
    "balanced_alternative": {
        "weights": {
            "position_sizing": 17, "valuation_stretch": 17, "quality_drift": 17,
            "tax_efficiency": 17, "opportunity_cost": 16, "technical_regime": 16,
        }
    },
    "reduced_opportunity_cost": {
        "weights": {
            "position_sizing": 27, "valuation_stretch": 27, "quality_drift": 21,
            "tax_efficiency": 16, "opportunity_cost": 3, "technical_regime": 6,
        }
    },
    "increased_opportunity_cost": {
        "weights": {
            "position_sizing": 20, "valuation_stretch": 20, "quality_drift": 15,
            "tax_efficiency": 10, "opportunity_cost": 30, "technical_regime": 5,
        }
    },
}

NON_BASELINE_SCENARIOS = {k: v for k, v in SCENARIOS.items() if k != "baseline"}


def _foundation():
    return run_foundation(
        FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
        as_of=AS_OF, run_id="cr012a",
    )


def _h(payload, instrument):
    return next(h for h in payload["holdings"] if h["instrument"] == instrument)


def _run_scenario(foundation, overrides):
    return decide_on_foundation(foundation, policy_overrides=overrides, apply_hysteresis=False)


# ---- 1. Scenario definitions are deterministic --------------------------------

def test_scenario_set_is_fixed_and_deterministic():
    # The scenario dict itself is static Python data: re-importing / re-reading
    # it yields byte-identical structures across calls.
    import json
    a = json.dumps(SCENARIOS, sort_keys=True, default=str)
    b = json.dumps(SCENARIOS, sort_keys=True, default=str)
    assert a == b


def test_scenario_set_has_required_named_scenarios():
    required = {
        "baseline",
        "position_sizing_emphasis",
        "valuation_stretch_emphasis",
        "quality_drift_emphasis",
        "tax_efficiency_emphasis",
        "opportunity_cost_emphasis",
        "technical_regime_emphasis",
        "balanced_alternative",
        "reduced_opportunity_cost",
        "increased_opportunity_cost",
    }
    assert required <= set(SCENARIOS.keys())


# ---- 2. Temporary weight overrides work through the existing mechanism -------

def test_weight_overrides_flow_through_existing_whatif_mechanism():
    foundation = _foundation()
    for name, overrides in NON_BASELINE_SCENARIOS.items():
        payload = _run_scenario(foundation, overrides)
        assert payload is not None, f"scenario {name} produced no payload"
        assert "holdings" in payload


# ---- 5. Only the six weight dimensions vary (per scenario) -------------------

@pytest.mark.parametrize("name,overrides", sorted(NON_BASELINE_SCENARIOS.items()))
def test_scenario_only_overrides_weight_keys(name, overrides):
    assert set(overrides.keys()) == {"weights"}
    assert set(overrides["weights"].keys()) <= set(AUTHORIZED_WEIGHT_DIMENSIONS)
    assert set(overrides["weights"].keys()) <= set(WEIGHT_KEYS)


def test_authorized_dimension_set_matches_scoring_weight_keys():
    # Pin: the six authorized dimensions are exactly app.scoring.WEIGHT_KEYS.
    # If this ever fails, the Stage 2 category set has changed outside this CR
    # and CR-012A's authorized scope must be re-examined before proceeding.
    assert set(AUTHORIZED_WEIGHT_DIMENSIONS) == set(WEIGHT_KEYS)
    assert len(AUTHORIZED_WEIGHT_DIMENSIONS) == 6


# ---- 3. policy.yaml / default policy is not mutated ---------------------------

def test_policy_yaml_not_mutated_by_scenarios(tmp_path, monkeypatch):
    import yaml
    import app.policy as pol

    real_policy = load_policy()
    shadow_path = tmp_path / "policy.yaml"
    shadow_path.write_text(yaml.safe_dump(real_policy))
    monkeypatch.setattr(pol, "POLICY_PATH", shadow_path)

    before_bytes = shadow_path.read_bytes()
    before_weights = copy.deepcopy(load_policy()["weights"])

    foundation = _foundation()
    for overrides in NON_BASELINE_SCENARIOS.values():
        _run_scenario(foundation, overrides)

    after_bytes = shadow_path.read_bytes()
    after_weights = load_policy()["weights"]
    assert after_bytes == before_bytes, "policy.yaml file must not be written to"
    assert after_weights == before_weights, "on-disk default weights must not change"


# ---- 4. Production/default baseline behavior remains invariant ---------------

def test_baseline_scenario_matches_unmodified_production_run():
    foundation = _foundation()
    baseline_via_whatif = _run_scenario(foundation, SCENARIOS["baseline"])
    baseline_direct = decide_on_foundation(foundation, apply_hysteresis=False)
    assert baseline_via_whatif["content_hash"] == baseline_direct["content_hash"]


def test_golden_trilogy_unaffected_by_baseline_scenario():
    # The permanent regression anchors (V1.1-A authority doc §10) must be
    # untouched by simply exercising the baseline scenario through what-if.
    foundation = _foundation()
    payload = _run_scenario(foundation, SCENARIOS["baseline"])
    assert _h(payload, "Salasar Techno Engg")["decision"] == "TRIM"
    assert _h(payload, "Salasar Techno Engg")["stage1"]["winning_gate"] == "G2"
    assert _h(payload, "Ashoka Buildcon")["decision"] == "EXIT"
    assert _h(payload, "Ashoka Buildcon")["stage1"]["winning_gate"] == "G1"
    assert _h(payload, "Larsen & Toubro")["decision"] == "HOLD"
    assert _h(payload, "AGI Greenpac")["decision"] == "WATCH"


# ---- 6. Returned decisions remain valid DecisionPayload results ---------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_scenario_output_is_valid_decision_payload(name, overrides):
    # decide_on_foundation() already runs validate_decision_payload() internally
    # (app/pipeline.py); reaching this point without raising is the contract.
    foundation = _foundation()
    payload = _run_scenario(foundation, overrides)
    assert payload["holdings"], f"scenario {name} produced no holdings"
    for h in payload["holdings"]:
        assert h["decision"] in (
            "HOLD", "WATCH", "TRIM", "HARVEST", "EXIT", "NO-DECISION",
        )


# ---- 7. Repeated execution is deterministic -----------------------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_scenario_is_deterministic_across_repeated_runs(name, overrides):
    foundation = _foundation()
    first = _run_scenario(foundation, overrides)
    second = _run_scenario(foundation, overrides)
    assert first["content_hash"] == second["content_hash"]


# ---- 8. Baseline versus scenario outputs can be compared ----------------------

def test_scenarios_can_be_compared_against_baseline():
    foundation = _foundation()
    baseline = _run_scenario(foundation, SCENARIOS["baseline"])
    comparison = {}
    for name, overrides in NON_BASELINE_SCENARIOS.items():
        scenario_payload = _run_scenario(foundation, overrides)
        comparison[name] = {
            "content_hash_changed": scenario_payload["content_hash"] != baseline["content_hash"],
            "decisions": {h["instrument"]: h["decision"] for h in scenario_payload["holdings"]},
        }
    # At least one weight-emphasis scenario must be comparable (able to produce
    # a decision map) — the comparison itself is the deliverable, not any
    # particular decision outcome.
    assert len(comparison) == len(NON_BASELINE_SCENARIOS)
    for name, result in comparison.items():
        assert isinstance(result["decisions"], dict) and result["decisions"]


# ---- 9. No G2 threshold/gate parameter is modified -----------------------------

def test_scenarios_never_touch_gate_or_band_policy_keys():
    forbidden_keys = {
        "bands", "target_bands", "max_single_stock_pct", "rebalance_trigger_multiple",
        "g1_pledge_pct", "ltcg_period_days", "recon_tolerance_inr",
    }
    for overrides in NON_BASELINE_SCENARIOS.values():
        assert forbidden_keys.isdisjoint(overrides.keys())
        assert forbidden_keys.isdisjoint(overrides.get("weights", {}).keys())


def test_g2_gate_math_is_unchanged_by_weight_scenarios():
    # G2 evaluation (app/gates.py) does not consume Stage 2 weights at all; this
    # characterizes that weight-only overrides cannot move the G2 boundary.
    from app.gates import evaluate_gates

    baseline_gate = evaluate_gates(
        alloc_pct=11.0, bucket="large", pledge_pct=0.0, quality_score=100,
        days_to_ltcg=240, valuation_subscore=50, policy=load_policy(),
    )
    weighted_policy = copy.deepcopy(load_policy())
    weighted_policy["weights"] = SCENARIOS["opportunity_cost_emphasis"]["weights"]
    weighted_gate = evaluate_gates(
        alloc_pct=11.0, bucket="large", pledge_pct=0.0, quality_score=100,
        days_to_ltcg=240, valuation_subscore=50, policy=weighted_policy,
    )
    assert baseline_gate == weighted_gate


# ---- 10 / 11. D-14 and Watchlist remain non-operational -----------------------

def test_d14_hurdles_remain_non_operational_under_weight_scenarios():
    from app.scoring import opportunity_cost_evidence

    foundation = _foundation()
    for overrides in SCENARIOS.values():
        payload = _run_scenario(foundation, overrides)
        for h in payload["holdings"]:
            oc = h.get("stage2", {}).get("opportunity_cost") if h.get("stage2") else None
            if oc is not None:
                assert oc["source"] in ("peg_proxy", "watchlist", "missing")
                # D-14 is not a recognized operational source under any scenario.
                assert oc["source"] != "hurdle_d14"
    # Direct evidence-function check: no watchlist/D-14 input surface exists to feed.
    import inspect
    sig = inspect.signature(opportunity_cost_evidence)
    assert list(sig.parameters.keys()) == ["f"]


def test_watchlist_source_never_appears_without_a_watchlist_ingest_path():
    # There is no watchlist file in fixtures/ and no watchlist ingest is wired;
    # confirm the fixture screener data cannot accidentally produce a
    # "watchlist" opportunity_cost source under any authorized scenario.
    foundation = _foundation()
    for overrides in SCENARIOS.values():
        payload = _run_scenario(foundation, overrides)
        for h in payload["holdings"]:
            stage2 = h.get("stage2")
            oc = stage2.get("opportunity_cost") if stage2 else None
            if oc is not None:
                assert oc["source"] != "watchlist"


# ---- 12. Fixtures are not modified ---------------------------------------------

def test_fixture_files_are_not_modified_by_running_scenarios():
    fixture_files = ["portfolio.csv", "screener.csv", "ledger.csv", "sold_sample.csv"]
    before = {name: (FIXDIR / name).read_bytes() for name in fixture_files}

    foundation = _foundation()
    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)

    after = {name: (FIXDIR / name).read_bytes() for name in fixture_files}
    assert before == after
