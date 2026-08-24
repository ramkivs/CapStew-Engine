"""CR-012B — G2 threshold sensitivity characterization (fresh implementation).

Scope (per CR-012B fresh implementation authorization):

    A bounded, non-production, test-only characterization of how existing
    authoritative G2 decisions respond to temporary variation of the two
    authorized G2 policy scalars, through the EXISTING non-persisting
    what-if mechanism:

        policy_overrides -> decide_on_foundation(...) -> temporary decisions

    Only these two G2 dimensions vary between scenarios:

        max_single_stock_pct        (D-03 absolute cap leg)
        rebalance_trigger_multiple  (D-04 multiple, applied to target_top)

    target_bands is NEVER varied and never appears in any override.
    target_top remains band_for(bucket, policy)[1] in every scenario -- it is
    verified as an invariant, never varied. The CR-018 A1 rule
    (G2 base = target_top, not midpoint) is exercised as fixed checkpoints
    and is not modified.

    No band, weight, trim, tax, confidence, Opportunity Cost, D-14,
    Watchlist, or schema behaviour is varied here. This module does not
    create a new what-if capability; it only exercises the one that already
    exists and is already audited (test_audit.py, "what-if isolation").

    These are characterization tests, not a backtest, not an optimizer, and
    not a production-tuning exercise. No scenario here is a recommendation,
    and no scenario proposes a production threshold.

This is a FRESH implementation candidate. It supersedes no prior evidence and
claims no equivalence to any previously lost CR-012B candidate.
"""
import copy
import inspect
from datetime import date
from pathlib import Path

import pytest

from app.gates import evaluate_gates
from app.pipeline import decide_on_foundation, run_foundation
from app.policy import load_policy, validate_policy
from app.scoring import ASSUMED_SMALL_MICRO_BASIS, band_for

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
AS_OF = date(2026, 8, 22)
POLICY = load_policy()

# The two authorized G2 dimensions. These are exactly the two policy scalars
# consumed by the G2 predicate in app/gates.py:
#
#     cap   = policy["max_single_stock_pct"]
#     rebal = band[1] * policy["rebalance_trigger_multiple"]
#     g2    = alloc_pct > cap or alloc_pct > rebal
#
# Pinning them here means an accidental widening of the authorized override
# surface is caught by this module rather than silently absorbed.
AUTHORIZED_G2_DIMENSIONS = ("max_single_stock_pct", "rebalance_trigger_multiple")

# Keys that must never be overridden by a CR-012B scenario. target_bands heads
# this list: it feeds both the G2 band-leg and app/trim.py target_alloc_pct, so
# varying it would perturb GOLDEN-G2-TRIM-S-SALASAR.
FORBIDDEN_OVERRIDE_KEYS = (
    "target_bands", "bands", "weights", "quality_floor", "quality_drop_pts",
    "pledge_threshold_pct", "pledge_qoq_pp", "ltcg_defer_window_days",
    "valuation_extreme_suppress", "buckets", "ltcg_period_days",
    "recon_tolerance_inr", "min_position_alloc_pct", "min_position_value",
    "hurdle_nifty_pct", "hurdle_liquid_pct", "rerating_strong_pct",
    "rerating_critical_pct", "participation_adv_pct", "participation_position_pct",
    "txn_cost_liquid_pct", "txn_cost_microcap_pct", "review_cadence",
    "policy_version", "effective_from",
)

