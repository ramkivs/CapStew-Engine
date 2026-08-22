# Capital Steward Engine — Methodology Freeze v1.0
*(Spec v1.1 addendum — supersedes conflicting sections of Spec v1.0)*

> **Status: CLOSED — signed off 2026-08-22.** All P0 items frozen; authority decisions recorded in §15. Phase 1 (data foundation) is built and contract-tested against these frozen rules. The scoring engine (gates/composite/trim) remains uncoded until Phase 2, which reads these rules verbatim.
> **Supersedes:** Spec v1.0 §4.1 (gate wording), §4.2 (MAX trim), §4.3 (decision labels), §3/§4 (decision names); Architecture & UI Guidelines v1.0 (ADR-1 slider contradiction, §12.3 badge table, §11.7 enum).
> **Companions:** `architecture-and-ui-guidelines.md` (updated to v1.1) · `profit-booking-engine-ui-prototype.html` (updated) · `profit-booking-engine-analysis.md` (findings, unchanged — historical).
> **Date:** 2026-08-22

---

## 0. Name & terminology [FROZEN]

**Product name:** **Capital Steward Engine** (UI label: "Capital Steward"; decision layer: "Capital Steward Decision Engine").

**Why:** the system stewards capital and positions — HOLD / WATCH / TRIM / HARVEST / EXIT, concentration management, tax sequencing, behavioural averaging detection, opportunity cost. "Profit booking" is one of its actions, not its identity.

Recorded alternatives (rejected, kept for audit): Capital Harvest Engine (over-emphasises selling), Position Steward Engine (precise but less elegant).

**Rename map (old → new):**

| Spec v1.0 label | Frozen label |
|---|---|
| HOLD | **HOLD** |
| HOLD-WATCH | **WATCH** |
| PARTIAL PROFIT BOOK | **TRIM** |
| FULL PROFIT BOOK / EXIT (Target) | **HARVEST** |
| EXIT (Stop-Loss / Thesis Break) | **EXIT** |
| ACCUMULATE (tag) | **ACCUMULATE** *(tag, unchanged)* |

---

## 1. Decision semantics [FROZEN]

| Decision | Meaning | Primary trigger | Typical P&L | Tax note |
|---|---|---|---|---|
| **HOLD** | Continue; no action | Thesis intact, sized correctly, valuation in line | any | — |
| **WATCH** | Continue; evidence deteriorating | Composite 31–55; shorten review cadence | any | — |
| **TRIM** | Reduce to a computed target (partial) | Sizing breach **or** valuation stretch (modes S/V, §5) | usually gain | FIFO-lot tax plan attached |
| **HARVEST** | Full exit — target/value reached | Thesis largely played out / valuation stretched (composite ≥76) | gain | plan against ₹1.25L headroom |
| **EXIT** | Full exit — thesis/risk broken | Governance, quality floor, stop-loss (G1) | any, often loss | losses harvestable (S.74) |
| **ACCUMULATE** | Tag on a HOLD only — under-allocated vs conviction | §1.1 rule | — | never a competing decision |

**HARVEST vs EXIT is now unambiguous:** HARVEST = *the merits say leave* (target reached); EXIT = *the risk says leave* (thesis broken). The UI must never render HARVEST as "EXIT (Target)" — that conflation is what created the ambiguity.

### 1.1 ACCUMULATE trigger rule [FROZEN]
```
ACCUMULATE tag iff ALL of:
  decision == HOLD
  AND conviction_score ≥ high_threshold            (from Quality/Growth engines)
  AND allocation_pct < target_band_low
  AND valuation not stretched (PE/PB premium ≤ 0, or MOS > 0)
  AND no Stage-1 gate fired
  AND no averaging-into-losses flag on this name   (never add to a flagged loser)
```

---

## 2. Gate precedence [FROZEN] — G0 → G4

Resolves the "which gate wins?" ambiguity. Precedence is strict and total: **G0 > G1 > G2 > G3 > G4**. Every gate that fires is *recorded* in `stage1.gates_fired` even when a higher gate wins (explainability).

