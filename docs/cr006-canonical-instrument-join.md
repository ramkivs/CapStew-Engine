# CR-006 — G0 Portfolio↔Ledger Canonical Instrument Join

**Status:** GOVERNANCE RECORD · **APPROVED / AUTHORIZED FOR IMPLEMENTATION** (implementation not yet started)

**Baseline (at recording):** branch `arena/01a033db-capstew-engine` @ `ebfbde2d65f6f351e58373f78cdbb1f21672e5a7` (`origin/main` @ `ffdf9cba2c7f5e479765c57f314f2cb7823d8138`)

> **CR-020 annotation (2026-08-27, additive):** the recording-time branch tip above has since advanced — CR-006 join commit `ac9cd09`, then CR-006 remediation commit `e473417b75d0a60a9be7376803d4d77a867e5858` (G0 NO-DECISION hysteresis boundary fix: `app/decision.py` + `tests/test_cr006.py` T/U/V). `origin/main` remains `ffdf9cb`. The line above is preserved verbatim for audit.

**Authorization:** CR-006 was separately authorized by the authority **after** the CR-006 read-only inspection. The authorization is:

- not inferred from existing code;
- not inferred from CR-019;
- not inferred from CR-005;
- not inferred from implementation;
- not inferred from tests.

CR-019 establishes the existing `canonical_name_key()` facility, but does **not** by itself authorize its use as the G0 Portfolio↔Ledger join key. CR-005 explicitly preserved the existing reconciliation contract and did **not** authorize this change. This document is the required durable authority record, created **before any engine code is changed**.

---

## 1. Objective

Use the existing deterministic `canonical_name_key()` (`app/symbols.py:50`) as the Portfolio (XIRR) ↔ Raw Trade Ledger identity join key for G0 reconciliation, while preserving raw source names and failing closed on canonical-key collisions.

## 2. Recorded authority decisions (A–L)

**A. Canonical join key — APPROVED.** Portfolio↔Ledger G0 identity matching may use the existing deterministic `canonical_name_key()`. Do NOT create a new normalization function. Do NOT alter the existing canonicalization algorithm as part of CR-006.

**B. Raw name preservation.** Portfolio and Ledger raw `Instrument` strings must remain unchanged for display, provenance, diagnostics, audit evidence, and serialized source information. Canonicalization is lookup identity only.

**C. Exact match.** Existing exact raw-name matches remain valid.

**D. Canonical-equivalent match.** After exact matches are consumed, canonical-equivalent names may be linked when there is exactly **1 distinct Portfolio name AND 1 distinct Ledger name** for that canonical key.

**E. Collision safety — MANDATORY (fail closed).** If more than one distinct raw Portfolio name maps to the same canonical key, OR more than one distinct raw Ledger name maps to the same canonical key: **BLOCK / FAIL CLOSED.** No arbitrary first match. No fuzzy selection. No scoring. No ticker guessing. No heuristic selection. No silent data repair. A collision must produce an explicit **blocking** reconciliation issue. An additive issue code such as `CANONICAL_NAME_COLLISION` is authorized, provided its semantics are exactly collision/blocking diagnostics and not a methodology change.

**F. Missing ledger.** If there is no canonical-equivalent Ledger counterpart: existing `NO_LOTS` behavior remains.

**G. Numeric reconciliation.** Existing G0 numeric checks remain completely unchanged. Existing tolerance remains **₹0.01**. No tolerance increase or relaxation is authorized.

**H. Ledger-only rows.** Existing `LEDGER_ONLY_LOTS` behavior remains unchanged except that its counterpart determination may use the approved canonical link.

**I. No fuzzy matching.** Explicitly prohibited.

**J. No methodology change.** CR-006 does NOT authorize changes to: scoring; weights; thresholds; gates; policy; tax methodology; trim; hysteresis; confidence; watchlist; D-14; G2; screener methodology; decision methodology.

**K. Sold/FIFO.** `sold.csv` / FIFO matching is explicitly **OUT OF SCOPE**. Do not change the sold/FIFO join in CR-006.

**L. Payload / schema.** No payload-version or schema-version change is authorized or expected.

