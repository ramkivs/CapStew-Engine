# CAPITAL STEWARD ENGINE
# CR-015 — Backtest Methodology Addendum v1

**Status:** CR-015 addendum prepared · documentation artifact only  
**Authority basis:** `docs/v1.1-authority-decisions-v1.md`, Decision D — Backtest Methodology Addendum  
**Baseline:** V1.1 main after CR-001, CR-009, CR-018, and CR-007  
**Release status:** v1.1 release **not** authorized  

---

## 0. Governance boundary

This artifact is the CR-015 Backtest Methodology Addendum authorized by Gate V1.1-A.

It is **not** a runtime implementation. It does not authorize or introduce:

- a backtest harness
- a backtest UI
- historical archive ingestion
- sold-ledger replay implementation
- benchmark data integration
- frontend changes
- fixture changes
- policy changes
- scoring changes
- gate changes
- weight or threshold optimization
- eligibility or confidence changes
- tax-engine changes
- trim-engine changes
- D-14 operationalization
- `hurdle_d14`
- watchlist ingestion or scoring
- `schema_version`
- release, tag, or version changes

Current protected state remains:

| Item | State |
|---|---|
| CR-001 | COMPLETE / MAIN |
| CR-009 | COMPLETE / MAIN |
| CR-018 | COMPLETE / MAIN |
| CR-007 | COMPLETE / MAIN |
| V1.0.0 | FROZEN |
| V1.1-A | ACCEPTED |
| RELEASE | NOT AUTHORIZED |

---

## 1. Permanent rule

```text
BACKTEST = EVALUATION FRAMEWORK
```

and not:

```text
BACKTEST = METHODOLOGY OPTIMIZATION LOOP
```

Historical backtest results must **never** silently redefine, retune, or override the frozen methodology. If a future backtest reveals poor outcomes, the result is evidence for a separate authority decision, not permission to change gates, weights, thresholds, fixtures, policy, or golden expectations.

Backtesting is therefore a measurement and audit discipline: it asks whether the engine’s decisions would have behaved as intended under specified historical conditions. It does not decide what the methodology should have been.

---

## 2. Evaluation principles

Any future implementation of a backtest must preserve these principles:

1. **Decision replay is historical, not adaptive.** The engine must replay the policy, inputs, and code state applicable to the historical decision under evaluation.
2. **Policy-at-the-time controls.** Every replayed decision must cite `policy_version` and `content_hash` when available.
3. **No hindsight inputs.** Data unavailable at the decision timestamp must not be used to create that decision.
4. **Outcome measurement is separate from decision generation.** Outcomes may be measured after the fact, but may not leak into the decision replay.
5. **Mechanics-only mode is valid.** When outcome data quality is insufficient, a backtest may verify engine mechanics without claiming performance validity.
6. **Goldens are permanent anchors.** Existing goldens remain regression fixtures, not optimization targets.

---

## 3. The 18 required backtest questions

### 3.1 Successful EXIT

An EXIT is successful when, after the decision point, the position’s risk thesis remains broken or worsens such that continued holding would not have been justified under the frozen rules.

A future evaluation may consider:

- subsequent drawdown avoided
- persistence or worsening of G1 governance / thesis-break evidence
- absence of a later rule-consistent re-entry signal
- opportunity loss avoided relative to staying invested

An EXIT must not be judged successful merely because price declined after sale if the original EXIT evidence was not available at decision time.

### 3.2 Successful TRIM-S

TRIM-S is the sizing/risk-cap trim. It is successful when it reduces allocation back toward the authorized band top while preserving the methodology’s risk-control intent.

A future evaluation may consider:

- allocation after trim versus `target_top`
- reduction of position concentration risk
- avoidance of later concentration-driven drawdown
- realized tax and transaction cost drag as evaluation metrics, not decision overrides

TRIM-S success must be measured against the frozen target-band and participation constraints that existed at decision time.

### 3.3 Successful TRIM-V

TRIM-V is the valuation-pressure trim. It is successful when partial realization reduces exposure to valuation stretch while preserving residual participation.