| Gate | Condition | Decision | Beats |
|---|---|---|---|
| **G0 — Data integrity** | Blocking parse/reconcile error | `NO-DECISION` (status, not a recommendation) | everything |
| **G1 — Thesis / Governance break** | quality < floor (40) **or** quality drop ≥ 20 vs entry snapshot **or** pledge > 10% / +5pp QoQ **or** governance flag | **EXIT** | G2, G3, G4 |
| **G2 — Absolute allocation / risk breach** | alloc > absolute cap (10%) **or** alloc > 1.5× target_top | **TRIM** (mode S, to cap) | G3, G4 |
| **G3 — Tax defer** | days-to-LTCG (oldest unsold lot) < 30 **and** valuation_subscore < 85 **and** no G1/G2 | **HOLD** (defer) | G4 |
| **G4 — Stage 2 composite** | coverage-eligible (§3) | HOLD / WATCH / TRIM / HARVEST via bands + hysteresis | — |

**Two explicit rules the review demanded:**

1. **Risk caps are never tax-deferred.** If G2 (allocation breach) and G3 (near LTCG) fire together, **G2 wins** — trim to cap. Tax optimisation must not override a portfolio risk policy.
2. **Governance/thesis break is never a partial.** G1 → EXIT (full), not TRIM — a broken thesis is not a trimming problem.

**G3 valuation-extreme override** (carried from analysis §2.1): the defer only applies when the position is *not* stretched. If `valuation_subscore ≥ 85`, G3 does **not** fire and the position proceeds to G4 normally — deferring a +94% re-rating microcap 30 days for 7.5pp of tax is an expected-value loss. The suppressed defer is recorded as `stage1.tax_defer_suppressed: true`.

### 2.1 Portfolio action-queue priority [FROZEN — new policy decision, needs sign-off]
The action queue is **not** a plain composite sort — a governance EXIT can fire at composite 20 and outrank an 88 HARVEST.

```
Priority:  EXIT > TRIM-S > TRIM-V > HARVEST
Within a tier: composite score descending.
Reason class attached to every queue entry:  RISK (EXIT) · SIZING (TRIM-S) · VALUATION (TRIM-V / HARVEST)
```

> **Explicit decision, not silently chosen:** this ordering is proposed as the default and must be confirmed or reordered at sign-off (checklist item 11). The alternative — a plain composite sort across all action types — is rejected because it lets a high-scoring valuation harvest outrank a low-scoring governance exit.

---

## 3. Missing-data eligibility [FROZEN]

Renormalisation alone must not manufacture confidence. Add a formal eligibility floor.

```
coverage = Σ(w_k for available categories) / Σ(all weights)      # over the 6 categories
```

| Tier | Rule |
|---|---|
| coverage ≥ 80% | Normal Stage 2 scoring |
| 60% ≤ coverage < 80% | **Advisory-only** — decision emitted, `confidence` capped at 55, banner `PARTIAL EVIDENCE` |
| coverage < 60% | Decision forced to **WATCH** (insufficient evidence) — no TRIM/HARVEST |

**Critical-category rules (independent of coverage):**

```
TRIM / HARVEST  require  valuation_stretch OR quality_drift present   (else cap at WATCH)
HARVEST         requires valuation_stretch present                    (harvest = valuation target reached)
EXIT (G1)       requires quality_drift OR governance present          (thesis break must be evidenced)
position_sizing always present for open positions (portfolio file guarantees it)
```

Note: `EXIT` is gate-driven, not composite-driven, so coverage tiers apply to Stage 2 only; a governance breach exits regardless of how little else is known.

---

## 4. Confidence equation [FROZEN]

**Score ≠ Confidence** is a first-class concept: the decision label comes from the score; confidence qualifies the *evidence quality*, not the direction. "TRIM, score 72, confidence 54%" is a valid and useful output.

```
Confidence = round( clamp( 100 − P_missing − P_divergence − P_boundary − P_proxy − P_staleness , 20 , 95 ) )

P_missing    = 25 × (1 − coverage)                    # 0..25
P_divergence = min(15, 0.6 × stdev(available subscores) + E)
               E = 0  if ≥2 engines agree directionally
               E = 5  if single engine only
               E = 8  if engines disagree directionally
P_boundary   = max(0, 5 − d)                          # d = distance (pts) to nearest band edge; applies only when d ≤ 5
P_proxy      = 5 × (# proxy categories in use), cap 10 # valuation/quality running on peer-relative or level-only proxies
P_staleness  = 3 × (# stale inputs), cap 6            # valuation/prices stale >3d; ledger stale >7d
```

