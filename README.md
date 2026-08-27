# Capital Steward Engine — Phase 3 (tax + history + provenance)

Portfolio discipline · valuation · tax · risk.

- **Phase 1 (done):** data foundation — parsers → normalization → reconciliation (G0) → per-lot FIFO → canonical payload, with the determinism hash. No decision logic.
- **Phase 2 (done):** the decision engine — G0–G4 gates → Stage-2 scorer → confidence → hysteresis → TRIM-S/TRIM-V → `reason_tree`/`why_now` → DecisionPayload.
- **Phase 2 audit: PASSED — no known open audit findings** (table below; 111 → 126 backend tests — build-point count, superseded by the epoch table below).
- **Phase 3 (this build):** tax-year subsystem (S.74 set-off, exemption, carry-forward, FIFO sell matching, tax-aware sequencing) + run history/`diff` + provenance completion. **126 backend tests green at the Phase-3 build point; frontend TypeScript build clean — counts since superseded; see the epoch table below.**

## Status

| Gate | Status |
|---|---|
| Methodology freeze | ✅ CLOSED |
| Phase 1 (data foundation) | ✅ COMPLETE |
| Phase 2 (decision engine) | ✅ COMPLETE |
| Phase 2 implementation audit A–J | ✅ PASSED |
| Phase 3 (tax · history · provenance) | ✅ COMPLETE |
| React/UI integration | ✅ COMPLETE (gates UI-1…UI-6) |
| UI Product Acceptance (UAT-01…06) | ✅ PASSED |
| Release gate (R-01…R-10) | ✅ PASSED — tagged `v1.0.0` (`RELEASE-v1.md` + `MANIFEST.sha256`) |

## Epochs, test counts & release records (CR-020, 2026-08-27)

| Epoch | Ref | Status | Backend tests |
|---|---|---|---|
| v1.0.0 (**CERTIFIED** — the only certified epoch) | annotated tag → commit `86677380` | R-01…R-10 10/10 PASS; `RELEASE-v1.md` + `MANIFEST.sha256` (frozen) | 126 (at certification) |
| v1.1.0 | lightweight tag `638890bb` + hosted GitHub Release | **RELEASE-DOCUMENTED MILESTONE — not a certified release** (E2E-013-R C1 / E2E-017-PD R1-B); no in-repo release record exists for this epoch | 176 (hosted-Release claim; not re-audited in-repo) |
| main-current | `ffdf9cba2c7f5e479765c57f314f2cb7823d8138` | TESTED (CR-005/CR-019/CR-008/CR-012A/CR-012B merged) | 450 collected |
| session branch | `arena/01a033db-capstew-engine` @ `e473417b75d0a60a9be7376803d4d77a867e5858` | TESTED; CR-006 REAL-DATA VERIFIED (authority-executed acceptance) | 497 collected |

- `MANIFEST.sha256` pins the **v1.0.0 tree only** and `RELEASE-v1.md` records the **v1.0.0 release only**. Both are frozen v1.0.0 records, unchanged by design — they are not current-tree manifests.
- Version constants (`ENGINE_VERSION`, `NORMALIZATION_VERSION`, `CALCULATION_VERSION`, `policy_version`) are currently static across epochs, so payload provenance discriminates material builds only via git SHA + test ledger until the **VP-1** rule (`docs/version-provenance-rule-vp1.md`) applies to future engine-mutating CRs.

## Pipeline

```
CSV parsers → normalize → reconcile (G0) → per-lot FIFO → FoundationPayload
                                                              ↓
                 G0 → G1 → G2 → G3 → G4 (composite, eligibility-capped, hysteresis-gated)
                                                              ↓
                    confidence → trim (S/V) → reason_tree + why_now → DecisionPayload
```

The **browser never computes a decision** (ADR-1a); the API is the authority.

## Layout

```
app/
  config.py      engine version, SYMBOL_MAP, staleness thresholds, STORE_PATH
  policy.py      policy loading + validation (policy is data, not code)
  ingest.py      CSV parsers
  normalize.py   date disambiguation + symbol mapping
  reconcile.py   G0 cost-basis reconciliation
  lot_engine.py  per-lot FIFO engine + position roll-up (+ fundamentals join)
  determinism.py canonical JSON + content_hash
  pipeline.py    run_foundation() + run_engine() + decide_on_foundation()
  store.py       append-only SQLite run store (ADR-4) — hysteresis source of truth + run diff
  tax.py         tax-year subsystem: FIFO sell matching, S.74 set-off, exemption, carry-forward, sequencing
  gates.py       Stage 1 gates G0–G4 (strict precedence)
  scoring.py     sub-scores, eligibility tiers, bands, four-state data quality
  confidence.py  round(clamp(100 − Σ penalties, 20, 95))
  hysteresis.py  asymmetric transitions + N=2 persistence + seed()
  trim.py        constrained trim sizing (TRIM-S / TRIM-V, FIFO prefix)
  behavior.py    averaging-into-losses guardrail
  decision.py    decide_instrument() / decide_all() → DecisionPayload
  main.py        FastAPI endpoints (14: health · reconcile · ingest · lots · run · run-sample · what-if · decisions · holdings · runs · run diff · tax-tracker · policy GET/PUT)
  schema.py      CR-001 runtime DecisionPayload validator
  symbols.py     CR-006 canonical instrument identity (deterministic name-key join; no fuzzy/ticker heuristics)
policy/policy.yaml        D-01…D-15 (signed in Freeze §14; operational serialization only)
fixtures/                 generated CSV fixtures (golden trilogy embedded) + sold_sample.csv
tests/                    backend suites — 497 collected at session epoch `e473417` (unit · gates · scoring · confidence · trim · hysteresis · decision · audit · policy · tax · diff · API · schema · determinism · import_errors · golden fixtures · CR-005/006/007/009/012A/012B/018/019); 126 at the Phase-3 build point
scripts/hash_engine.py    cross-process determinism probe
```