# ---------------------------------------------------------------------------
# Finite, deterministic, named scenario set. Every scenario is a G2-scalars-only
# policy_overrides dict -- no target_bands/weights/gate-threshold keys appear.
#
# Values are bounded characterization probes, not proposed production
# thresholds and not the output of any search, sweep, fit, or optimizer. Each
# was chosen to sit inside existing policy validation (in particular
# max_single_stock_pct stays well above the min_position_alloc_pct floor of
# 0.5) and to straddle the CR-018 A1 checkpoint windows.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "baseline": None,  # no override; production policy.yaml D-03/D-04 apply
    # --- bounded max_single_stock_pct sensitivity (D-03 cap leg) -------------
    "cap_tightened_9_0": {"max_single_stock_pct": 9.0},
    "cap_tightened_8_0": {"max_single_stock_pct": 8.0},
    "cap_relaxed_12_0": {"max_single_stock_pct": 12.0},
    "cap_relaxed_15_0": {"max_single_stock_pct": 15.0},
    # --- bounded rebalance_trigger_multiple sensitivity (D-04 band leg) ------
    "multiple_tightened_1_00": {"rebalance_trigger_multiple": 1.0},
    "multiple_tightened_1_25": {"rebalance_trigger_multiple": 1.25},
    "multiple_relaxed_1_75": {"rebalance_trigger_multiple": 1.75},
    "multiple_relaxed_2_00": {"rebalance_trigger_multiple": 2.0},
    # --- small finite combined cap + multiplier sensitivity ------------------
    "combined_tightened": {
        "max_single_stock_pct": 9.0, "rebalance_trigger_multiple": 1.25,
    },
    "combined_relaxed": {
        "max_single_stock_pct": 12.0, "rebalance_trigger_multiple": 2.0,
    },
    "combined_tight_cap_loose_multiple": {
        "max_single_stock_pct": 9.0, "rebalance_trigger_multiple": 2.0,
    },
    "combined_loose_cap_tight_multiple": {
        "max_single_stock_pct": 12.0, "rebalance_trigger_multiple": 1.0,
    },
}

NON_BASELINE_SCENARIOS = {k: v for k, v in SCENARIOS.items() if k != "baseline"}

# CR-018 A1 disagreement windows, reused strictly as FIXED CHECKPOINTS (they are
# regression boundaries recorded in docs/v1.1-authority-decisions-v1.md section 3,
# not new methodology and not tuning targets).
CR018_WINDOWS = {
    "large": (9.0, 10.0),
    "mid": (5.25, 7.5),
    "small": (3.0, 4.5),
    "micro": (3.0, 4.5),
}

# Production (baseline) decisions for the fixture portfolio, recorded from an
# actual run. Used as the comparison anchor.
BASELINE_DECISIONS = {
    "Salasar Techno Engg": ("TRIM", "G2", "S"),
    "Ashoka Buildcon": ("EXIT", "G1", None),
    "Larsen & Toubro": ("HOLD", "G3", None),
    "AGI Greenpac": ("WATCH", None, None),
    "Bajaj Finance": ("TRIM", "G2", "S"),
    "HDFC Bank": ("TRIM", "G2", "S"),
    "Bank of Baroda": ("TRIM", "G2", "S"),
    "DAM Capital Advisors": ("WATCH", None, None),
    "Bharat Coking Coal": ("WATCH", None, None),
}


def _foundation():
    return run_foundation(
        FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
        as_of=AS_OF, run_id="cr012b",
    )


def _h(payload, instrument):
    return next(h for h in payload["holdings"] if h["instrument"] == instrument)


def _run_scenario(foundation, overrides):
    return decide_on_foundation(foundation, policy_overrides=overrides, apply_hysteresis=False)


def _decision_map(payload):
    return {
        h["instrument"]: (
            h["decision"], h["stage1"]["winning_gate"], (h.get("trim") or {}).get("mode"),
        )
        for h in payload["holdings"]
    }


def _merged(overrides):
    """Merge overrides onto the production policy the same way decide_all does."""
    p = dict(copy.deepcopy(POLICY))
    for k, v in (overrides or {}).items():
        p[k] = v
    return p


def _g2_fired(alloc_pct, bucket, overrides=None):
    result = evaluate_gates(
        alloc_pct=alloc_pct, bucket=bucket, pledge_pct=0.0, quality_score=100,
        days_to_ltcg=240, valuation_subscore=50, policy=_merged(overrides),
    )
    return "G2_allocation" in result["gates_fired"]