- Rounded to integer **inside the canonical equation** (`round()` is part of the definition, not a display choice). Full breakdown emitted in `confidence_breakdown` (never a bare number).
- **Exact identity (test it as written, not as prose):** `confidence == round(clamp(100 − Σ(penalties), 20, 95))`. The breakdown lists the *penalties*; confidence is **not** a sum of breakdown parts — do not code it as one.
- All constants are **policy-tunable**; the **structure** (five additive penalties, clamp 20–95, round to integer, eligibility cap 55) is frozen.

---

## 5. Trim sizing — constrained optimisation [FROZEN]

**Replaces Spec v1.0 §4.2's `MAX(...)` heuristic**, which over-trims by conflation. Trim has two distinct modes with different objectives.

**Setup:** lots `L₁..Lₙ` FIFO-ascending; a sell plan `s = (k, f)` sells all of lots `1..k` plus fraction `f ∈ [0,1)` of lot `k+1`.
```
sell_qty(s)   = Σ_{i≤k} qty_i + f·qty_{k+1}
sell_value(s) = Σ_{i≤k} qty_i·ltp + f·qty_{k+1}·ltp
```

**Hard constraints (any violation ⇒ infeasible):**
```
C1  alloc_after(s) = (cur_value − sell_value(s)) / V  ≤  max_band_alloc
C2  qty_held − sell_qty(s) ≥ min_position_qty                        (dust floor)
C3  sell_qty(s) ≤ max_executable_qty   where:
      ADV known:     max_executable_qty = max_pct_adv × 20d_ADV        (max_pct_adv = 10%)
      ADV unknown:   max_executable_qty = max_pct_position × qty_held  (max_pct_position = 25%)
C4  FIFO prefix (structural — sell oldest-first, matching Indian tax matching)
```

**Objective (lexicographic over feasible s):**

| Mode | Trigger | Objective |
|---|---|---|
| **TRIM-S (sizing)** | G2 breach, or rebalance band breach | 1. minimise `|alloc_after − target_top|` · 2. minimise `tax_cost` · 3. minimise `sell_value` · 4. minimise `txn_cost` |
| **TRIM-V (valuation)** | composite 56–75 with allocation in band (trim from strength) | sell `ρ ∈ [0.25, 0.50]` of qty (policy) chosen to 1. minimise `tax_cost` · 2. minimise `txn_cost` |

```
tax_cost(s) = 0.125 × max(0, LTCG(s) − remaining_headroom) + 0.20 × STCG(s)
```

- The old "book qty such that realised gain ≈ remaining headroom" is now **emergent** from `tax_cost`: LTCG up to the ₹1.25L headroom is free, so the objective prefers it automatically — no separate MAX term needed.
- LTCG-preference is also emergent from the FIFO-prefix constraint (oldest lots first), not a separate objective.
- Output: `fifo_lots_to_sell = [1..k] + (k+1, fraction f)`, `suggested_qty`, `suggested_value`, `tax_breakdown`, `mode` (`S`/`V`), `est_transaction_cost`.
- `trim.suggested_qty = null` when not applicable — the UI renders `—`, never 0.

---

## 6. Hysteresis [FROZEN]

Band edges must not create decision churn (75↔76 flapping).

```
HOLD   ↔ WATCH:   enter WATCH at ≥31,   revert to HOLD at <28
WATCH  ↔ TRIM:    enter TRIM at ≥56,    revert to WATCH at <52
TRIM   ↔ HARVEST: enter HARVEST at ≥76, revert to TRIM at <72

Persistence: composite must sit in the new band for N = 2 consecutive runs
(distinct as_of dates) before the label changes.
Emergency override: G0/G1/G2 bypass hysteresis immediately.
```
Thresholds are policy; the **enter/exit asymmetry + persistence mechanism** is part of the engine contract.

