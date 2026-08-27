# CR-012A — Weight-Only Sensitivity Characterization

**Status:** MERGED / CURRENT (test/doc-only) — merged to `main` via PR #3 (history: `eb5cd7a`, `ab429fb`).

> **CR-020 note (2026-08-27):** the original status line read "FRESH IMPLEMENTATION CANDIDATE". That wording, and the Baseline/Authorization lines below, are retained verbatim as the historical record of how this candidate was authorized; only this status line is restated.
**Baseline:** `origin/main` @ `dd84555eed6275a5895a8c9326be664d35bf3122`
**Authorization:** CR-012A Fresh Implementation Authorization (this candidate supersedes no prior evidence; the original CR-012A candidate was lost and is unrecoverable — see governance record. This is a new implementation, not a reconstruction, and claims no equivalence to the lost candidate.)

---

## 1. Purpose

Characterize how the existing, authoritative backend decision engine responds
when the Stage 2 category **weights** are varied, using the engine's existing
non-persisting what-if mechanism:

```
policy_overrides
    ->
decide_on_foundation(...)
    ->
temporary DecisionPayload (not persisted, does not mutate policy.yaml)
```

This is an **analysis/characterization exercise**, expressed entirely as
automated tests (`tests/test_cr012a.py`) plus this explanatory document. It
adds no new runtime capability.

---

## 2. Scope

In scope:

- Exercising the **existing** `app.pipeline.decide_on_foundation(policy_overrides=...)` /
  `app.pipeline.run_engine(policy_overrides=...)` what-if path with a finite,
  named set of Stage 2 **weight-only** override scenarios.
- Verifying the six Stage 2 category weights are the only policy dimension
  varied.
- Verifying the what-if isolation contract already established by
  `tests/test_audit.py::test_i_what_if_does_not_persist_or_mutate_policy`
  continues to hold under these specific weight scenarios.
- Recording, for the existing synthetic fixture portfolio
  (`fixtures/portfolio.csv`, `fixtures/screener.csv`, `fixtures/ledger.csv`),
  which named scenarios change any holding's decision relative to the
  production-weighted baseline, and which do not.