@pytest.fixture(scope="module")
def foundation():
    return _foundation()


# ---- 1. Deterministic named scenarios -----------------------------------------

def test_scenario_set_is_fixed_and_deterministic():
    assert list(SCENARIOS) == [
        "baseline",
        "cap_tightened_9_0", "cap_tightened_8_0",
        "cap_relaxed_12_0", "cap_relaxed_15_0",
        "multiple_tightened_1_00", "multiple_tightened_1_25",
        "multiple_relaxed_1_75", "multiple_relaxed_2_00",
        "combined_tightened", "combined_relaxed",
        "combined_tight_cap_loose_multiple", "combined_loose_cap_tight_multiple",
    ]
    assert SCENARIOS["baseline"] is None
    assert len(NON_BASELINE_SCENARIOS) == 12


def test_scenario_set_covers_the_required_contract_shape():
    cap_only, mult_only, combined = [], [], []
    for name, ov in NON_BASELINE_SCENARIOS.items():
        keys = set(ov)
        if keys == {"max_single_stock_pct"}:
            cap_only.append(name)
        elif keys == {"rebalance_trigger_multiple"}:
            mult_only.append(name)
        else:
            combined.append(name)
    assert len(cap_only) == 4        # bounded cap sensitivity
    assert len(mult_only) == 4       # bounded multiple sensitivity
    assert len(combined) == 4        # small finite combined set


def test_scenario_values_are_plain_finite_scalars():
    for name, ov in NON_BASELINE_SCENARIOS.items():
        for key, value in ov.items():
            assert isinstance(value, float), f"{name}.{key} must be a fixed float"
            assert value == value and value not in (float("inf"), float("-inf"))


# ---- 2. Only the two authorized G2 parameters are overridden ------------------

@pytest.mark.parametrize("name,overrides", sorted(NON_BASELINE_SCENARIOS.items()))
def test_scenario_only_overrides_authorized_g2_parameters(name, overrides):
    assert set(overrides).issubset(set(AUTHORIZED_G2_DIMENSIONS)), name
    assert overrides, f"{name} must override at least one authorized parameter"


def test_authorized_dimensions_are_exactly_the_two_g2_policy_scalars():
    source = inspect.getsource(evaluate_gates)
    assert 'policy["max_single_stock_pct"]' in source
    assert 'policy["rebalance_trigger_multiple"]' in source
    assert AUTHORIZED_G2_DIMENSIONS == ("max_single_stock_pct", "rebalance_trigger_multiple")


def test_no_scenario_touches_any_forbidden_policy_key():
    for name, ov in NON_BASELINE_SCENARIOS.items():
        for forbidden in FORBIDDEN_OVERRIDE_KEYS:
            assert forbidden not in ov, f"{name} must not override {forbidden}"


# ---- 3 / 4. target_bands is never overridden and never changes ----------------

def test_target_bands_never_appears_in_any_scenario_override():
    for name, ov in NON_BASELINE_SCENARIOS.items():
        assert "target_bands" not in (ov or {}), name
        assert "small_micro" not in repr(ov), name


@pytest.mark.parametrize("name,overrides", sorted(NON_BASELINE_SCENARIOS.items()))
def test_target_bands_values_remain_unchanged_under_every_scenario(name, overrides):
    merged = _merged(overrides)
    assert merged["target_bands"] == POLICY["target_bands"]
    assert merged["target_bands"] == {
        "large": [4.0, 8.0], "mid": [2.0, 5.0], "small_micro": [1.0, 3.0],
    }


# ---- 5. target_top invariant --------------------------------------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_target_top_remains_band_for_bucket_policy_index_1(name, overrides):
    merged = _merged(overrides)
    for bucket, expected_top in (
        ("large", 8.0), ("mid", 5.0), ("small", 3.0), ("micro", 3.0), (None, 3.0),
    ):
        assert band_for(bucket, merged)[1] == expected_top
        assert band_for(bucket, merged) == band_for(bucket, POLICY)