A future evaluation may consider:

- subsequent mean reversion or underperformance after valuation stretch
- retained upside participation from the unsold residual position
- realized tax and transaction costs
- whether the trim size remained within the frozen participation and dust-floor constraints

TRIM-V success must not be used to tune valuation thresholds without a separate authority decision.

### 3.4 Successful HOLD

A HOLD is successful when no action was warranted and the position remained within the acceptable methodology envelope over the evaluation horizon.

A future evaluation may consider:

- no triggered hard gate during the follow-up window
- acceptable drawdown relative to benchmark / sector controls
- preserved long-term upside when selling would have been premature
- continued evidence sufficiency

A HOLD should not be considered failed solely because another asset outperformed it unless opportunity-cost methodology explicitly authorized such a comparison at decision time.

### 3.5 Successful WATCH

A WATCH is successful when insufficient or advisory-quality evidence was handled conservatively and did not force an unsupported action.

A future evaluation may consider:

- whether missing evidence later resolved without requiring retrospective action
- whether WATCH prevented unsupported trimming or exiting
- whether review cadence was followed
- whether later evidence would have changed the decision under the frozen rules

WATCH is an evidence-quality state as much as an investment-action state. Its evaluation must consider data availability.

### 3.6 Successful HARVEST

A HARVEST is successful when a stronger profit-booking decision captures gains or reduces risk without violating tax, trim, and residual-position constraints.

A future evaluation may consider:

- subsequent reversal or underperformance after harvest
- tax-adjusted realized value
- retained / redeployed capital outcome, if data quality supports it
- whether the decision followed the frozen score bands and evidence requirements

HARVEST outcomes must not be used to retune composite band thresholds without separate authority.

### 3.7 Evaluation horizons

Backtest reporting must define horizons before measurement. Suggested horizon families are:

| Horizon | Use |
|---|---|
| Immediate / 1–7 days | Checks execution-risk and gate urgency |
| Short / 30 days | Review cadence and fast reversal risk |
| Medium / 90 days | Typical HOLD / WATCH review horizon |
| Long / 180–365 days | Larger thesis and tax-cycle evaluation |

The selected horizon must match the decision type. For example, G2 concentration controls may be evaluated differently from a long-horizon HOLD.

### 3.8 Tax treatment

Tax effects must be reported as outcome components, not as retroactive methodology changes.

A future backtest should record:

- STCG / LTCG classification at the historical decision point
- realized tax drag for executed trim / exit simulations
- exemption headroom where available
- tax deferral effects for G3 cases
- transaction cost assumptions

Tax treatment must not alter historical decisions unless the frozen decision logic at that time included the relevant tax input.

### 3.9 Market / benchmark controls

Backtest conclusions must separate stock-specific decision quality from broad market movement.

A future evaluation may compare outcomes against:

- broad index movement
- sector / industry benchmarks
- cash or liquid alternatives where authorized
- equal-horizon benchmark returns

Benchmark controls are evaluation aids only. They do not activate D-14 or change opportunity-cost scoring without separate authority.

### 3.10 Sector / theme controls

Sector and theme controls should identify whether a decision succeeded because of stock-specific insight or sector-wide movement.

A future evaluation may record:

- sector return over the evaluation horizon
- theme concentration changes
- peer basket movement
- market-cap bucket effects

Sector controls must not create new gates or alter existing gate precedence.

### 3.11 Survivorship bias

Backtests must account for the fact that current portfolio files may exclude positions that were fully sold before the test period.

A valid performance backtest requires a survivorship-aware universe that includes:

- open positions
- sold positions
- delisted or unavailable positions where relevant
- historical holdings snapshots

If sold or historical universe data is incomplete, the backtest must explicitly label results as biased or mechanics-only.

### 3.12 Hindsight leakage

No future information may be used to generate a historical decision.

Examples of prohibited hindsight leakage:

- using later fundamentals snapshots
- using later market-cap bucket classification
- using known sale outcomes to choose thresholds
- using future benchmark data inside the decision engine
- using later policy versions to replay earlier decisions

