# CR-012B — G2 Threshold Sensitivity Characterization

**Status:** MERGED / CURRENT (test/doc-only) — merged to `main` via PR #4 (history: `31073e6`, `ffdf9cb`).

> **CR-020 note (2026-08-27):** the original status line read "FRESH IMPLEMENTATION CANDIDATE". That wording, and the Baseline/Authorization lines below, are retained verbatim as the historical record of how this candidate was authorized; only this status line is restated.
**Baseline:** `origin/main` @ `ab429fbb84a5a5ef6017dca1cf8c31cae87009f2`
**Authorization:** CR-012B Fresh Implementation Authorization (this candidate supersedes no prior evidence; the original CR-012B candidate was lost and is unrecoverable, and its recorded fingerprints, forensic-audit PASS, promotion-preflight PASS, scenario outputs, and test counts are VOID for this candidate. This is a new implementation, not a reconstruction, and claims no equivalence to the lost candidate.)

---

## 1. Purpose

Characterize how the existing, authoritative backend **G2 allocation gate**
responds when its two authorized policy scalars are varied, using the engine's
existing non-persisting what-if mechanism:

```
policy_overrides
    ->
decide_on_foundation(...)
    ->
temporary DecisionPayload (not persisted, does not mutate policy.yaml)
```

This is an **analysis/characterization exercise**, expressed entirely as
automated tests (`tests/test_cr012b.py`) plus this explanatory document. It
adds no new runtime capability.

CR-012B is the G2-threshold counterpart to the completed CR-012A weight-only
characterization. The two are disjoint: CR-012A varied Stage 2 composite
weights, which `app/gates.py` never reads; CR-012B varies gate inputs and does
not touch weights.

---

## 2. Scope

In scope:

- Exercising the **existing** `app.pipeline.decide_on_foundation(policy_overrides=...)`
  what-if path with a finite, named set of **G2-scalar-only** override scenarios.
- Verifying that exactly two policy dimensions are varied.
- Verifying `target_bands` is never overridden and never changes.
- Verifying `target_top = band_for(bucket, policy)[1]` holds as an invariant.
- Re-checking the CR-018 A1 disagreement windows as **fixed checkpoints** under
  every scenario.
- Recording, for the existing synthetic fixture portfolio, which named
  scenarios change any holding's decision relative to the production baseline.