---

## 7. Browser-computation rule [FROZEN] — resolves the ADR contradiction

Architecture v1.0 said "browser never computes a decision" while §12.5 asked the UI to "recompute every decision client-side during weight dragging." That contradiction is resolved as follows:

- **The browser NEVER computes a decision, a composite score, or any decision-relevant number. Ever.**
- **v1 behaviour (chosen):** weight/parameter drag → debounced `POST /api/v1/what-if` (50 ms) → server returns the authoritative payload → UI swaps it in. **No client-side recompute exists in v1.**
- The 50 ms local recompute is not worth compromising the architectural rule. The 60 fps target is met by *optimistic UI* (a "recalculating…" shimmer on the affected cells), not by client-side decision math.
- Permitted client-side operations: formatting, sorting, filtering, colouring, rendering. **Nothing that produces a decision or score.**

---

## 8. Determinism guarantee [FROZEN]

**Named principle: the Capital Steward Determinism Guarantee.**

```
∀ (inputs, policy, engine_version):
  pipeline produces byte-identical decisions content
  (identical content_hash; run_id / timestamps recorded separately, excluded from the hash)
```

Mechanics:
- **Canonical sort:** lots by `(trade_date ASC, buy_price ASC, stable lot_id ASC)`.
- **Fixed precision:** subscores rounded to 2 decimals before blending; composite to 1 decimal; confidence integer. No float drift in the decision path (use `decimal` or integer cents).
- **No randomness** in the pipeline; no wall-clock reads inside scoring (time enters only via `as_of`).
- **No dict-iteration-order dependence** — iterate sorted keys where order matters.

**Test:** fixture replay → assert `content_hash` equality across runs, processes, and restarts. Determinism ≠ immutability: replay writes a new `run_id` but an identical `content_hash`.

---

## 9. Output schema additions [FROZEN]

The §4.3 output is extended (schema in Architecture §11.7). Two fields are promoted to first-class:

### 9.1 `reason_tree` — machine-readable explanation
Textual drivers stay for human reading; the tree makes the engine explainable without reverse-engineering prose.
```json
"reason_tree": {
  "stage1": {
    "g0_data_integrity": "ok",
    "g1_thesis_break": false,
    "g2_allocation": { "fired": true, "alloc_pct": 9.8, "cap_pct": 3.0 },
    "g3_tax_defer": { "fired": false, "suppressed": true, "why": "valuation_subscore 97 ≥ 85" }
  },
  "stage2": {
    "position_sizing": { "score": 92, "contributors": ["alloc 9.8% vs band 0–3%"] },
    "valuation_stretch": { "score": 97, "contributors": ["PE 55× vs median 18×", "87% re-rating"] }
  },
  "decision_path": "G2 → TRIM (mode S)",
  "previous_run": { "decision": "TRIM", "composite_score": 71, "as_of": "2026-08-15" }
}
```

### 9.2 `why_now` + `previous_run`
```json
"why_now": {
  "primary_trigger": "Allocation crossed 8% cap on 2026-08-20",
  "contributors": [
    { "label": "Allocation breach", "delta": "+18" },
    { "label": "Valuation stretch", "delta": "+14" },
    { "label": "Tax timing", "delta": "−8" },
    { "label": "Quality drift", "delta": "+5" }
  ]
}
```

---

## 10. Policy validation [FROZEN]

Before `PUT /api/v1/policy` commits, the server validates:

```
weights sum > 0            ·   each weight within allowed range
bands non-overlapping      ·   bands contiguous (cover 0–100)
min_position < target      ·   target < max_cap
tax_defer_window ≥ 0       ·   hysteresis_band < band_width
```
Client shows **"Policy is internally consistent"** (or the specific violation) before enabling **Commit**. Dragging alone never persists.

**Policy-change impact preview** (commits the what-if idea further) — before commit, show:
```
Current policy → Proposed policy
  HARVEST → TRIM       2
  TRIM    → HOLD       3
  HOLD    → WATCH      4
  EXIT    → unchanged  1
  Action queue:        7 → 5 candidates
  Highest impact:      SALASAR  TRIM → HARVEST · KALYAN  TRIM → HOLD
```