Outcome data may be used only after the decision has been generated and frozen for evaluation.

### 3.13 Historical input snapshots

A valid replay requires input snapshots as-of the historical decision date.

Required snapshot families may include:

- portfolio holdings
- screener / fundamentals
- ledger / lots
- sold ledger, when evaluating realized outcomes
- policy version
- engine version
- normalization and calculation versions

When snapshots are missing, the evaluation must downgrade to mechanics-only or explicitly mark data-quality limitations.

### 3.14 Policy-at-the-time replay

Historical replay must use the policy that existed at the time of the decision.

Every replayed decision should cite:

```text
policy_version
content_hash
engine_version
calculation_version
normalization_version
```

The `content_hash` is the audit anchor for what the engine said on the available inputs. A later policy cannot be substituted silently.

### 3.15 Sold positions

Sold positions are essential for evaluating EXIT, TRIM, HARVEST, and survivorship bias.

A future addendum implementation may require sold-position records with:

- instrument
- quantity sold
- sell date
- sell price
- lot matching / FIFO identity when available
- realized gain/loss classification

Absence of sold-position data prevents a clean performance backtest and should trigger mechanics-only mode or an explicit bias warning.

### 3.16 Corporate actions, if in scope

Corporate actions may affect historical comparability.

If in scope, a future backtest must define treatment for:

- splits
- bonuses
- dividends
- mergers / demergers
- symbol changes
- delistings

If corporate-action data is unavailable, the backtest must either exclude affected cases, mark them low-quality, or run mechanics-only.

### 3.17 Outcome data quality

Backtest output must include outcome-data quality, distinct from decision-input quality.

Suggested states:

| State | Meaning |
|---|---|
| complete | required outcome data exists and reconciles |
| partial | some outcome data missing but evaluation still informative |
| biased | universe or sold-position gaps materially affect result |
| mechanics_only | outcome data insufficient for performance claims |
| invalid | data conflicts prevent evaluation |

Outcome quality must be shown with the result and must not be hidden behind a single performance number.

### 3.18 Mechanics-only mode

Mechanics-only mode is required when historical outcome data is insufficient.

In mechanics-only mode, the backtest may verify:

- parser / normalization replay
- G0–G4 gate execution
- score calculation
- confidence calculation
- trim-plan generation
- reason-tree and provenance generation
- content-hash determinism

Mechanics-only mode must not claim investment performance, win rate, alpha, tax benefit, or benchmark outperformance.

---

## 4. Non-optimization covenant

Backtest findings may produce one of these governance outputs:

1. no action
2. data-quality improvement request
3. new authority question
4. new named Change Request proposal
5. rejection of a proposed change

Backtest findings may not directly produce:

- changed weights
- changed thresholds
- changed gate precedence
- changed golden expected results
- changed fixture outcomes
- changed policy defaults
- changed tax or trim methodology

Any such change requires a separate authority gate.

---

## 5. Protected regression anchors

The following remain permanent anchors:

```text
SALASAR → TRIM / G2 / mode S
ASHOKA  → EXIT / G1
LT      → HOLD / G3
AGI     → WATCH / INSUFFICIENT
Tax goldens remain unchanged
```

Backtest outcomes must not silently retune or reinterpret these anchors.

---

## 6. Future implementation prerequisites

A future runtime backtest CR, if ever authorized, must separately define:

- exact input files
- historical snapshot storage format
- sold-position format
- benchmark source and licensing
- corporate-action source
- replay engine boundaries
- output schema
- test fixtures
- audit requirements
- UAT gate

None of those are implemented by this addendum.

---

## 7. Summary

This addendum opens the methodology framework for evaluating Capital Steward Engine decisions over history. It deliberately stops short of implementation.

The binding rule is:

```text
BACKTEST = EVALUATION FRAMEWORK
BACKTEST ≠ METHODOLOGY OPTIMIZATION LOOP
```

Historical results are evidence for governance, not automatic authority to change the engine.