Out of scope: see [Non-goals](#4-non-goals).

---

## 3. Authorized parameters

CR-012B varies exactly the two policy scalars consumed by the G2 predicate in
`app/gates.py`:

```python
cap   = policy["max_single_stock_pct"]
rebal = band[1] * policy["rebalance_trigger_multiple"]
g2    = alloc_pct is not None and (alloc_pct > cap or alloc_pct > rebal)
```

| Dimension | Production default (`policy/policy.yaml`) | Role |
|---|---|---|
| `max_single_stock_pct` | 10.0 | D-03 absolute cap leg |
| `rebalance_trigger_multiple` | 1.5 | D-04 multiple, applied to `target_top` |

No other policy key is varied by any CR-012B scenario. This is enforced by
`test_scenario_only_overrides_authorized_g2_parameters` and
`test_no_scenario_touches_any_forbidden_policy_key`.

Note that `band[1]` — `target_top` — is the **third** input to the band leg. It
is deliberately **not** an authorized dimension; see §5.

---

## 4. Non-goals

CR-012B does **NOT**:

- authorize production threshold changes
- authorize production policy changes
- introduce G2 threshold sliders or any frontend control
- perform optimization, parameter sweeps, threshold fitting, or threshold tuning
- search for or propose a "better" cap or multiple
- make any production recommendation
- constitute a backtest
- change methodology or gate logic
- activate D-14
- activate Watchlist
- create a new what-if capability

It also does not modify `policy/policy.yaml`, gates (`app/gates.py`), scoring
(`app/scoring.py`), trim logic (`app/trim.py`), tax logic (`app/tax.py`),
confidence (`app/confidence.py`), schema (`app/schema.py`), fixtures, the
frontend, `MANIFEST.sha256`, `RELEASE-v1.md`, tags, releases, dependencies, or
any existing test file.

---

## 5. target_bands exclusion and the target_top invariant

`target_bands` is **explicitly excluded** from variation. This is a hard
firewall, not a stylistic choice, for two reasons:

1. **`band[1]` feeds G2 *and* trim sizing.** `app/trim.py` uses
   `target_top = band[1]` to compute `target_alloc_pct` and `suggested_qty`.
   Varying a band edge would silently perturb `GOLDEN-G2-TRIM-S-SALASAR`
   (`target_alloc_pct == 3.0`, `suggested_qty == 120.0`).
2. **Existing validation would not catch a bad edge.**
   `app/policy.py::validate_policy` only asserts `b[1] > b[0]` for each band,
   so an altered edge would pass validation and corrupt goldens undetected.

`target_top` is therefore **verified, never varied**. Across all 13 scenarios
the tests assert:

```
band_for("large",  policy)[1] == 8.0
band_for("mid",    policy)[1] == 5.0
band_for("small",  policy)[1] == 3.0
band_for("micro",  policy)[1] == 3.0
band_for(None,     policy)[1] == 3.0      (CR-009 fallback)

target_bands == {"large": [4.0, 8.0], "mid": [2.0, 5.0], "small_micro": [1.0, 3.0]}
```

`test_cr018_target_top_implementation_is_unchanged` additionally asserts the
source of `evaluate_gates` still computes
`rebal = band[1] * policy["rebalance_trigger_multiple"]` and contains no
midpoint construct, so the rejected A2 rule cannot silently return.

---

## 6. Scenario definitions

Thirteen named, deterministic, G2-scalars-only scenarios are defined in
`tests/test_cr012b.py::SCENARIOS`. Each is a finite hand-authored vector, not
the output of an optimizer or parameter search, and **none is a proposed
production threshold**.

| Scenario | `max_single_stock_pct` | `rebalance_trigger_multiple` |
|---|---|---|
| `baseline` | 10.0 (prod) | 1.5 (prod) |
| `cap_tightened_9_0` | 9.0 | — |
| `cap_tightened_8_0` | 8.0 | — |
| `cap_relaxed_12_0` | 12.0 | — |
| `cap_relaxed_15_0` | 15.0 | — |
| `multiple_tightened_1_00` | — | 1.00 |
| `multiple_tightened_1_25` | — | 1.25 |
| `multiple_relaxed_1_75` | — | 1.75 |
| `multiple_relaxed_2_00` | — | 2.00 |
| `combined_tightened` | 9.0 | 1.25 |
| `combined_relaxed` | 12.0 | 2.00 |
| `combined_tight_cap_loose_multiple` | 9.0 | 2.00 |
| `combined_loose_cap_tight_multiple` | 12.0 | 1.00 |

`baseline` passes no `policy_overrides` at all — it uses the on-disk production
values unmodified, purely to establish the comparison anchor.

**Bounding rationale.** All cap values stay far above the
`min_position_alloc_pct` floor (0.5), so every scenario satisfies
`validate_policy` with zero errors (asserted by
`test_scenario_policy_remains_valid_under_existing_validation`). Values were
chosen to straddle the CR-018 checkpoint windows and the fixture portfolio's
actual allocations — not by any search procedure.

---

## 7. Fixed inputs

All scenarios share the same fixed foundation, built once per test module from
the existing synthetic fixtures — no new fixtures were created:

- `fixtures/portfolio.csv`
- `fixtures/screener.csv`
- `fixtures/ledger.csv`
- `as_of = 2026-08-22`
- `app.pipeline.run_foundation(...)` output, reused as the base for every
  `decide_on_foundation(...)` what-if call

Hysteresis is disabled for a clean per-scenario comparison.

No raw CR-005 data, real holdings, real transactions, or private financial
examples are used anywhere in this characterization.

---

## 8. Characterization outputs (this repository, this fixture set)

These are **factual outputs** of running the existing engine against existing
fixtures under this candidate's tests — not predictions and not recommendations.

### 8.1 Fixture allocation surface

| Instrument | Bucket | `alloc_pct` | `target_top` | `1.5 × top` |
|---|---|---|---|---|
| Salasar Techno Engg | micro | 5.20 | 3.0 | 4.5 |
| Ashoka Buildcon | small | 25.82 | 3.0 | 4.5 |
| Larsen & Toubro | large | 9.64 | 8.0 | 12.0 |
| AGI Greenpac | *(none)* | 2.00 | 3.0 | 4.5 |
| Bajaj Finance | large | 18.48 | 8.0 | 12.0 |
| HDFC Bank | large | 20.60 | 8.0 | 12.0 |
| Bank of Baroda | large | 10.67 | 8.0 | 12.0 |
| DAM Capital Advisors | small | 1.04 | 3.0 | 4.5 |
| Bharat Coking Coal | mid | 6.55 | 5.0 | 7.5 |

### 8.2 Baseline decisions (production thresholds)

| Instrument | Decision | Winning gate | Trim mode |
|---|---|---|---|
| Salasar Techno Engg | TRIM | G2 | S |
| Ashoka Buildcon | EXIT | G1 | — |
| Larsen & Toubro | HOLD | G3 | — |
| AGI Greenpac | WATCH | — | — |
| Bajaj Finance | TRIM | G2 | S |
| HDFC Bank | TRIM | G2 | S |
| Bank of Baroda | TRIM | G2 | S |
| DAM Capital Advisors | WATCH | — | — |
| Bharat Coking Coal | WATCH | — | — |

Baseline `content_hash`: `7a6592699d802ac6245bac4b7ac7d8414750ab66add32e7188b5dbef3878617e`
Baseline G2 population: **4** (Salasar, Bajaj Finance, HDFC Bank, Bank of Baroda)

### 8.3 Per-scenario deltas vs. baseline

Only changed instruments are shown. Every scenario's `content_hash` differs
from baseline.

| Scenario | G2 count | Decision changes vs. baseline |
|---|---|---|
| `baseline` | 4 | — |
| `cap_tightened_9_0` | 5 | Larsen & Toubro: HOLD/G3 → TRIM/G2/S |
| `cap_tightened_8_0` | 5 | Larsen & Toubro: HOLD/G3 → TRIM/G2/S |
| `cap_relaxed_12_0` | 3 | Bank of Baroda: TRIM/G2/S → WATCH |
| `cap_relaxed_15_0` | 3 | Bank of Baroda: TRIM/G2/S → WATCH |
| `multiple_tightened_1_00` | 6 | Larsen & Toubro: HOLD/G3 → TRIM/G2/S; Bharat Coking Coal: WATCH → TRIM/G2/S |
| `multiple_tightened_1_25` | 5 | Bharat Coking Coal: WATCH → TRIM/G2/S |
| `multiple_relaxed_1_75` | 3 | Salasar Techno Engg: TRIM/G2/**S** → TRIM/(no gate)/**V** |
| `multiple_relaxed_2_00` | 3 | Salasar Techno Engg: TRIM/G2/**S** → TRIM/(no gate)/**V** |
| `combined_tightened` | 6 | Larsen & Toubro: HOLD/G3 → TRIM/G2/S; Bharat Coking Coal: WATCH → TRIM/G2/S |
| `combined_relaxed` | 2 | Salasar Techno Engg: TRIM/G2/S → TRIM/(no gate)/V; Bank of Baroda: TRIM/G2/S → WATCH |
| `combined_tight_cap_loose_multiple` | 4 | Salasar Techno Engg: TRIM/G2/S → TRIM/(no gate)/V; Larsen & Toubro: HOLD/G3 → TRIM/G2/S |
| `combined_loose_cap_tight_multiple` | 6 | Larsen & Toubro: HOLD/G3 → TRIM/G2/S; Bharat Coking Coal: WATCH → TRIM/G2/S |

### 8.4 Material difference from CR-012A

CR-012A found the golden trilogy **completely insensitive** to weight variation,
because gates run first and never consult `policy["weights"]`.

**CR-012B finds the opposite, and this is the central characterization result:**
the authorized scalars *are* gate inputs, so gate-driven outcomes move.

- **Larsen & Toubro** (9.64%, large) sits between `target_top` 8.0 and the
  production cap 10.0. Tightening the cap to 9.0 pulls it over the D-03 leg:
  HOLD/G3 → TRIM/G2/S. Its G3 tax-defer is *outranked*, consistent with the
  frozen rule that risk caps are never tax-deferred.
- **Salasar Techno Engg** (5.20%, micro) exceeds the production band leg
  `1.5 × 3.0 = 4.5`. Relaxing the multiple to 1.75 lifts the leg to 5.25, above
  5.20, so the G2 gate stops firing. The holding still books — but as a
  **valuation-driven TRIM-V** from Stage 2, not a gate-driven TRIM-S. The
  golden *anchor* `GOLDEN-G2-TRIM-S-SALASAR` describes behavior at production
  thresholds and is unchanged there.
- **Ashoka Buildcon** (EXIT/G1) and **AGI Greenpac** (WATCH/INSUFFICIENT) are
  invariant across all 13 scenarios — G1 outranks G2, and AGI at 2.0% is below
  every band leg in the set.

This sensitivity is expected and is precisely what CR-012B exists to record. It
is **not** a defect, and it is **not** an argument for changing production
thresholds.

---

## 9. CR-018 A1 checkpoint results

The CR-018 A1 disagreement windows are reused strictly as **fixed checkpoints**.
Under production policy they reproduce the CR-018 contract exactly:

| Bucket | Window | 1st edge | 2nd edge | Just above |
|---|---|---|---|---|
| large | 9.0 – 10.0 | no G2 | no G2 | G2 at 10.0001 |
| mid | 5.25 – 7.5 | no G2 | no G2 | G2 at 7.5001 |
| small | 3.0 – 4.5 | no G2 | no G2 | G2 at 4.5001 |
| micro | 3.0 – 4.5 | no G2 | no G2 | G2 at 4.5001 |
| *(unknown → CR-009 fallback)* | 3.0 – 4.5 | no G2 | no G2 | G2 at 4.5001 |

Under the non-baseline scenarios the checkpoints move — that is the
characterization — but every outcome is **fully explained by the closed-form A1
predicate** `alloc > cap OR alloc > target_top × multiple`, asserted pointwise
by `test_cr018_checkpoints_are_explained_entirely_by_the_two_scalars`. Selected
observations:

- `cap_tightened_8_0` — the large window collapses entirely (9.0 now exceeds the
  8.0 cap), while mid/small/micro are untouched: a cap-leg-only effect.
- `cap_relaxed_12_0` / `cap_relaxed_15_0` — the large bucket stops firing even
  at 10.0001, because the band leg `1.5 × 8.0 = 12.0` now binds instead of D-03.
  This is the **leg-masking** property: for large holdings the band leg is
  normally unreachable behind the D-03 cap.
- `multiple_tightened_1_00` — every band leg drops to `1.0 × top`, so mid fires
  from 5.25 and small/micro from 4.0.
- `multiple_relaxed_1_75` / `_2_00` — mid/small/micro stop firing anywhere in
  their windows; only the large bucket's D-03 leg still fires at 10.0001.

`tests/test_cr018.py` remains **unmodified and passing 7/7**, and
`test_cr018_seven_test_contract_file_is_untouched` asserts that file still
defines exactly 7 tests referencing `target_top`.

---

## 10. Baseline invariants

Across all thirteen scenarios the following hold, asserted by
`tests/test_cr012b.py`:

1. The `baseline` scenario is bit-identical, by `content_hash`, to calling
   `decide_on_foundation` with no `policy_overrides` at all.
2. `target_bands` never appears in an override and never changes value.
3. `target_top` remains `band_for(bucket, policy)[1]` for every bucket.
4. G1 methodology is unchanged: a governance or quality break still yields
   EXIT/G1 regardless of the G2 scalars.
5. G3 methodology is unchanged: near-LTCG defer still yields HOLD/G3 for
   in-band holdings, and valuation-extreme suppression still applies.
6. Gate precedence G1 > G2 > G3 is intact; G2 still yields TRIM-S and is never
   tax-deferred.
7. Ashoka Buildcon (EXIT/G1) and AGI Greenpac (WATCH/INSUFFICIENT, `bucket=None`,
   `assumed_small_micro` basis, `position_sizing` = proxy) are invariant.
8. `opportunity_cost.source` is always one of `peg_proxy` / `missing`; never
   `hurdle_d14`, never `watchlist`.
9. Every scenario output validates as a DecisionPayload (enforced inside
   `decide_on_foundation` via `app.schema.validate_decision_payload`).
10. Every scenario policy passes `validate_policy` with zero errors.
11. Production on-disk values remain `max_single_stock_pct = 10.0` and
    `rebalance_trigger_multiple = 1.5`.

---

## 11. Determinism, isolation, and privacy

**Determinism.** Each scenario produces an identical `content_hash` on repeated
execution, both against a shared foundation and across independently rebuilt
foundations. All 13 scenarios yield mutually distinct hashes from baseline.

**Isolation.** Every scenario runs through the existing, already-audited what-if
path, proven non-persisting by
`tests/test_audit.py::test_i_what_if_does_not_persist_or_mutate_policy` — which
already exercises exactly these two keys. CR-012B adds its own confirmations:

- `test_policy_yaml_not_mutated_by_scenarios` — running all scenarios leaves the
  on-disk policy file byte-identical.
- `test_in_memory_default_policy_is_not_mutated_by_scenarios` — the loaded
  policy dict is unchanged after the full scenario set.
- `test_scenarios_never_persist_a_run` — `RunStore.save_run` is never invoked.
- `test_no_scenario_execution_path_writes_to_the_store` — the store stays empty.
- `test_fixture_files_are_not_modified_by_running_scenarios` — fixture content
  is unchanged (compared line-ending-normalized; the repo's `conftest.py`
  regenerates fixtures per session with platform-native endings, a pre-existing
  behavior unrelated to this candidate).

**Privacy.** Only synthetic fixture instruments appear. No real holdings, no
CR-005 inputs, no account identifiers.

---

## 12. Interpretation rules

- A scenario's deltas describe **sensitivity of the existing G2 gate to its two
  authorized scalars**, not a judgment about which thresholds are "better."
- Any holding whose decision changes is, by construction, one whose `alloc_pct`
  sits between the baseline and scenario values of `max_single_stock_pct` or
  `target_top × rebalance_trigger_multiple`.
- G1-controlled holdings are insensitive by design — G1 outranks G2.
- For **large-bucket** holdings the band leg (`1.5 × 8.0 = 12.0`) sits above the
  D-03 cap (10.0), so the cap leg normally binds first. Relaxing the cap past
  12.0 hands control to the band leg. Any reading of large-bucket results must
  account for this leg-masking.
- A holding leaving G2 does not necessarily stop booking: it may still be
  actioned by Stage 2 as TRIM-V (see Salasar under a relaxed multiple).
- These outputs are reproducible exactly by re-running `tests/test_cr012b.py`
  against this exact fixture set and `as_of` date; they are not projections
  about any other portfolio or date.

---

## 13. Acceptance criteria

This candidate is accepted as a valid CR-012B characterization artifact if and
only if:

1. `tests/test_cr012b.py` passes in full, deterministically, on repeated runs.
2. The full existing regression suite continues to pass unmodified.
3. No file other than `tests/test_cr012b.py` and this document is created or
   modified.
4. `policy/policy.yaml`, all `fixtures/*`, `app/*`, `frontend/*`, schema,
   `MANIFEST.sha256`, `RELEASE-v1.md`, and all existing tests are byte-identical
   before and after running these tests.
5. `target_bands` is never overridden and never changes.
6. `target_top` is verified as `band_for(bucket, policy)[1]` in every scenario.
7. CR-018 remains 7/7 and unmodified.
8. Golden trilogy and AGI anchors are unaffected by the `baseline` scenario.
9. No parameter other than `max_single_stock_pct` and
   `rebalance_trigger_multiple` is varied by any scenario.

**Observed results at candidate completion:**

| Check | Result |
|---|---|
| `pytest tests/test_cr012b.py` | **217 passed** |
| Focused regression (audit, policy, scoring, decision, gates, cr018) | **66 passed**, 1 known warning |
| Full suite | **450 passed**, 1 known warning |
| CR-018 | **7 passed** |

The single warning is the pre-existing FastAPI/Starlette `TestClient`
deprecation notice, unrelated to this candidate.

---

## 14. Explicit limitation of authority

This document and its tests are **characterization only**. They do **not**
authorize, and must not be cited to justify:

- production threshold changes
- production policy changes
- G2 threshold sliders or any frontend control
- optimization, threshold fitting, or threshold tuning
- production recommendations
- backtesting or any backtest harness
- D-14 activation or Watchlist activation
- any modification to `target_bands`, CR-018 behavior, or the golden anchors

Any such change requires its own separately authorized named CR.

---

## 15. Known limitations

- The characterization covers exactly thirteen named scenarios against one fixed
  synthetic fixture portfolio at one fixed `as_of` date. It is not exhaustive
  over the two-parameter space and is not a sensitivity surface or gradient
  analysis.
- Decision changes are sensitive to the specific fixture allocations; the same
  scenarios against a different portfolio could show different or no deltas.
- Large-bucket results are shaped by D-03/D-02 leg masking (§12) and should not
  be generalized to portfolios whose band tops exceed the cap.
- Only `bucket`-classified and CR-009 fallback paths present in this fixture set
  are exercised; no scenario introduces new bucket data.
- This document does not evaluate historical or backtested outcome quality of
  any scenario — that would require the separately gated, not-yet-implemented
  Backtest Methodology Addendum harness, explicitly out of scope here.
- The `policy/policy.yaml` D-04 comment still reads "× target mid-point" while
  the implemented and authorized rule is `× target_top`. Per
  `docs/v1.1-authority-decisions-v1.md` §3 this is **stale wording, not a
  competing rule**, and is explicitly out of CR-012B's scope to fix. It is
  recorded here as an observation only.
- CR-012A (weight-only sensitivity) is a distinct, completed CR. It is not
  reopened, modified, or superseded by this document or its tests.