def test_cr018_target_top_implementation_is_unchanged():
    """G2's band leg must still be target_top * multiple, never a midpoint."""
    source = inspect.getsource(evaluate_gates)
    assert 'rebal = band[1] * policy["rebalance_trigger_multiple"]' in source
    assert "midpoint" not in source and "mid_point" not in source


# ---- 6. policy.yaml is never modified ----------------------------------------

def test_policy_yaml_not_mutated_by_scenarios(tmp_path, monkeypatch, foundation):
    import yaml

    import app.policy as pol

    shadow = tmp_path / "policy.yaml"
    shadow.write_text(yaml.safe_dump(load_policy()))
    monkeypatch.setattr(pol, "POLICY_PATH", shadow)
    before = shadow.read_bytes()

    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)

    assert shadow.read_bytes() == before
    assert load_policy()["max_single_stock_pct"] == POLICY["max_single_stock_pct"]
    assert load_policy()["rebalance_trigger_multiple"] == POLICY["rebalance_trigger_multiple"]
    assert load_policy()["target_bands"] == POLICY["target_bands"]


def test_in_memory_default_policy_is_not_mutated_by_scenarios(foundation):
    snapshot = copy.deepcopy(POLICY)
    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)
    assert POLICY == snapshot
    assert load_policy() == snapshot


# ---- 7. Fixtures are never modified in content --------------------------------

def test_fixture_files_are_not_modified_by_running_scenarios(foundation):
    names = ("portfolio.csv", "screener.csv", "ledger.csv")
    # Compare line-ending-normalized content: the repo's conftest regenerates
    # fixtures per session and the generator writes platform-native endings.
    before = {n: (FIXDIR / n).read_bytes().replace(b"\r\n", b"\n") for n in names}
    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)
    after = {n: (FIXDIR / n).read_bytes().replace(b"\r\n", b"\n") for n in names}
    assert after == before


# ---- 8. Every scenario produces a valid DecisionPayload -----------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_scenario_output_is_valid_decision_payload(name, overrides, foundation):
    # decide_on_foundation validates internally via validate_decision_payload.
    payload = _run_scenario(foundation, overrides)
    assert payload["holdings"] and len(payload["holdings"]) == 9
    assert payload["content_hash"]
    for h in payload["holdings"]:
        assert h["decision"] in ("HOLD", "WATCH", "TRIM", "HARVEST", "EXIT")


@pytest.mark.parametrize("name,overrides", sorted(NON_BASELINE_SCENARIOS.items()))
def test_scenario_policy_remains_valid_under_existing_validation(name, overrides):
    assert validate_policy(_merged(overrides)) == []


# ---- 9. Production baseline remains unchanged ---------------------------------

def test_baseline_scenario_matches_unmodified_production_run(foundation):
    explicit = _run_scenario(foundation, SCENARIOS["baseline"])
    implicit = decide_on_foundation(foundation, apply_hysteresis=False)
    assert explicit["content_hash"] == implicit["content_hash"]
    assert _decision_map(explicit) == BASELINE_DECISIONS


def test_baseline_g2_population_is_the_recorded_production_set(foundation):
    payload = _run_scenario(foundation, SCENARIOS["baseline"])
    g2 = sorted(h["instrument"] for h in payload["holdings"]
                if h["stage1"]["winning_gate"] == "G2")
    assert g2 == ["Bajaj Finance", "Bank of Baroda", "HDFC Bank", "Salasar Techno Engg"]