Out of scope: see [Non-goals](#4-non-goals).

---

## 3. Six weight dimensions

CR-012A varies exactly the six Stage 2 category weights defined in
`app/scoring.py::WEIGHT_KEYS` and validated by `app/policy.py::validate_policy`:

| Dimension | Production default (`policy/policy.yaml`) |
|---|---|
| `position_sizing` | 25 |
| `valuation_stretch` | 25 |
| `quality_drift` | 20 |
| `tax_efficiency` | 15 |
| `opportunity_cost` | 10 |
| `technical_regime` | 5 |

No other policy key (bands, target bands, `max_single_stock_pct`,
`rebalance_trigger_multiple`, pledge/quality gate thresholds, LTCG period,
reconciliation tolerance, etc.) is varied by any CR-012A scenario. This is
enforced by `tests/test_cr012a.py::test_scenarios_never_touch_gate_or_band_policy_keys`
and `test_g2_gate_math_is_unchanged_by_weight_scenarios`.

---

## 4. Non-goals

CR-012A does **NOT**:

- authorize production weight changes
- change methodology
- establish G2 thresholds
- establish threshold sliders
- constitute a backtest
- optimize production weights
- activate D-14
- activate Watchlist
- create a new what-if capability

It also does not modify `policy/policy.yaml`, gates (`app/gates.py`), trim
logic (`app/trim.py`), tax logic (`app/tax.py`), confidence methodology
(`app/confidence.py`), Opportunity Cost methodology (`app/scoring.py`
`opportunity_cost`/`opportunity_cost_source`), schema (`app/schema.py`),
fixtures, or the frontend.

---

## 5. Scenario vectors

Nine named, deterministic, weights-only scenarios are defined in
`tests/test_cr012a.py::SCENARIOS`. Each is a finite hand-authored vector, not
the output of an optimizer or parameter search, and none is a proposed
production weight set.

| Scenario | position_sizing | valuation_stretch | quality_drift | tax_efficiency | opportunity_cost | technical_regime |
|---|---|---|---|---|---|---|
| `baseline` | 25 (prod) | 25 (prod) | 20 (prod) | 15 (prod) | 10 (prod) | 5 (prod) |
| `position_sizing_emphasis` | 60 | 10 | 10 | 10 | 5 | 5 |
| `valuation_stretch_emphasis` | 10 | 60 | 10 | 10 | 5 | 5 |
| `quality_drift_emphasis` | 10 | 10 | 60 | 10 | 5 | 5 |
| `tax_efficiency_emphasis` | 10 | 10 | 10 | 60 | 5 | 5 |
| `opportunity_cost_emphasis` | 10 | 10 | 10 | 10 | 55 | 5 |
| `technical_regime_emphasis` | 10 | 10 | 10 | 10 | 5 | 55 |
| `balanced_alternative` | 17 | 17 | 17 | 17 | 16 | 16 |
| `reduced_opportunity_cost` | 27 | 27 | 21 | 16 | 3 | 6 |
| `increased_opportunity_cost` | 20 | 20 | 15 | 10 | 30 | 5 |

`baseline` passes no `policy_overrides` at all — it uses the on-disk
production weights unmodified, purely to establish the comparison anchor.

---

## 6. Fixed inputs

All scenarios share the same fixed foundation, generated once per test run
from the existing synthetic fixtures — no new fixtures were created:

- `fixtures/portfolio.csv`
- `fixtures/screener.csv`
- `fixtures/ledger.csv`
- `as_of = 2026-08-22`
- `app.pipeline.run_foundation(...)` output (built once, then reused as the
  base for every `decide_on_foundation(...)` what-if call in the scenario set)

No raw CR-005 data, real holdings, real transactions, or private financial
examples are used anywhere in this characterization.

---

## 7. Characterization outputs (this repository, this fixture set)

Running the nine scenarios against the current fixture portfolio (via
`decide_on_foundation`, hysteresis disabled for a clean per-scenario
comparison) produces the following **observed** results. These are factual
outputs of running the existing engine against existing fixtures under this
candidate's tests — not predictions and not recommendations.

**Baseline decisions** (production weights):

| Instrument | Decision |
|---|---|
| Salasar Techno Engg | TRIM |
| Ashoka Buildcon | EXIT |
| Larsen & Toubro | HOLD |
| AGI Greenpac | WATCH |
| Bajaj Finance | TRIM |
| HDFC Bank | TRIM |
| Bank of Baroda | TRIM |
| DAM Capital Advisors | WATCH |
| Bharat Coking Coal | WATCH |

**Per-scenario deltas vs. baseline** (only changed instruments shown; every
scenario's `content_hash` differs from baseline because composite scores
shift even where the banded decision does not):

| Scenario | Decision changes vs. baseline |
|---|---|
| `position_sizing_emphasis` | Bharat Coking Coal: WATCH → TRIM |
| `valuation_stretch_emphasis` | DAM Capital Advisors: WATCH → TRIM |
| `quality_drift_emphasis` | DAM Capital Advisors: WATCH → HOLD; Bharat Coking Coal: WATCH → HOLD |
| `tax_efficiency_emphasis` | DAM Capital Advisors: WATCH → TRIM |
| `opportunity_cost_emphasis` | Bharat Coking Coal: WATCH → HOLD |
| `technical_regime_emphasis` | (none — composite scores shift but no holding crosses a band boundary) |
| `balanced_alternative` | (none) |
| `reduced_opportunity_cost` | (none) |
| `increased_opportunity_cost` | (none) |

The golden trilogy (`SALASAR → TRIM-S / G2`, `ASHOKA → EXIT / G1`,
`LT → HOLD / G3`) and the AGI Greenpac `WATCH / INSUFFICIENT` anchor are
**unchanged in every scenario**, because all three are gate-driven (G1/G2/G3)
or coverage-driven outcomes that do not depend on Stage 2 composite weights.
This is asserted directly by
`test_golden_trilogy_unaffected_by_baseline_scenario` for the baseline case,
and is consistent with `test_g2_gate_math_is_unchanged_by_weight_scenarios`,
which shows gate evaluation does not consume weights at all.

---

## 8. What-if isolation

Every scenario is executed through the existing, already-audited what-if
path (`decide_on_foundation`), which is proven non-persisting and
non-mutating by `tests/test_audit.py::test_i_what_if_does_not_persist_or_mutate_policy`.
CR-012A's own tests add a second, weight-scenario-specific confirmation:

- `test_policy_yaml_not_mutated_by_scenarios` — running all nine scenarios
  leaves the on-disk policy file byte-identical and leaves in-memory default
  weights unchanged.
- No scenario writes a run to the store; none of the CR-012A tests calls
  `RunStore.save_run`.

---

## 9. Baseline invariants

Across all nine scenarios, the following must hold (and are asserted by
`tests/test_cr012a.py`):

1. The `baseline` scenario (no override) is bit-identical, by `content_hash`,
   to calling `decide_on_foundation` with no `policy_overrides` at all.
2. The golden trilogy and AGI Greenpac anchor are unaffected in the baseline
   scenario.
3. G2 gate evaluation (`app/gates.py::evaluate_gates`) is identical whether or
   not Stage 2 weights are overridden, for a fixed set of gate inputs —
   because gate evaluation never reads `policy["weights"]`.
4. `opportunity_cost` provenance (`source`) is always one of
   `peg_proxy` / `watchlist` / `missing`, and is never `watchlist` in this
   fixture set (no watchlist ingest path exists), under every scenario.
5. Every scenario output validates as a DecisionPayload (validation is
   enforced inside `decide_on_foundation` itself via
   `app.schema.validate_decision_payload`).

---

## 10. Interpretation rules

- A scenario's decision deltas describe **sensitivity of the existing scorer
  to weight allocation**, not a judgment about which weighting is "better."
- Any holding whose decision changes under a given scenario is, by
  construction, one whose *composite* score (not gate outcome) sits near a
  band boundary (`app/scoring.py::band_of`, edges 30/55/75) under the
  baseline weights; emphasizing a category can push it across that boundary.
- Holdings already gate-controlled (G1/G2/G3) are insensitive to weight
  changes by design — the gates run first and never consult
  `policy["weights"]`.
- These outputs are reproducible exactly by re-running
  `tests/test_cr012a.py` against this exact fixture set and `as_of` date;
  they are not projections about any other portfolio or date.

---

## 11. Acceptance criteria

This candidate is accepted as a valid CR-012A characterization artifact if
and only if:

1. `tests/test_cr012a.py` passes in full, deterministically, on repeated runs.
2. The full existing regression suite (`pytest`) continues to pass unmodified.
3. No file other than `tests/test_cr012a.py` and this document is
   created or modified.
4. `policy/policy.yaml`, all `fixtures/*`, schema, and frontend files are
   byte-identical before and after running these tests.
5. The golden trilogy and AGI Greenpac anchors are unaffected by the
   `baseline` scenario.
6. No G2/gate/band/trim/tax/confidence/Opportunity-Cost/D-14/Watchlist
   parameter is varied by any scenario.

---

## 12. Known limitations

- The characterization set covers exactly nine named scenarios against one
  fixed synthetic fixture portfolio at one fixed `as_of` date. It is not
  exhaustive over the weight simplex and is not a sensitivity surface or
  gradient analysis.
- Composite-score-driven decision changes are sensitive to the specific
  fixture data (`fixtures/screener.csv` proxy fundamentals); the same
  scenarios against a different portfolio could show different (or no)
  decision deltas.
- This document does not evaluate historical/backtested outcome quality of
  any scenario — that would require the (separately gated, not-yet-
  implemented) Backtest Methodology Addendum harness, which is explicitly
  out of scope here.
- `technical_regime_emphasis`, `balanced_alternative`,
  `reduced_opportunity_cost`, and `increased_opportunity_cost` change every
  holding's numeric composite score (hence `content_hash`) without moving
  any holding across a decision-band boundary in this particular fixture
  set; this is a property of where this fixture set's composite scores sit
  relative to band edges, not a general claim about those weightings.
- CR-012B (G2 sensitivity) is a distinct, separately gated future CR and is
  not addressed, exercised, or unblocked by this document or its tests.