## 3. Recorded implementation surface (inspection result, pre-implementation)

WOULD CHANGE:

- `app/symbols.py` — additive link-index builder (the existing `canonical_name_key()` itself is NOT to be changed unless a separate authority decision explicitly authorizes it);
- `app/reconcile.py` — G0 join consumption;
- `app/lot_engine.py` — position/lot roll-up consumption;
- `app/decision.py` — decision tax/trim lot lookup consumption;
- `app/pipeline.py` — build-once wiring;
- `tests/test_cr006.py` — new additive acceptance tests.

Recorded finding: `reconcile.py` alone is **insufficient**, because the same Portfolio↔Ledger identity relationship is consumed by three sites — reconciliation (`reconcile.py:26-35`), position/lot roll-up (`lot_engine.py:66-93`), and decision tax/trim lot lookup (`decision.py:284-299`). Sold/FIFO (`pipeline.py:186-205`, `tax.py:235`) is explicitly excluded.

## 4. Recorded acceptance test battery (A–O)

A. exact raw-name match · B. whitespace-only canonical-equivalent match · C. case canonicalization where already supported · D. punctuation canonicalization where already supported · E. A1 canonical-equivalent case proceeds through existing numeric G0 · F. A2 missing canonical Ledger counterpart remains `NO_LOTS` · G. A3 numeric mismatch remains blocking · H. Portfolio-side canonical collision blocks · I. Ledger-side canonical collision blocks · J. both-side canonical duplication blocks · K. true ledger-only orphan remains warning · L. deterministic repeated execution · M. existing ₹0.01 tolerance unchanged · N. CR-005 screener partial-data behavior unchanged · O. existing goldens unchanged.

Any canonicalization behavior not already supported by the existing `canonical_name_key()` is NOT to be invented.

## 5. Recorded real-data acceptance baseline (evidence-only, not a guarantee)

Prior read-only classification of the actual three exports (A1+A2 = all 67 NO-DECISION):

| Metric | Value |
|---|---|
| Total holdings | 163 |
| NO-DECISION | 67 |
| A1 canonical-name mismatch | 62 |
| A2 missing ledger match | 5 |
| A3 numeric mismatch | 0 |
| A4 other blocker | 0 |

This is an acceptance **baseline**, NOT a guarantee. After implementation, acceptance must re-run the read-only classifier against the same three real exports. Expected **direction**: A1 → 0; A2 → remain blocked; A3 → 0; no new blocker class. "62 decisions restored" is NOT recorded as a guaranteed outcome; acceptance must be based on actual post-implementation evidence.

> **CR-020 annotation (2026-08-27, additive — acceptance outcome):** the authority-executed post-implementation acceptance DID re-run against the same three real exports and PASSED at `e473417` (CR-006 remediation tree). Authority-reported record: HTTP 200; engine_version 0.3.1-phase3; HOLD 40 / WATCH 111 / NO-DECISION 5 / EXIT 7; G0_NO-DECISION = 5 = total NO-DECISION; no non-G0 NO-DECISION; no G4→NO-DECISION paths; the five NO-DECISION names were genuine NO_LOTS (ECOS Mobility, GMR Power Urban Infra, Grauer Weil, Matrimony, JKBANK); AGI Greenpac proceeded G4 → HOLD (composite 14.8) with `previous_run.decision = NO-DECISION` preserved audit-only — the remediated invariant. These figures are the authority-reported acceptance record (evidence-only), not a golden for other inputs.

## 6. Governance fences (verified at recording)

Frozen registry (`docs/v1.1-authority-decisions-v1.md`, blob `deb6189292d62e76ef98ef178e2802998d9275b4`), methodology freeze, backtest addendum, policy (`policy/policy.yaml`), schema, fixtures, goldens — all byte-identical to `origin/main` at recording and MUST remain so. No D-14/watchlist/G2 methodology is implicated by this record. Tags `v1.0.0` / `v1.1.0` unmoved.

## 7. Next step

Implementation may proceed **only** under a separate CR-006 implementation prompt. This record grants the authorization; it does not exercise it.