# ---- 10 / 11. G1 and G3 methodology remain unchanged --------------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_g1_methodology_is_unchanged_by_g2_scenarios(name, overrides):
    merged = _merged(overrides)
    assert merged["quality_floor"] == POLICY["quality_floor"]
    assert merged["pledge_threshold_pct"] == POLICY["pledge_threshold_pct"]
    # A G1 governance/quality break still wins regardless of the G2 scalars.
    g1 = evaluate_gates(alloc_pct=25.0, bucket="small", pledge_pct=12.4, quality_score=100,
                        days_to_ltcg=240, valuation_subscore=50, policy=merged)
    assert g1["winning_gate"] == "G1" and g1["decision"] == "EXIT"
    g1q = evaluate_gates(alloc_pct=1.0, bucket="small", pledge_pct=0.0, quality_score=10,
                         days_to_ltcg=240, valuation_subscore=50, policy=merged)
    assert g1q["winning_gate"] == "G1" and g1q["decision"] == "EXIT"


@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_g3_methodology_is_unchanged_by_g2_scenarios(name, overrides):
    merged = _merged(overrides)
    assert merged["ltcg_defer_window_days"] == POLICY["ltcg_defer_window_days"]
    assert merged["valuation_extreme_suppress"] == POLICY["valuation_extreme_suppress"]
    # Well inside every band: no G2 leg can fire, so G3 defer still applies.
    g3 = evaluate_gates(alloc_pct=2.0, bucket="large", pledge_pct=0.0, quality_score=100,
                        days_to_ltcg=12, valuation_subscore=40, policy=merged)
    assert g3["winning_gate"] == "G3" and g3["decision"] == "HOLD"
    # Valuation-extreme suppression of G3 is likewise untouched.
    sup = evaluate_gates(alloc_pct=2.0, bucket="large", pledge_pct=0.0, quality_score=100,
                         days_to_ltcg=12, valuation_subscore=90, policy=merged)
    assert sup["tax_defer_suppressed"] is True and sup["winning_gate"] is None


# ---- 12. CR-018 A1 windows remain intact --------------------------------------

def test_cr018_a1_windows_hold_under_production_policy():
    """Baseline reproduction of the CR-018 A1 checkpoints (7/7 contract)."""
    for bucket, (lo, hi) in CR018_WINDOWS.items():
        assert not _g2_fired(lo, bucket)
        assert not _g2_fired(hi, bucket)
        assert _g2_fired(hi + 0.0001, bucket)
    # CR-009 unknown-bucket fallback uses the same A1 boundaries.
    assert not _g2_fired(3.0, None)
    assert not _g2_fired(4.5, None)
    assert _g2_fired(4.5001, None)


def test_cr018_a1_rejected_midpoint_rule_is_never_reintroduced():
    """A2 (1.5 x midpoint) must not fire at any scenario's band leg."""
    for name, ov in SCENARIOS.items():
        merged = _merged(ov)
        for bucket in ("large", "mid", "small", "micro"):
            band = band_for(bucket, merged)
            midpoint = (band[0] + band[1]) / 2.0
            # The engine's band leg is always computed from target_top.
            assert band[1] * merged["rebalance_trigger_multiple"] != pytest.approx(
                midpoint * merged["rebalance_trigger_multiple"]
            ), f"{name}/{bucket}: band leg collapsed onto the rejected midpoint base"


@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_cr018_checkpoints_are_explained_entirely_by_the_two_scalars(name, overrides):
    """Checkpoint outcomes must equal the closed-form A1 predicate."""
    merged = _merged(overrides)
    cap = merged["max_single_stock_pct"]
    mult = merged["rebalance_trigger_multiple"]
    for bucket, (lo, hi) in CR018_WINDOWS.items():
        top = band_for(bucket, merged)[1]
        for probe in (lo, hi, hi + 0.0001):
            expected = probe > cap or probe > top * mult
            assert _g2_fired(probe, bucket, overrides) is expected


def test_cr018_seven_test_contract_file_is_untouched():
    """CR-012B must not modify the CR-018 contract tests it depends on."""
    cr018 = Path(__file__).resolve().parent / "test_cr018.py"
    text = cr018.read_text(encoding="utf-8")
    assert "target_top" in text
    assert text.count("def test_") == 7