---

## 11. Testing — invariants & boundaries [FROZEN for CI]

In addition to the existing unit/contract/E2E plan:

**Invariants (property tests):**
```
FIFO selected lots always oldest-first
sold_qty ≤ held_qty
remaining_qty ≥ min_position_qty
alloc_after ≤ policy max_cap
decision unchanged by UI rendering (payload → screen is a pure projection)
same inputs + same policy = same decision
same run replay = same content_hash
confidence == round(clamp(100 − Σ penalties, 20, 95))   (breakdown lists the penalties, not confidence parts)
```

**Boundary tests (exact-value):**
```
holding exactly 365 days · 364 · 366
composite exactly 30 · 55 · 75 · 76
allocation exactly at cap · one rupee above cap
pledge exactly at threshold
one category missing · all categories missing
coverage exactly 60% · 80%
```

**Canonical gate-precedence fixtures (the trilogy):**
```
Golden Case A — Risk-cap precedence:    SALASAR  pledge 4.0% (<10), alloc 9.8% (>3 cap), composite 87 → G2 wins → TRIM-S
Golden Case B — Thesis-break precedence: ASHOKA  pledge 12.4% (>10), composite 48 → G1 wins → EXIT
Golden Case C — Tax defer:              LT      22d to LTCG, valuation subscore 40 (<85), composite 38 (WATCH) → G3 wins → HOLD
```
These three fixtures are fixed in the mock payload and reused in every fixture/contract test — they must never silently change, because they pin the G1/G2/G3 precedence semantics.

**Test IDs (assigned for Phase 1/2):** `GOLDEN-G2-TRIM-S-SALASAR`, `GOLDEN-G1-EXIT-ASHOKA`, `GOLDEN-G3-HOLD-LT`.

**Fixture scope split (Phase 1 vs 2):** Phase 1 contract fixtures assert the **data facts** the gates read (SALASAR pledge 4.0 & micro-cap bucket; ASHOKA pledge 12.4 + 16 declining all-red lots; LT oldest lot = 22 days-to-LTCG). The **gate decisions** (TRIM-S / EXIT / HOLD) are asserted by Phase 2 gate tests against synthetic gate inputs (alloc 9.8%, composite 87/48/38) — the allocation % and composite values are portfolio/scoring outputs, not ledger facts, so they are not pinned in the Phase 1 CSVs.

## 12. Roadmap (post-freeze)

**P1 — strongly recommended (next sprints):**
1. Decision-change history + run diff (`GET /runs`, `GET /runs/{id}/diff`)
2. "Why now?" + "Why no action" explanation
3. Policy-impact preview (§10)
4. Provenance fields on every input (`source, source_version, source_as_of, ingested_at, normalization_version`) and derived metric (`calculation_version, policy_version`)
5. Policy validation (§10)
6. Invariant/property tests (§11)

**P2 — deferred (data gaps unchanged):**
cross-engine divergence dashboard · post-tax XIRR · own-historical valuation median · relative strength vs index · watchlist opportunity engine · live read-only data.

---

## 13. Change log vs prior artifacts

| # | P0 item | Prior state | Frozen replacement |
|---|---|---|---|
| 1 | Gate precedence | three gates, no precedence | G0–G4 strict ordering, risk-cap-not-tax-deferred, governance-never-partial |
| 2 | Confidence | field existed, undefined | §4 equation + caps + breakdown |
| 3 | Missing-data | "renormalise + penalise" | eligibility tiers + critical-category rules |
| 4 | Trim sizing | `MAX(...)` | constrained optimisation, modes S/V |
| 5 | Browser computation | ADR contradicted §12.5 | §7 — no client recompute, server `/what-if` |
| 6 | Hysteresis | mentioned, undefined | enter/exit asymmetry + N=2 persistence |
| 7 | Decision semantics | HOLD-WATCH/PARTIAL/FULL blurring | HOLD/WATCH/TRIM/HARVEST/EXIT |
| 8 | Determinism | implied | §8 definition + test |

---

## 14. Policy parameter defaults — D-01…D-15 [PROPOSED — awaiting authority]