## Run

```bash
pip install -r requirements.txt
python fixtures/generate_fixtures.py fixtures   # regenerate fixtures
pytest -q                                       # suite size is epoch-stamped (see epochs table): 497 collected at e473417
cd frontend && npx tsc --noEmit                 # frontend type-check clean
uvicorn app.main:app --host 0.0.0.0 --port 8000 # API
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/v1/health` | liveness + engine version + phase |
| POST | `/api/v1/reconcile` | dry-run cost-basis reconciliation (G0) |
| POST | `/api/v1/ingest` | Phase 1 foundation only |
| GET  | `/api/v1/lots/{instrument}` | per-lot FIFO view |
| POST | `/api/v1/run` | **full engine run** → DecisionPayload (optional `sold` file adds `tax_year`) |
| POST | `/api/v1/run-sample` | run the bundled golden-fixture demo through the full engine (no file upload) — used by the demo + acceptance test |
| POST | `/api/v1/what-if` | recompute with policy overrides (never persisted, never mutates policy) |
| GET  | `/api/v1/decisions?run_id=` | last / specific decision payload (served from the persisted store) |
| GET  | `/api/v1/holdings/{instrument}` | one holding's full decision (from latest persisted run) |
| GET  | `/api/v1/runs` | run history list (run_id, as_of, policy_version, content_hash) |
| GET  | `/api/v1/runs/{run_id}/diff` | diff a run against its predecessor (decision/score/gate changes, added/removed, distribution) |
| GET  | `/api/v1/tax-tracker?fy=` | realised tax year: gross/net, S.74 set-off, exemption headroom, carry-forward, open-position split |
| GET/PUT | `/api/v1/policy` | read / validate+commit policy (versioned; invalid PUT → 422, file untouched) |

## Golden precedence fixtures (Freeze §11)

Asserted at **data-fact level** (Phase 1) and **decision level** (Phase 2):

| Test ID | Fixture | Decision |
|---|---|---|
| GOLDEN-G2-TRIM-S-SALASAR | Salasar (pledge 4.0, alloc > 1.5× micro band) | G2 → TRIM-S |
| GOLDEN-G1-EXIT-ASHOKA | Ashoka (pledge 12.4, 16 declining all-red lots) | G1 → EXIT |
| GOLDEN-G3-HOLD-LT | Larsen & Toubro (22d to LTCG, valuation < 85) | G3 → HOLD |

Plus precedence proofs: G1 beats G2/G3/G4 · G2 beats G3 ("risk caps are never
tax-deferred") · G3 beats G4 · governance is never partial. G0 (broken
reconciliation) → NO-DECISION.

## Tax golden fixtures (Phase 3 — second fixture family)

| Test ID | Rule | Expected |
|---|---|---|
| GOLDEN-TAX-LTCG | >12mo gain | LTCG; ₹1.25L exemption; 0 tax under headroom |
| GOLDEN-TAX-STCG | ≤12mo gain | STCG; 20%; no exemption |
| GOLDEN-TAX-EXEMPTION | LTCG above ₹1.25L | 12.5% on the excess only |
| GOLDEN-TAX-S74-SET-OFF | STCL 60k, STCG 40k, LTCG 100k | STCL offsets STCG then LTCG → net LTCG 80k → 0 tax; LTCL offsets LTCG only |
| GOLDEN-TAX-CROSS-FY | LTCL carried forward | offsets later-year LTCG; lapses at 8 years |

FIFO sell matching (`match_sells_fifo`) and tax-aware sequencing (`rank_candidates`:
LTCG-eligible gains first, then ascending STCG) are covered in `tests/test_tax.py`.

## Frontend (React + TypeScript + Vite)

`frontend/` is a pure **renderer** of the authoritative backend — the browser never
computes a decision, a score, or a tax number (ADR-1a). It talks to the engine only
through the Vite dev-server proxy (`/api` → `http://127.0.0.1:8000`) using relative URLs.

```
frontend/src/
  api/            client.ts · engine.ts · tax.ts · history.ts · policy.ts   ← UI-1 gate
  types.ts        DecisionPayload / Holding / TaxYear / Policy / RunDiff types
  components/     Header · InputsView · DecisionsView · HoldingDetail ·
                  WeightsView · TaxView · HistoryView · ActivityLogPanel · ui primitives
  utils/          exportDecisions.ts (client-side export of the authoritative payload)
  App.tsx         tab shell + state (+ sold-ledger upload wiring)
                  (ActivityLogPanel / exportDecisions / HoldingDetail are post-v1.0.0
                  additions — IMPLEMENTED, pending E2E-018 observed-rendered verification)
```