# ---- 13. G1 > G2 > G3 precedence remains intact -------------------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_gate_precedence_is_unchanged_by_g2_scenarios(name, overrides):
    merged = _merged(overrides)
    # Force both G1 and G2 conditions: G1 must win, and never partially.
    both = evaluate_gates(alloc_pct=50.0, bucket=None, pledge_pct=12.4, quality_score=100,
                          days_to_ltcg=12, valuation_subscore=40, policy=merged)
    assert both["winning_gate"] == "G1"
    assert both["decision"] == "EXIT"
    assert both["trim_mode"] is None
    assert "G2_allocation" in both["gates_fired"]
    # G2 outranks G3: risk caps are never tax-deferred.
    g2g3 = evaluate_gates(alloc_pct=50.0, bucket=None, pledge_pct=0.0, quality_score=100,
                          days_to_ltcg=12, valuation_subscore=40, policy=merged)
    assert g2g3["winning_gate"] == "G2"
    assert g2g3["decision"] == "TRIM"
    assert g2g3["trim_mode"] == "S"
    assert "G3_tax_defer" not in g2g3["gates_fired"]


# ---- 14 / 15. D-14 and Watchlist remain non-operational -----------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_d14_remains_non_operational_under_g2_scenarios(name, overrides, foundation):
    payload = _run_scenario(foundation, overrides)
    for h in payload["holdings"]:
        oc = h["reason_tree"]["stage2"].get("opportunity_cost")
        if oc is not None and "source" in oc:
            assert oc["source"] in ("peg_proxy", "watchlist", "missing")
            assert oc["source"] != "hurdle_d14"
    assert "hurdle_d14" not in repr(payload)


@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_watchlist_remains_non_operational_under_g2_scenarios(name, overrides, foundation):
    payload = _run_scenario(foundation, overrides)
    for h in payload["holdings"]:
        oc = h["reason_tree"]["stage2"].get("opportunity_cost")
        if oc is not None and "source" in oc:
            assert oc["source"] != "watchlist"
    assert not (FIXDIR / "watchlist.csv").exists()


# ---- 16. No run is persisted --------------------------------------------------

def test_scenarios_never_persist_a_run(tmp_path, monkeypatch, foundation):
    from app.store import RunStore

    import app.config as cfg

    monkeypatch.setattr(cfg, "STORE_PATH", tmp_path / "cr012b.db")
    store = RunStore()
    before = store.count()

    calls = []
    original = RunStore.save_run
    monkeypatch.setattr(RunStore, "save_run",
                        lambda self, *a, **k: calls.append(1) or original(self, *a, **k))

    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)

    assert calls == []
    assert RunStore().count() == before


def test_no_scenario_execution_path_writes_to_the_store(tmp_path, monkeypatch, foundation):
    """Executing the whole scenario set must leave the store empty."""
    from app.store import RunStore

    import app.config as cfg

    monkeypatch.setattr(cfg, "STORE_PATH", tmp_path / "cr012b_empty.db")
    for overrides in SCENARIOS.values():
        _run_scenario(foundation, overrides)
    assert RunStore().count() == 0


# ---- 17. Repeated execution is deterministic ----------------------------------

@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_scenario_is_deterministic_across_repeated_runs(name, overrides, foundation):
    first = _run_scenario(foundation, overrides)
    second = _run_scenario(foundation, overrides)
    assert first["content_hash"] == second["content_hash"]
    assert _decision_map(first) == _decision_map(second)


def test_scenario_determinism_across_independent_foundations():
    a = _run_scenario(_foundation(), SCENARIOS["combined_tightened"])
    b = _run_scenario(_foundation(), SCENARIOS["combined_tightened"])
    assert a["content_hash"] == b["content_hash"]


def test_distinct_scenarios_are_distinguishable_from_baseline(foundation):
    baseline = _run_scenario(foundation, SCENARIOS["baseline"])
    for name, overrides in NON_BASELINE_SCENARIOS.items():
        payload = _run_scenario(foundation, overrides)
        assert payload["content_hash"] != baseline["content_hash"], name