*These defaults were drafted in the analysis doc §7. They are restated here so sign-off item 9 can be made against **this artifact alone**, not a cross-reference. The values are **policy, not methodology**: the frozen structure above holds regardless of the numbers chosen here. Decision labels use the frozen vocabulary (WATCH/TRIM/HARVEST).*

| ID | Parameter | Proposed default |
|---|---|---|
| D-01 | Bucket definitions (by market cap) | Large ≥ ₹20k Cr · Mid ₹5k–20k · Small ₹500–5k · Micro < ₹500 Cr |
| D-02 | Target allocation band | Large 4–8% · Mid 2–5% · Small/Micro 1–3% |
| D-03 | Absolute max single-stock cap (G2) | 10% (any bucket) |
| D-04 | Rebalance trigger | position > 1.5× target mid-point → TRIM-S to band top |
| D-05 | Quality floor / thesis break (G1) | composite quality < 40, or drop ≥ 20 pts vs entry snapshot |
| D-06 | Promoter pledge spike (G1) | pledged % > 10%, or ≥ +5pp in one quarter |
| D-07 | LTCG defer window (G3) | 30 days, with valuation-extreme override (valuation_subscore ≥ 85 suppresses defer) |
| D-08 | Composite band boundaries | 0–30 HOLD · 31–55 WATCH · 56–75 TRIM · 76–100 HARVEST |
| D-09 | Category weights (default profile) | sizing 25 / valuation 25 / quality 20 / tax 15 / opp-cost 10 / technical 5 |
| D-10 | Re-rating share thresholds | > 65% strong signal · > 80% critical (sliding, not cliff) |
| D-11 | Min meaningful position | no trim leaves < 0.5% allocation or < ₹5,000 value |
| D-12 | Participation cap (C3) | ADV known: 10% × 20d ADV · ADV unknown: 25% × qty |
| D-13 | Transaction-cost assumption | 0.35% round trip liquid · 1.0% microcap |
| D-14 | Default opportunity-cost hurdle | Nifty 11% pre-tax long-term · liquid fund 6.4% ("wait") |
| D-15 | Review cadence | HOLD (conf ≥ 70) +90d · HOLD (conf < 70) +30d · TRIM/HARVEST +7d verify · Stage-1 fire +1d |

---

## 15. Sign-off checklist

- [x] 0 — Name: **Capital Steward Engine** adopted
- [x] 1 — Decision semantics (HOLD/WATCH/TRIM/HARVEST/EXIT + ACCUMULATE)
- [x] 2 — Gate precedence G0–G4 (incl. risk-cap-not-tax-deferred)
- [x] 3 — Missing-data eligibility tiers + critical-category rules
- [x] 4 — Confidence equation + caps
- [x] 5 — Trim constrained optimisation (modes S/V)
- [x] 6 — Hysteresis (enter/exit + N=2)
- [x] 7 — Browser-computation rule (no client recompute)
- [x] 8 — Determinism guarantee + replay test
- [x] 9 — Policy thresholds D-01…D-15 (§14 table) **ACCEPTED as proposed** — D-14 (opportunity-cost hurdles) accepted *provisionally*, subject to periodic review (market-regime-sensitive)
- [x] 10 — Cross-artifact consistency: Freeze ↔ Architecture ↔ Prototype — no executable rule contradicts the Freeze
- [x] 11 — Action-queue priority (§2.1): **ACCEPTED** EXIT > TRIM-S > TRIM-V > HARVEST

## 16. Sign-off record

| Date | Authority | Items | Notes |
|---|---|---|---|
| 2026-08-22 | Ramki (via review) | 0–11 | All accepted; D-14 provisional; gate **CLOSED** |

## 17. Phase 1 shipped (2026-08-22)

Data foundation built and contract-tested in `capital-steward/` — parsers → normalization →
reconciliation (G0) → per-lot FIFO engine → canonical payload with determinism hash.
34 tests green; golden trilogy asserted at data-fact level; live FastAPI (health / reconcile /
ingest / lots). No decision logic, no browser computation, no live data (ADR-3/ADR-5).
Phase 2 = gates → scoring → confidence → writer, reading this freeze verbatim.