**UI gates delivered in order:**
- **UI-1** — single API adapter layer; components never construct raw `fetch`.
- **UI-2** — Decisions screen (table, badge, confidence, score, gate, action queue).
- **UI-3** — Detail drawer (decision, confidence, sub-scores, drivers, why-now,
  evidence, behavior, trim, FIFO lots, provenance).
- **UI-4** — Run history + diff (run N vs N-1, decision/score/gate changes).
- **UI-5** — Tax tracker (gross/net, S.74 set-off, exemption, carry-forward, open split) — **render, don't calculate**.
- **UI-6** — What-if: weight sliders → debounced `/what-if` → "Preview — not authoritative" banner. No local recompute.

**DecisionPayload contract: v1 · UI contract gate: UI-1…UI-6 PASS (2026-08-22).**
`frontend/src/types.ts` is the frozen serialization of this contract; the backend
`decision.py` payload is its authority.

**Run (both servers):**
```bash
# backend (port 8000)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# frontend (port 5173, proxies /api)
cd frontend && npm install && npm run dev
```

**Acceptance test (backend authoritative, UI renders exactly):** the bundled demo
run must display `SALASAR → TRIM-S (G2)`, `ASHOKA → EXIT (G1)`, `LT → HOLD (G3)` —
verified against the live payload; the browser never derives them.

## Domain separation (kept by design)

`TaxLedger` (`app/tax.py`) · `RunHistory` (`app/store.py`) · `DecisionEngine`
(`app/decision.py`) are **three separate modules**. The run store is append-only
decision history — never a generic mutable state database; run-diff derives
run N vs N-1 without rewriting either.

## Implementation audit (Phase 2 gate)

| Item | Question | Result |
|---|---|---|
| A | Determinism: same fixture × policy × new process → same `content_hash`? | ✅ `test_a_determinism_cross_process` (subprocess probe ×2) |
| B | Hysteresis survives process restart? | ✅ SQLite run store; `previous_holdings()` seeds hysteresis from the last **persisted** run |
| C | Does G0 block only the affected instrument? | ✅ blocked instrument → NO-DECISION, others proceed |
| D | Is eligibility applied before renormalisation? | ✅ tier caps applied post-composite; INSUFFICIENT → WATCH |
| E | Confidence `93.6 → 94`? | ✅ `round(clamp(...))`, integer ∈ [20,95] |
| F | Golden trilogy + precedence combos? | ✅ G1>G2>G3>G4 · governance never partial · risk caps never tax-deferred |
| G | Trim adversarial (one lot · cap · dust · cap+dust · tiny · below-target · LTCG/STCG split)? | ✅ `test_g_*` |
| H | Averaging flag is caution-only (never an exit by itself)? | ✅ `test_h_averaging_flag_is_caution_not_exit` |
| I | What-if never persists / never mutates signed policy? | ✅ `test_i_what_if_does_not_persist_or_mutate_policy` |
| J | `/run` payload identical via `/decisions`? | ✅ `test_j_run_and_decisions_identical` |

**Four-state data quality** (proxy ≠ missing ≠ stale ≠ authoritative) is exposed per
holding as `data_quality` and drives the confidence penalties; `position_sizing` and
`tax_efficiency` are authoritative, the other four are v1 proxies until their sources land.
Opportunity Cost remains one 0–100 D-09 category at 10%; the live source is the
PEG proxy where fundamentals exist. D-14 / `hurdle_d14` and watchlist scoring are
not live; D-14 remains signed/provisional until separately authorized.
**Provenance** (engine/normalization/calculation/policy versions + per-file `as_of`) is
carried on every decision payload.

## Notes

- `policy.yaml` is the **operational serialization of the signed D-01…D-15 policy in
  Methodology Freeze §14; it must not introduce or silently alter policy values.**
- Sub-scores are 0-100 where higher = stronger pressure to reduce the position.
- The tax tracker supports realised-tax calculations **when a sold-transactions ledger is
  supplied** (optional `sold` upload on `/run`, or `fixtures/sold_sample.csv` in
  `run-sample`). The user's complete historical sold-transactions dataset is not yet
  guaranteed to exist, so the summary is **provisional until real sold data is provided**;
  it is authoritative for whatever sold ledger is actually supplied.
- v1 is local, single-user, advisory (ADR-3). No live market data (ADR-5). Deterministic
  (Capital Steward Determinism Guarantee, Freeze §8).
- Hysteresis is an explicit input: `run_engine()` (no history) is deterministic; `/run`
  supplies persisted history, so the same fixtures on a second `/run` yield identical
  decisions but a different `content_hash` (the `previous_run` field differs) — correct,
  since history is part of the input.
- `lot_id` is **per-instrument** (oldest unsold lot of a holding = #1), matching the
  per-lot FIFO tax model — a tax lot belongs to one stock, not the whole book.