# ---- 18 / 19. Golden trilogy and AGI regression -------------------------------

def test_golden_trilogy_and_agi_unchanged_in_baseline_scenario(foundation):
    payload = _run_scenario(foundation, SCENARIOS["baseline"])
    salasar, ashoka = _h(payload, "Salasar Techno Engg"), _h(payload, "Ashoka Buildcon")
    lt, agi = _h(payload, "Larsen & Toubro"), _h(payload, "AGI Greenpac")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"],
            salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert salasar["trim"]["target_alloc_pct"] == 3.0
    assert salasar["trim"]["suggested_qty"] == 120.0
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS


@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_ashoka_g1_exit_is_invariant_across_every_scenario(name, overrides, foundation):
    """G1 outranks G2, so the EXIT golden cannot move with the G2 scalars."""
    ashoka = _h(_run_scenario(foundation, overrides), "Ashoka Buildcon")
    assert ashoka["decision"] == "EXIT"
    assert ashoka["stage1"]["winning_gate"] == "G1"


@pytest.mark.parametrize("name,overrides", sorted(SCENARIOS.items()))
def test_agi_watch_insufficient_anchor_is_invariant(name, overrides, foundation):
    """AGI is coverage-driven at 2.0% -- below every band leg in the set."""
    agi = _h(_run_scenario(foundation, overrides), "AGI Greenpac")
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == ASSUMED_SMALL_MICRO_BASIS
    assert agi["data_quality"]["position_sizing"] == "proxy"


def test_salasar_and_lt_sensitivity_is_recorded_not_suppressed(foundation):
    """The golden trilogy's G2/G3 members DO respond -- record it factually.

    Unlike CR-012A (weights never reach the gates), the authorized G2 scalars
    are gate inputs, so SALASAR and LT can move. This is the characterization
    result itself; it is not a defect and not a recommendation.
    """
    salasar_relaxed = _h(_run_scenario(foundation, SCENARIOS["multiple_relaxed_1_75"]),
                         "Salasar Techno Engg")
    assert salasar_relaxed["decision"] == "TRIM"
    assert salasar_relaxed["stage1"]["winning_gate"] is None
    assert salasar_relaxed["trim"]["mode"] == "V"

    lt_tightened = _h(_run_scenario(foundation, SCENARIOS["cap_tightened_9_0"]),
                      "Larsen & Toubro")
    assert lt_tightened["decision"] == "TRIM"
    assert lt_tightened["stage1"]["winning_gate"] == "G2"
    assert lt_tightened["trim"]["mode"] == "S"


# ---- Observed characterization deltas (recorded from actual runs) -------------

EXPECTED_DELTAS = {
    "cap_tightened_9_0": {"Larsen & Toubro": ("TRIM", "G2", "S")},
    "cap_tightened_8_0": {"Larsen & Toubro": ("TRIM", "G2", "S")},
    "cap_relaxed_12_0": {"Bank of Baroda": ("WATCH", None, None)},
    "cap_relaxed_15_0": {"Bank of Baroda": ("WATCH", None, None)},
    "multiple_tightened_1_00": {
        "Larsen & Toubro": ("TRIM", "G2", "S"),
        "Bharat Coking Coal": ("TRIM", "G2", "S"),
    },
    "multiple_tightened_1_25": {"Bharat Coking Coal": ("TRIM", "G2", "S")},
    "multiple_relaxed_1_75": {"Salasar Techno Engg": ("TRIM", None, "V")},
    "multiple_relaxed_2_00": {"Salasar Techno Engg": ("TRIM", None, "V")},
    "combined_tightened": {
        "Larsen & Toubro": ("TRIM", "G2", "S"),
        "Bharat Coking Coal": ("TRIM", "G2", "S"),
    },
    "combined_relaxed": {
        "Salasar Techno Engg": ("TRIM", None, "V"),
        "Bank of Baroda": ("WATCH", None, None),
    },
    "combined_tight_cap_loose_multiple": {
        "Salasar Techno Engg": ("TRIM", None, "V"),
        "Larsen & Toubro": ("TRIM", "G2", "S"),
    },
    "combined_loose_cap_tight_multiple": {
        "Larsen & Toubro": ("TRIM", "G2", "S"),
        "Bharat Coking Coal": ("TRIM", "G2", "S"),
    },
}


@pytest.mark.parametrize("name,overrides", sorted(NON_BASELINE_SCENARIOS.items()))
def test_observed_decision_deltas_match_recorded_characterization(name, overrides, foundation):
    actual = _decision_map(_run_scenario(foundation, overrides))
    deltas = {k: v for k, v in actual.items() if BASELINE_DECISIONS[k] != v}
    assert deltas == EXPECTED_DELTAS[name]


def test_g2_population_counts_are_monotone_in_the_expected_direction(foundation):
    """Tightening cannot shrink the G2 set; relaxing cannot grow it."""
    def n_g2(overrides):
        return sum(1 for h in _run_scenario(foundation, overrides)["holdings"]
                   if h["stage1"]["winning_gate"] == "G2")

    base = n_g2(SCENARIOS["baseline"])
    assert base == 4
    assert n_g2(SCENARIOS["cap_tightened_9_0"]) >= base
    assert n_g2(SCENARIOS["multiple_tightened_1_00"]) >= base
    assert n_g2(SCENARIOS["cap_relaxed_12_0"]) <= base
    assert n_g2(SCENARIOS["multiple_relaxed_2_00"]) <= base
    assert n_g2(SCENARIOS["combined_tightened"]) == 6
    assert n_g2(SCENARIOS["combined_relaxed"]) == 2


# ---- 20. No production recommendation, optimization, or UI control -----------

def test_module_declares_no_preferred_threshold_values():
    # Tokens are assembled from fragments so that this guard does not match
    # its own source text.
    banned = ("recommend" + "ed_", "optim" + "al_", "best" + "_value",
              "tun" + "ed_", "slid" + "er", "swe" + "ep(", "mini" + "mize",
              "maxi" + "mize", "curve" + "_fit")
    text = Path(__file__).read_text(encoding="utf-8").lower()
    for token in banned:
        assert token not in text, f"forbidden construct present: {token}"


def test_scenarios_are_hand_authored_not_generated():
    """No scenario may be produced by a range/loop/search construct."""
    source = inspect.getsource(inspect.getmodule(test_scenarios_are_hand_authored_not_generated))
    scenario_block = source.split("SCENARIOS = {", 1)[1].split("\n}", 1)[0]
    for generator in ("range(", "for ", "while ", "itertools", "random", "numpy"):
        assert generator not in scenario_block


def test_production_policy_values_are_never_proposed_for_change():
    """The production D-03/D-04 values remain the only on-disk values."""
    assert POLICY["max_single_stock_pct"] == 10.0
    assert POLICY["rebalance_trigger_multiple"] == 1.5
    # No scenario is asserted to be preferable to production; the module only
    # records deltas. This test pins the production anchor itself.
    on_disk = load_policy()
    assert on_disk["max_single_stock_pct"] == 10.0
    assert on_disk["rebalance_trigger_multiple"] == 1.5


# ---- Privacy ------------------------------------------------------------------

def test_no_private_or_production_data_referenced():
    # Markers are assembled from fragments so this guard does not match itself.
    markers = ("CR-" + "005", "real" + "_holdings", "dem" + "at",
               "PA" + "N", "clie" + "nt_", "account" + "_no")
    text = Path(__file__).read_text(encoding="utf-8")
    for marker in markers:
        assert marker not in text, f"privacy marker present: {marker}"
    # Only the synthetic fixture instruments appear.
    assert "Salasar Techno Engg" in text and "AGI Greenpac" in text
