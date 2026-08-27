# Capital Steward Engine
# Architecture & UI/UX Design Guidelines (v1.1)

> **v1.1:** incorporates the Methodology Freeze (`methodology-freeze-v1.md`). Decision semantics renamed HOLD/WATCH/TRIM/HARVEST/EXIT; ADR-1a resolves the browser-computation contradiction; §13 adds the freeze amendments. Where this doc conflicts with the Freeze, **the Freeze wins**.

> **Status:** Addendum to Spec v1.0 — structured as **Section 11 (System Architecture)** and **Section 12 (UI/UX Design Guidelines)** so it can be appended verbatim or kept standalone.
> **Companion artifacts:** `profit-booking-engine-analysis.md` (findings/gaps/plan) · `profit-booking-engine-ui-prototype.html` (clickable visual source of truth).
> **Date:** 2026-08-22

---

# SECTION 11 — SYSTEM ARCHITECTURE

## 11.1 Architecture decision records (ADRs)

These lock the "will this be React?" question and everything downstream of it. Each is a one-way door — signed off here, not revisited.

### ADR-1 — React SPA frontend + Python FastAPI backend
**Decision:** Browser app in **React 18 + TypeScript** (Vite build), talking JSON-over-HTTP to a **Python FastAPI** service that owns all decision logic.

**Rationale:**
- The scoring engines (Quality/Growth/Value/Momentum, Arena Platform) already live in Python. Re-implementing the per-lot FIFO tax engine, reconciliation, and composite scoring in JS would create two sources of truth for the same math — the exact failure mode the spec warns against with cross-engine divergence.
- React is the right frontend because the UI is a stateful, interactive dashboard (live weight sliders → instant decision re-derivation, slide-over detail panels, progress overlays) — classic React strengths, not server-rendered pages.
- **Iron rule:** the browser never computes a decision. The UI renders whatever `decisions.json` contains. If a number looks wrong, it's wrong in the engine, and no amount of frontend cleverness should paper over it.

### ADR-1a — Browser never computes a decision or a score (resolves v1.0 contradiction)
**Decision:** v1.0's §12.5 asked the UI to "recompute every decision client-side during weight dragging," which contradicts ADR-1. **Resolved per Freeze §7:** the browser never computes a decision, a composite score, or any decision-relevant number. Weight/parameter drag triggers a debounced `POST /api/v1/what-if` (50 ms) and the UI swaps in the server's authoritative payload. Client-side work is limited to formatting, sorting, filtering, and optimistic "recalculating…" shimmer — never decision math.

### ADR-2 — `decisions.json` is the single contract between tiers
**Decision:** One response schema (fully specified in §11.6) is the only thing the frontend consumes. Every screen is a pure projection of that schema.

**Rationale:** keeps the two tiers independently testable and lets the UI be rebuilt without touching the engine. Also makes the output *machine-exportable* (CSV/JSON download for Ramki's reconciliation workbooks).

### ADR-3 — Advisory mode, never auto-execute
**Decision:** Promote spec Enhancement #4 from "enhancement" to **design principle of v1**. Stage 1 gates auto-*flag* (red banner, +1-day review); Stage 2 composites are always advisory, surfaced for review. There is no broker integration and no auto-order path in v1.

**Rationale:** thesis quality and conviction do not reduce cleanly to a number; the human reviews every recommendation.

### ADR-4 — Append-only decision log
**Decision:** Every run writes an immutable `decisions` record keyed by `run_id` with a hash of the input files + policy. Nothing is ever updated in place.

**Rationale:** this is what makes the backtest harness (Enhancement #1) possible later, and gives an audit trail of *what the engine said, when, on what inputs*.

### ADR-5 — CSV upload for inputs in v1 (no live market integration)
**Decision:** v1 ingests the three CSVs (portfolio, screener, trade ledger) via file upload. No live price/NSE/Screener.in API calls.

**Rationale:** the three files are the known source of truth; live integration adds auth, rate-limit, and staleness complexity with no decision-logic benefit in v1. Revisit in v2 (read-only market data only).

### ADR-6 — Static single-file HTML prototype is the design source of truth
**Decision:** The prototype (`profit-booking-engine-ui-prototype.html`) defines layout, color, component behavior, and interaction. The React build ports it 1:1. It is also kept as a zero-dependency fallback deliverable. **The prototype is the visual and interaction source of truth, but never the source of truth for decision computation** — `decisionOf()`/`compositeOf()` must not be ported into React (ADR-1a).

**Rationale:** the in-app preview environment has no network, so a React/CDN build won't render there — a single self-contained file previews instantly and is fully portable. The production app is the same screens, React-ified.

### ADR-7 — Policy is data, not code
**Decision:** weights, bands, and thresholds (D-01…D-15 from the analysis doc) live in a versioned `policy` store, editable from the UI, and are passed to the engine on every run.

**Rationale:** spec §4.1 explicitly demands configurable parameters; hardcoding them makes the what-if slider (Enhancement #3) impossible.

---

## 11.2 System diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                 BROWSER — React 18 + TypeScript SPA                  │
│                                                                      │
│  [Inputs & Policy]  [Decisions]  [Weights & Thresholds]  [Tax Tracker]│
│   uploads · run      table · queue ·     sliders · what-if    budget  │
│                      slide-over                                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  JSON over HTTP  (TanStack Query)
        POST /run  POST /what-if  GET /decisions  GET /holdings/{id}
        GET /tax-tracker  GET/PUT /policy  POST /reconcile  GET /health
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│              PYTHON — FastAPI decision engine (single service)       │
│                                                                      │
│  1 ingest → 2 normalize → 3 reconcile → 4 lot engine →               │
│  5 Stage-1 gates → 6 Stage-2 composite → 7 portfolio layer →         │
│  8 decisions writer (append-only)                                    │
└───────────────┬──────────────────────────────────────┬───────────────┘
                │                                      │
        ┌───────▼────────┐                    ┌────────▼─────────┐
        │  SQLite (local) │                    │  file store      │
        │  lots, positions│                    │  uploaded CSVs   │
        │  fundamentals_  │                    │  dated snapshots │
        │  snapshot,      │                    │  (archive for    │
        │  decisions,     │                    │   score decay &  │
        │  policy, themes │                    │   backtest)      │
        └────────────────┘                    └──────────────────┘
```

**Notes:**
- Single-process FastAPI for v1 (local, single-user). SQLite is a file, not a server — no external DB dependency.
- The **snapshot archiver** (cron or in-app button) copies each uploaded screener into a dated folder — this closes spec gap G-05 (quality score at entry vs now) over time.
- No message queue, no background workers in v1; a run is synchronous (< a few seconds for ~120 stocks).

---

## 11.3 Backend module breakdown

> **CR-020 correction (2026-08-27):** the original v1.1 table named modules/functions before implementation settled. The table below is restated to the as-built inventory (`app/`); where planned and as-built names differ, the as-built module is authoritative.

| Module (`app/`) | Responsibility | Key functions | Output |
|---|---|---|---|
| `ingest` | Parse the 3 CSVs | `parse_portfolio()`, `parse_screener()`, `parse_ledger()` (tolerant; per-slot precheck in `main`) | parsed rows |
| `normalize` | Date disambiguation, source-name preservation, units | date inference + raw-name retention (no ticker mapping — see `symbols`) | canonical rows |
| `symbols` (CR-006) | Deterministic instrument identity + portfolio↔ledger join | `canonical_name_key()`, `build_portfolio_ledger_link()` (fail-closed collision blocking) | canonical join keys |
| `reconcile` | Cost-basis integrity (G0) | per-name qty/invested checks | pass / blocking errors |
| `lot_engine` | Per-lot FIFO tax lots + position roll-up | lot build, `days_to_ltcg`, aggregates (+ fundamentals join) | lots + positions |
| `determinism` | Canonical JSON + `content_hash` | canonical serializer / run hash | hash |
| `schema` (CR-001) | Runtime DecisionPayload validation | payload validator + `DECISIONS` enum (six states) | validated payload |
| `behavior` | Averaging-into-losses guardrail | none / warn / block-adds flags | flag |
| `gates` | Stage 1 gates G1–G3 (G0 handled by caller) | `evaluate_gates()` (single entry; strict precedence G1 > G2 > G3) | gate result |
| `scoring` | Sub-scores, eligibility tiers, bands, four-state data quality | `composite()`, `band_of()`, eligibility caps | scores / tiers |
| `confidence` | Confidence equation | `round(clamp(100 − Σ penalties, 20, 95))` | integer 20–95 |
| `hysteresis` | Asymmetric transitions + N=2 persistence + gate bypass | `apply()`, `bypass()`, `seed()` | stabilized state |
| `trim` | Constrained trim sizing (Freeze §5) | `trim_s()` (to band top), `trim_v()` (ρ), FIFO `sell_plan()` | trim plan |
| `tax` | Tax-year subsystem | FIFO sell matching, S.74 set-off, exemption, carry-forward, `rank_candidates()` sequencing | tax payload |
| `store` | Append-only run store (ADR-4) | `runs` table, `previous_holdings()` hysteresis seed, run diff | persisted runs |
| `decision` | Per-instrument + portfolio decision assembly | `decide_instrument()`, `decide_all()` — action queue, theme concentration | DecisionPayload |
| `pipeline` | Foundation + engine orchestration | `run_foundation()`, `run_engine()`, `decide_on_foundation()` | payloads |
| `policy` | Policy load + validation (policy is data, not code) | loader + validator | policy dict |
| `config` | Version constants + thresholds + paths | — | constants |

Planned modules that did not ship under their v1.1 names (CR-020 record): `portfolio_layer` → responsibilities live in `tax.py` (sequencing), `decision.py` (queue, theme concentration), `store.py`; `writer` → `store.py`; `whatif` → `POST /what-if` in `main.py` (recompute, never persisted); `accumulate_tag` / the ACCUMULATE trigger → **GAP — never implemented (EMM-H3; disposition E2E-017-PD R2-C)**; `map_name_to_ticker` → superseded by the CR-006 deterministic `canonical_name_key()` join (no fuzzy/ticker heuristics — engine guardrail).

---

## 11.4 Pipeline stages (mirrors the prototype's run overlay)

The UI's progress overlay shows exactly these 7 stages — it is a live reflection of the backend pipeline, not decorative:

| # | Stage | Module | Failure behavior |
|---|---|---|---|
| 1 | Parse 3 files & normalize dates (DD-MM vs ISO) | ingest/normalize | Blocking error, per-file message |
| 2 | Reconcile cost basis: `Σ(lot qty × buy) == Invested` | reconcile | **Blocking** (hard data error) |
| 3 | Build per-lot FIFO tax engine (days-to-LTCG, lot P&L) | lot_engine | Blocking if no lots parse |
| 4 | Run Stage 1 hard gates (governance · allocation · tax-defer) | gates | Non-blocking (gates emit, don't crash) |
| 5 | Score Stage 2 composite per bucket profile | scoring | Non-blocking; apply Freeze §3 eligibility tiers + critical-category rules **first**, then renormalise weights within the eligible set |
| 6 | Rank candidates · theme rebalance · tax-year budget | portfolio_layer | Non-blocking |
| 7 | Write `decisions` (append-only log) + return payload | writer | Blocking (a run that can't persist must not report success) |

---

## 11.5 Data model (tables)

From analysis §8.7, finalized here:

> **CR-020 correction (2026-08-27):** as built, only the `runs` table (`data/engine.db`, ADR-4 append-only) and the versioned `policy/policy.yaml` file physically persist; `lots`/`positions` are in-memory structures rebuilt each run, not stored tables. Row annotations below mark planned-but-unimplemented structures.

| Table | Columns (key fields bold) | Append-only? |
|---|---|---|
| `lots` | **lot_id**, instrument, trade_date, qty, buy_price, ltp, days_held, days_to_ltcg, ltcg_eligible, lot_gain, lot_gain_pct | Rebuilt each ingest |
| `positions` | **instrument**, name, bucket, qty_held, avg_buy, invested, current_value, alloc_pct, gain_pct, first_date, last_date, theme_tags | Derived from lots |
| `fundamentals_snapshot` | **snapshot_id**, **as_of_date**, instrument, pe, pb, peg, roe, roce, growth fields, debt_equity, pledge_pct, dii_3m, fii_3m, sma_200, premiums… | **CR-022 update (2026-08-27):** the snapshot archiver now exists as `app/archive.py` — raw input bytes + canonical normalized foundation corpora + policy snapshots persist immutably under `data/archive/` (content-addressed blobs + append-only hash-chained manifest). Dated fundamentals series accumulate from CR-022 activation forward; **no table named `fundamentals_snapshot` exists** (storage is the blob/manifest pair), G-04/G-05 remain OPEN pending separate authority decisions, and pre-activation history remains unrecoverable. See `cr022-snapshot-archive.md` |
| `decisions` | **run_id**, **as_of**, input_hash, policy_version, payload_json | **Yes** |
| `policy` | **policy_id**, **effective_from**, weights_json, thresholds_json, bands_json | **Yes (versioned)** |
| `themes` | **instrument**, theme | **CR-023 update (2026-08-28):** implemented differently — a standalone authority-controlled document `themes/themes.yaml` (versioned, effective-dated, provenance-bearing; taxonomy v1 signed off; assignments performed only by the authority) resolved per position and archived per run (CR-022 pattern). Not a SQLite table, not policy.yaml. Theme concentration groups manual-first with `sub_sector` fallback; `sub_sector` itself is untouched. See `cr023-manual-theme-tags.md` |
| `sold` | **sell_id**, instrument, qty, sell_date, sell_price | Implemented differently: optional sold-transactions CSV on `POST /run` (or `fixtures/sold_sample.csv` via `run-sample`), consumed by `tax.py`; not a stored table |

**Provenance (Freeze P1-4):** every input row carries `source, source_version, source_as_of, ingested_at, normalization_version`; every derived metric carries `calculation_version, policy_version`. Same lineage philosophy as `input_hash` + `policy_version`, applied to the data itself.

---

## 11.6 API contract

All responses are `application/json`. Errors use a uniform envelope.

### `POST /api/v1/run`
Multipart upload of the three files + optional policy override. Synchronous in v1; returns the full payload below (also persisted).

```
Content-Type: multipart/form-data
  portfolio.csv, screener.csv, ledger.csv   (required, all three)
  policy_overrides (optional JSON string)
  as_of (optional ISO date; defaults to today)
→ 200  { full decision payload (§11.7) }
→ 4xx  { error envelope }        // e.g. reconcile mismatch
```

### `POST /api/v1/what-if`  (Enhancement #3 — sensitivity)
```
{ "run_id": "…", "policy_overrides": { "weights": {…}, "thresholds": {…} } }
→ 200 { full decision payload }   // computed only — NOT persisted to decisions log
```

### `GET /api/v1/decisions?run_id=…`
Returns the stored payload for a past run (audit/backtest read path).

### `GET /api/v1/holdings/{instrument}?run_id=…`
Single holding detail, including `lots[]`, `subscores`, `trim`, `tax_status`.

### `GET /api/v1/tax-tracker?fy=2026-27`
Tax-year budget summary (§11.7 `portfolio_summary` + sequencing rules). Rendered as **provisional** until sold-transactions data exists.

### `GET /api/v1/runs`
Run history list: `run_id, as_of, engine_version, policy_version, input_hash, holdings_count, gates_fired`.

### `GET /api/v1/runs/{run_id}/diff`
Diffs a run against its predecessor: per-instrument `decision`/`score` changes with the contributing deltas (e.g. "SALASAR TRIM → HARVEST, score 73 → 79, PE premium +8%, allocation +0.7%"). This is the operational review surface, far more useful than re-reading the whole portfolio each cycle.

### `GET /api/v1/policy` / `PUT /api/v1/policy`
Read/write the versioned policy. `PUT` creates a new version (never mutates).

### `POST /api/v1/reconcile`
Dry-run reconciliation only — returns the report without scoring. Used by the "validate inputs" action before a full run.

### `GET /api/v1/health`
Liveness + engine version + data-as-of of the last run.

### Error envelope (uniform)

> **CR-020 correction (2026-08-27):** restated to the as-built wire shape (`app/main.py:_api_error`). The previously documented flat `{"error": …}` envelope and code list were design-time text and were never the shipped serialization (recorded documentation-staleness item C3).

As-built envelope (FastAPI serializes `detail` verbatim):

```json
{
  "detail": {
    "error": {
      "code": "IMPORT_ERROR",
      "severity": "blocking",
      "message": "portfolio.csv line 42: …",
      "stage": "parse:portfolio",
      "file": "portfolio.csv"
    }
  }
}
```

As-built status/code mapping: `400 IMPORT_ERROR` (per-slot parse precheck with `stage: parse:<slot>` + `file`; ingest/ValueError family with `stage`) · `500 ENGINE_ERROR` (unexpected engine exceptions, with `stage`) · `500 INTERNAL_ERROR` (DecisionPayload validation failure, `details.errors`) · `400` plain detail string (non-`.csv` upload) · `404` plain detail string (no run yet / unknown run_id or instrument) · `422` FastAPI request validation / invalid `PUT /policy` (policy file untouched).

Data-integrity and data-quality outcomes travel in the **payload**, not the envelope: `warnings[]` entries (`SYMBOL_UNMATCHED`, `PARTIAL_DATA`, `STALENESS`, `DATE_FORMAT_INFERRED`, `LEDGER_ONLY_LOTS`) and G0 blocking outcomes (`RECONCILE_MISMATCH`, `NO_LOTS`, `CANONICAL_NAME_COLLISION`) surface as NO-DECISION holdings plus payload warnings.

---

## 11.7 Response schema (extends spec §4.3 — the UI's only input)

```json
{
  "run_id": "run_20260822T091500",
  "as_of": "2026-08-22",
  "engine_version": "1.0.0",
  "data_as_of": {
    "portfolio": "2026-08-15",
    "screener": "2026-08-15",
    "ledger": "2026-08-15",
    "staleness": [
      { "file": "portfolio", "days_behind": 7, "flag": "warn" }
    ]
  },
  "portfolio_summary": {
    "total_value": 129830.0,
    "holdings_count": 10,
    "decision_distribution": { "HOLD": 5, "WATCH": 1, "TRIM": 3, "HARVEST": 0, "EXIT": 1 },
    "stage1_gates_fired": 3,
    "tax": {
      "fy": "2026-27",
      "ltcg_booked": 18400,
      "ltcg_exemption": 125000,
      "ltcg_headroom": 106600,
      "stcg_booked": 31200,
      "stcl_harvestable": 9800
    }
  },
  "holdings": [
    {
      "instrument": "SALASAR",
      "name": "Salasar Techno Engg",
      "bucket": "micro",
      "decision": "TRIM",
      "reason_tree": { "decision_path": "G2 → TRIM (mode S)" },
      "why_now": { "primary_trigger": "Allocation crossed 3% micro-cap cap" },
      "previous_run": { "decision": "TRIM", "composite_score": 71, "as_of": "2026-08-15" },
      "composite_score": 87.0,
      "confidence": 81,
      "confidence_breakdown": {
        "missing_data_penalty": 0,
        "divergence_penalty": 4,
        "boundary_penalty": 0,
        "proxy_penalty": 15
      },
      "subscores": {
        "position_sizing": 92,
        "valuation_stretch": 97,
        "quality_drift": 60,
        "tax_efficiency": 35,
        "opportunity_cost": 90,
        "technical_regime": 70
      },
      "stage1": { "fired": true, "gates": ["allocation_breach"] },
      "primary_drivers": [
        "HARD GATE: allocation 9.8% vs 3% micro-cap cap — trim to cap",
        "PE 55× vs own 5-yr median 18× — 87% of return is re-rating, not earnings"
      ],
      "watch_flags": ["FII holding down 3 consecutive quarters"],
      "tags": [],
      "behavioral_flags": [],
      "trim": {
        "suggested_qty": null,
        "suggested_value": 3680,
        "fifo_lots_to_sell": [1, 2, 3],
        "tax_breakdown": { "stcg": 680, "ltcg": 0 },
        "est_transaction_cost": 12.9,
        "min_position_check": "ok"
      },
      "tax_status": {
        "mixed_ltcg": false,
        "oldest_lot_days_held": 121,
        "oldest_lot_days_to_ltcg": 244,
        "ltcg_eligible_lots": 0
      },
      "data_completeness": {
        "position_sizing": true, "valuation": true, "quality": true,
        "tax": true, "opportunity_cost": false, "technical": false
      },
      "evidence": {
        "coverage": 0.67,
        "tier": "ADVISORY",
        "missing_weight": 0.33,
        "critical_categories_missing": ["valuation_stretch"],
        "decision_cap": "WATCH"
      },
      "lots": [
        {
          "lot_id": 1, "trade_date": "2026-04-23", "qty": 16, "buy_price": 42.0,
          "ltp": 76.5, "pnl": 552.0, "pnl_pct": 82.1,
          "days_held": 121, "days_to_ltcg": 244, "ltcg_eligible": false
        }
      ],
      "next_review_date": "2026-08-23"
    }
  ],
  "portfolio_layer": {
    "action_queue": [
      { "rank": 1, "instrument": "ASHOKA", "decision": "EXIT", "reason": "RISK", "score": 48.0 },
      { "rank": 2, "instrument": "SALASAR", "decision": "TRIM", "reason": "SIZING", "score": 87.0 },
      { "rank": 3, "instrument": "KALYANKJIL", "decision": "TRIM", "reason": "VALUATION", "score": 63.0 }
    ],
    "theme_concentration": [
      { "theme": "PSU / Infra", "members": ["SALASAR", "ASHOKA", "BCC"],
        "alloc_pct": 16.4, "band": [0, 15], "status": "breach" }
    ],
    "redeploy_correlation_check": []
  },
  "warnings": [
    { "code": "STALENESS", "message": "portfolio.csv is 7 days behind as-of" },
    { "code": "PARTIAL_DATA", "instrument": "AGIGREENPAC",
      "message": "Not in screener universe — position-sizing + tax inputs only" }
  ]
}
```

**Field semantics the UI must honor (from the analysis doc):**
- `decision` ∈ `HOLD | WATCH | TRIM | HARVEST | EXIT` (renamed per Freeze §1: WATCH = old HOLD-WATCH, TRIM = old PARTIAL, HARVEST = old FULL). EXIT is Stage-1-only; a `NO-DECISION` status is returned on G0 blocking errors.
- `reason_tree` — machine-readable explanation (Freeze §9.1): per-stage gates, per-category scores + contributors, and `decision_path`.
- `why_now` / `previous_run` — "why this decision *now*" with contributor deltas and the prior run (Freeze §9.2).
- `confidence` ∈ 20–95 (integer); always rendered with its breakdown, never as a bare number. Confidence is `round(clamp(100 − Σ penalties, 20, 95))` — the breakdown lists the *penalties*, not confidence parts.
- `evidence` — eligibility state (Freeze §3): `coverage`, `tier` (`NORMAL | ADVISORY | INSUFFICIENT`), `missing_weight`, `critical_categories_missing`, `decision_cap`. The UI renders why a decision was capped instead of inferring it.
- `subscores` are 0–100; the composite is the weighted blend, **renormalized** over available categories, with the missing weight reported in `data_completeness`.
- `behavioral_flags` carry the averaging-into-losses guardrail (values: `none | averaging_warn | averaging_block_adds`).
- `trim.suggested_qty` is **null** when a trim is not applicable (HOLD/EXIT-with-no-value) — the UI shows "—", not 0.
- `tags` carry `ACCUMULATE` (never a competing decision).

---

## 11.8 Security & operational notes (v1)

- **Local, single-user:** no auth in v1; runs on localhost. Add auth only if hosted.
- **Upload limits:** each CSV ≤ 10 MB; reject non-CSV extensions; sanitize filenames.
- **CSV-injection guard:** if re-exporting CSVs, prefix any cell starting with `= + - @` with `'`.
- **No secrets:** no broker keys, no external API keys in v1.
- **Data retention:** uploaded CSVs kept only in the dated archive (intentionally — that archive *is* the score-decay dataset); the raw upload temp files are deleted after ingest.

---

# SECTION 12 — UI/UX DESIGN GUIDELINES

## 12.1 Frontend stack

> **CR-020 correction (2026-08-27):** several stack choices in the original table were never adopted (recorded documentation-staleness item C4). Rows below are restated to the as-built `frontend/package.json` (React 18.3.1 · Vite · TypeScript; no state, table, or test libraries).

| Concern | Choice (as built) | Notes |
|---|---|---|
| Framework | React 18 + TypeScript + Vite | Dev server proxies `/api` → FastAPI (`vite.config`: `allowedHosts: true`) |
| Server state | None (no TanStack Query) | Plain React hooks over the single `api/` adapter layer (UI-1) |
| Client state | React component state (no Zustand) | Tab, selected holding, what-if draft values |
| Styling | Design tokens (CSS custom properties) | Match the prototype; Tailwind not used |
| Tables | Plain `<table>` markup (no @tanstack/react-table) | Holdings table is hand-rolled |
| Virtualization | Not used | — |
| Charts | None | Bars/rings are pure CSS/SVG (already in prototype) |
| E2E / component tests | **None** (no Playwright/Vitest dependency) | See §12.9 correction; any future harness requires a separately named CR |

**Why these:** the prototype already implements every visual element with plain CSS/SVG — no chart library is needed, which keeps the bundle small and the preview-environment constraint moot.

## 12.2 Component tree

```
<App>
 ├─ <Header>
 │   ├─ logo · title · subtitle
 │   ├─ <AsOfChip/>            — "as-of 2026-08-22"
 │   ├─ <AdvisoryBanner/>      — "⚠ ADVISORY MODE — Stage 2 never auto-executes"
 │   └─ <EngineStatusChip/>    — "● Engine v1.0 · shadow" | "idle" | "running"
 ├─ <TabBar>                   — 01 Inputs · 02 Decisions · 03 Weights · 04 Tax
 ├─ <Main>
 │   ├─ <InputsView>
 │   │   ├─ <Dropzone/>  ×3    — portfolio / screener / ledger
 │   │   ├─ <RunControls/>     — Run engine · Load sample · Validate-only
 │   │   ├─ <ReconcileStatus/> — pass/fail + mismatch rows
 │   │   └─ <PolicySnapshot/>  — read-only D-01…D-15 quick view
 │   ├─ <DecisionsView>
 │   │   ├─ <StatStrip/>       — value · decision dist · headroom · gates fired
 │   │   ├─ <HoldingsTable/>   — sortable → row click opens <HoldingDetail/>
 │   │   ├─ <ActionQueue/>     — ranked EXIT/TRIM/HARVEST (priority + reason class)
 │   │   └─ <ThemeConcentration/>
 │   ├─ <WeightsView>
 │   │   ├─ <WeightSliders/>   — 6 sliders + live total + normalisation note
 │   │   └─ <ThresholdsPanel/> — bands, hysteresis, re-rating share, etc.
 │   └─ <TaxView>
 │       ├─ <GainBudget/>      — headroom bars
 │       └─ <SequencingRules/>
 ├─ <HoldingDetail/> (SlideOver, role="dialog")
 │   ├─ header (ticker, name, bucket, decision badge, close)
 │   ├─ <CompositeCard/>      — confidence ring + sub-score bars
 │   ├─ <PositionSnapshot/>
 │   ├─ <DriversList/>        — primary_drivers (color-coded by severity)
 │   ├─ <WatchFlags/>
 │   ├─ <TrimBox/>            — qty/value/lots + FIFO tax note
 │   └─ <LotTable/>           — per-lot FIFO rows
 ├─ <RunOverlay/>             — 7 progress steps (live pipeline stages)
 └─ <Toasts/>                 — warnings/errors (staleness, partial-data)
```

## 12.3 Design tokens (must match prototype)

```css
/* Surfaces */
--bg:#0b0f17;        --panel:#121826;     --panel2:#161e30;
--line:#232c42;      --line2:#2c3752;
/* Text */
--text:#e6ecf7;      --muted:#8b96ad;     --dim:#5c6b85;
/* Semantic */
--green:#34d399;     --yellow:#fbbf24;    --orange:#fb923c;
--violet:#a78bfa;    --red:#f87171;       --blue:#60a5fa;
/* Mono */
--mono: ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
```

| Token | Use |
|---|---|
| `--green` | HOLD badge, positive P&L, in-band states, success |
| `--yellow` | WATCH badge, warnings, averaging flag, near-band |
| `--orange` | TRIM badge, STCG-related |
| `--violet` | HARVEST badge |
| `--red` | EXIT badge, hard gates, negative P&L, blocking errors |
| `--blue` | tickers/links, ACCUMULATE tag, information |
| `--mono` | **all numbers** (prices, %, scores, days) — tabular alignment is a requirement |

**Decision badge spec** (single source of truth):

| Decision | Label | Color |
|---|---|---|
| HOLD | `HOLD` | `#34d399` |
| WATCH | `WATCH` | `#fbbf24` |
| TRIM | `TRIM` | `#fb923c` |
| HARVEST | `HARVEST` | `#a78bfa` |
| EXIT | `EXIT · THESIS BREAK` | `#f87171` |
| NO-DECISION (G0) | `NO-DECISION` | `#94a3b8` |

Badge recipe: `color: <color>; background: <color>@10%; border: 1px solid <color>@27%;` with a 7px dot.

## 12.4 Screen-by-screen specification

### 12.4.1 View 01 — Inputs & Policy
**Purpose:** everything needed to run the engine; the only screen that writes.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│ [Dropzone portfolio.csv] [Dropzone screener.csv] [Dropzone ledger.csv] │
├───────────────────────────────┬──────────────────────────────┤
│ RUN CONTROLS                  │ POLICY SNAPSHOT (read-only)  │
│  ▶ Run engine   Load sample   │  max cap 10% · bands …       │
│  Validate-only                │  quality floor 40 · pledge 10%│
│  reconciliation hint (kbd)    │  LTCG window 30d              │
└───────────────────────────────┴──────────────────────────────┘
```

**Dropzone states:** empty → hover → loaded (filename + row count + as-of) → error (parse/mismatch).
**Run controls:** `Run engine` (full pipeline → overlay → navigates to Decisions), `Validate-only` (POST /reconcile, no navigation), `Load sample` (fills with bundled mock rows for demos).
**Reconcile status line** shows `Σ(lot qty × buy) == Invested` and `Σ(lot qty) == Qty Held` pass/fail with per-instrument mismatch rows.

### 12.4.2 View 02 — Decisions
**Purpose:** the primary read surface.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  [Stat: Portfolio value] [Stat: Decisions dist] [Stat: headroom] [Stat: gates] │
├───────────────────────────────────┬──────────────────────────┤
│ HOLDINGS TABLE (sortable)         │ ACTION QUEUE (ranked)    │
│  Instrument│Bucket│Alloc│G/L│…     │  1 ASHOKA   EXIT   48    │
│  …row click → slide-over…          │  2 SALASAR  TRIM   87    │
│                                    │  3 KALYAN   TRIM   63    │
│                                   ├──────────────────────────┤
│                                   │ THEME CONCENTRATION      │
│                                   │  PSU/Infra 16.4% ▓▓▓▓ warn│
└───────────────────────────────────┴──────────────────────────┘
```

**Holdings table columns** (fixed order, sortable by click):
`Instrument` (ticker + ACCUMULATE/AVG-DOWN tag chips) · `Bucket` · `Allocation %` · `Gain/Loss %` · `Decision` (badge) · `Score` (composite, colored by decision) · `Confidence %`.

**Stat strip semantics:**
- **Decisions** stat shows the 5-decision distribution as colored counts (green/yellow/orange/violet/red).
- **Headroom** stat shows `₹18,400 / 1,25,000` with a "14.7% · exemption intact" sub-line.
- **Gates fired** stat is red-tinted when > 0.

**Action queue:** ordered by priority **EXIT → TRIM → HARVEST** (risk/sizing outranks valuation), then composite score within a tier; each row carries a reason class chip **RISK / SIZING / VALUATION** (Freeze §2.1). Empty state text "No candidates." Sub-note: *"Not a plain composite sort — risk/sizing actions outrank valuation harvests."*

**Theme concentration:** one bar row per theme (PSU/Infra, rate-sensitive financials, …) with band marker; `breach` state renders the bar in `--yellow` with a warning note.

### 12.4.3 View 03 — Weights & Thresholds
**Purpose:** policy tuning + the what-if slider (Enhancement #3).

**Layout:**
```
┌─────────────────────────────────┬────────────────────────────┐
│ CATEGORY WEIGHTS                │ THRESHOLDS & GATES         │
│  Position sizing  ▓▓▓ 25%       │  bands 0-30/31-55/56-75/76+│
│  Valuation        ▓▓▓ 25%       │  hysteresis 2 runs         │
│  Quality drift    ▓▓▓ 20%       │  re-rating 65%/80%         │
│  Tax efficiency   ▓▓▓ 15%       │  min position 0.5%/₹5k     │
│  Opportunity cost ▓▓ 10%        │  participation 10% ADV     │
│  Technical        ▓ 5%          │  txn cost 0.35%/1.0%       │
│  TOTAL ▓▓▓▓▓▓▓▓▓ 100%  ✓        │  OC source: PEG proxy      │
└─────────────────────────────────┴────────────────────────────┘
```

**CR-008 wording note:** Opportunity Cost remains one 0–100 D-09 category at
10%. The live source is the PEG proxy where fundamentals exist; D-14 /
`hurdle_d14` and watchlist scoring are not live, and D-14 remains
signed/provisional until separately authorized.

**Interactions:**
- Each slider range 0–50. The running total bar is green at exactly 100%, red otherwise, with a note: *"Composite normalised to the running total (sum ≠ 100)."*
- **Live sensitivity (Freeze §7):** changing a weight does **not** recompute client-side. Dragging shows optimistic "recalculating…" shimmer and a debounced (50 ms) `POST /what-if` swaps in the authoritative payload. The UI never derives a decision or score.
- A "commit policy" button persists via `PUT /api/v1/policy` (versioned); dragging alone does not persist.
- Thresholds panel is D-01…D-15 read/write with the same commit semantics.

### 12.4.4 View 04 — Tax-Year Tracker (provisional until sold-data exists)
**Purpose:** FY gain budget + sequencing rules.

**Layout:**
```
┌─────────────────────────────────┬────────────────────────────┐
│ GAIN BUDGET (FY 2026-27)        │ SEQUENCING RULES           │
│  LTCG booked  ▓░░░░ ₹18,400     │  1 book small LTCG first   │
│  Headroom     ▓▓▓▓▓ ₹1,06,600   │  2 harvest ST losers       │
│  STCG booked  ▓▓░░░ ₹31,200     │  3 no wash-sale rule       │
│  STCL harvest ▓░░░░ ₹9,800      │  4 never defer stretched    │
│  ⚠ open-positions-only caveat   │    positions for LTCG      │
└─────────────────────────────────┴────────────────────────────┘
```

**Mandatory caveat line** (until sold-transactions export exists): *"All three files contain only open positions — realized-gains feed is a gap. Values are mock until the sold-transactions export is wired."* This is not a cosmetic disclaimer — it prevents the ₹1.25L headroom from being silently wrong.

### 12.4.5 Holding detail — SlideOver
**Purpose:** everything about one holding; the deepest screen.

**Anatomy (top → bottom):**
1. **Header:** `ticker` (mono, dim) · name + bucket · decision badge · close ✕.
2. **Composite & confidence card:** confidence ring (SVG, colored by decision) + composite score; beneath it, **six sub-score bars**, each labeled with category name + weight; a note explains the confidence formula.
3. **Position snapshot:** allocation %, gain/loss % (green/red), pledged promoter % (red if >10%), next review date.
4. **Primary drivers:** color-coded list — hard-gate items get a red left-border + `gate` class; strong signals amber; informational neutral.
5. **Watch flags:** warning list; `behavioral_flags` render as red- or amber-left-border rows (e.g. "Averaging-into-losses: 36 buy lots since May, net −4.3%").
6. **Trim box** (only when `trim` present): three stats — Qty, Value, Lots — plus the FIFO note ("All lots 81d → STCG 20%… Defer 284d for LTCG, or book now").
7. **FIFO tax lots table:** columns `Lot · Trade date · Qty · Buy · LTP · P&L · % · Held · To-LTCG`, oldest-first. The lots selected by the trim are row-highlighted. `To-LTCG` renders `LTCG ✓` in green when eligible, else `Nd`. A `mixed_ltcg: true` state adds a `MIXED LTCG` chip in the header.

**Interactions:** Esc closes; scrim click closes; focus trapped (role="dialog", aria-modal).

## 12.5 Interaction specifications

| Trigger | Behavior |
|---|---|
| Click **Run engine** | Validate 3 files loaded → show `RunOverlay` with 7 live steps → on success: navigate to Decisions, toast "run_… written" |
| Click **Load sample** | Populate dropzones with bundled mock rows (demo-safe) |
| Click holding **row** | Open SlideOver, fetch `/holdings/{id}` if not in payload |
| Drag **weight slider** | Optimistic shimmer → debounced `/what-if` (50 ms) → authoritative payload swaps in (no client-side decision math) |
| Click **Commit policy** | `PUT /policy` → toast "policy vN active" |
| Click **sort header** | Sort table by that column (numeric-aware) |
| Hover **bar/sub-score** | Tooltip with raw value + category weight |

## 12.6 Data-display rules

- **Numbers:** all numeric values in `--mono`, right-aligned, thousands-separated (`₹1,26,430` Indian grouping).
- **Sign coloring:** positive P&L green with `+`, negative red with `−`.
- **Percentages:** one decimal (e.g. `73.4%`); composite score integer.
- **Nulls:** render `—`, never `0` (a null trim is "not applicable", which is information).
- **Confidence:** always `81%` with the breakdown on hover/expand — never a bare number (analysis §2.2).
- **Data completeness:** holdings with partial coverage get a small "partial-data" chip; the missing-category weight is visible in the sub-score panel.
- **Staleness:** `data_as_of` older than N days (prices/valuation 3d, ledger 7d) surfaces a header `as-of` chip warning, not a silent failure.

## 12.7 Responsive & accessibility

- **Breakpoints:** 3-up stat/zone grids collapse to 1 column ≤ 900px; tables get horizontal scroll (already in prototype).
- **Contrast:** text `#e6ecf7` on `#0b0f17` ≈ 14:1; muted `#8b96ad` on `#121826` ≈ 7:1; badges use color-on-10%-tint (≥ 4.5:1).
- **Keyboard:** tab order Header → TabBar → content → SlideOver; Esc closes SlideOver/overlay; sliders are native `<input type=range>` with `aria-valuenow`; sortable headers are `<button>` with `aria-sort`.
- **Focus:** visible 2px outline in the semantic color; never `outline:none` without replacement.
- **Reduced motion:** honor `prefers-reduced-motion` — disable spinner/ring animations.

## 12.8 Performance budget

| Target | Approach |
|---|---|
| Slider drag ≥ 60 fps | Optimistic shimmer; authoritative recompute via debounced `/what-if` (50 ms) — no client-side recompute |
| Decisions payload < 250 KB for 120 holdings | Trim `lots[]` to summary in list view; full lots only in SlideOver fetch |
| First paint < 1.5 s | Vite bundle ~< 200 KB gz; no chart lib |
| Table 120+ rows smooth | @tanstack/react-virtual beyond 100 rows |

## 12.9 Testing plan

> **CR-020 correction (2026-08-27):** the Component and E2E rows were planned but never adopted — `frontend/package.json` has no test dependencies or scripts (staleness item C4). Any future UI test harness is a separately named CR; manual / observed-rendered verification (E2E-018 evidence standard) is the interim UI assurance mechanism.

| Layer | Tool | Covers | Status (CR-020, 2026-08-27) |
|---|---|---|---|
| Engine unit | pytest | reconcile math, FIFO lot engine (exact 365-day boundary, split lots, sells), gates, composite renormalization, trim sizing, confidence penalties | CURRENT — suite size epoch-stamped in root README |
| Contract | pytest snapshot | DecisionPayload against fixture CSVs — the UI's only contract | CURRENT (incl. CR-001 runtime payload validation) |
| Component | Vitest + RTL | badge mapping, slider total normalization, null-rendering (`—`), sign coloring | NOT ADOPTED (C4) — never shipped |
| E2E | Playwright | 4 golden flows: **upload→run→inspect detail** · **drag weight→decision flips** · **what-if no-persist** · **reconcile-mismatch error toast** | NOT ADOPTED (C4) — never shipped |

---

## 12.10 Mapping: spec §4.3 output → UI element

| Spec field | UI element | Notes |
|---|---|---|
| `ticker` | row ticker + SlideOver header | mono, blue |
| `decision` | Decision badge (table + SlideOver) | 5-state color table §12.3 |
| `confidence` | ring + `%` in table | always with breakdown |
| `suggested_trim_qty/value` | TrimBox stats | `—` when null |
| `primary_drivers` | DriversList (color-coded) | gate=red, strong=amber, info=neutral |
| `watch_flags` | WatchFlags | red/amber left-border rows |
| `next_review_date` | PositionSnapshot field | drives review cadence |

## 12.11 Out of scope for v1 (explicit)

- Broker/order integration and any auto-execution (ADR-3).
- Live market data / NSE / Screener.in API (ADR-5) — read-only data in v2.
- Multi-user auth / cloud hosting — local single-user only.
- The Divergence dashboard (Enhancement #6) and Post-tax XIRR field (Enhancement #2) are Phase-5 UI additions, not v1.
- Native mobile — responsive web only.

---

## 12.12 Implementation phases (UI-aligned, from the analysis doc)

| Phase | Backend deliverable | UI deliverable | Definition of done |
|---|---|---|---|
| 0 | Snapshot archiver scaffold | (none) | Dated screener archive running |
| 1 | ingest/normalize/reconcile + lot engine | Inputs view live (dropzones + reconcile status) | Fixture CSVs reconcile; mismatch toasts render |
| 2 | gates + scoring + confidence + writer | Decisions view + SlideOver live on real payload | Golden flow 1 passes E2E |
| 3 | trim sizing + behavioral flags + portfolio layer | Action queue, theme concentration, tax tracker | Golden flow 1–3 pass; AVG-DOWN flag visible |
| 4 | what-if + policy store | Weights & Thresholds live (commit + non-persist) | Golden flow 4 passes |
| 5 | enhancements | Divergence dashboard, post-tax XIRR, export CSV | — |

**Sequencing rule:** no UI work on a view until its backend payload field exists and is contract-tested (ADR-2 discipline). The prototype's screens are already the "done" target — each phase ports one screen from static to live.

---

# SECTION 13 — v1.1 FREEZE AMENDMENTS

*These supersede the earlier sections where they differ. Full rationale and equations live in `methodology-freeze-v1.md`.*

## 13.1 What was frozen (summary)
Gate precedence **G0→G4** (governance never partial; risk caps never tax-deferred) · confidence equation with additive penalties + clamp 20–95 · missing-data eligibility tiers + critical-category rules · trim as **constrained optimisation** (modes TRIM-S / TRIM-V, replacing MAX) · hysteresis (enter/exit asymmetry + N=2 persistence) · decision semantics **HOLD/WATCH/TRIM/HARVEST/EXIT** · determinism guarantee + replay test · browser never computes decisions.

## 13.2 New UI elements (P1)
- **Decision vs Action separation:** the primary screen must distinguish *Decision* (HARVEST — target reached), *Confidence* (81%), *Suggested action* (sell 48 shares), and *Human review* (**Required**) — reinforcing the advisory principle.
- **"Why now?" block:** contributor deltas (Allocation +18, Valuation +14, Tax −8) + primary trigger + previous-run line — answers "why this decision *this run*".
- **"Why no action" block:** for HOLD/WATCH winners, list the reasons the engine did *not* book (allocation in band, quality intact, valuation not extreme, days-to-LTCG, no better redeploy) — prevents treating every winner as a sell candidate.
- **Decision-change indicator:** every holding shows `HARVEST 87 ↑ prev TRIM 72 · 2 days ago` or `HOLD 28 · unchanged ×5 runs` — ties into review cadence.
- **Policy validation + impact preview** before Commit (Freeze §10).
- **Provisional tax figures:** LTCG headroom labeled **"provisional"** (not a small footnote) until the sold-transactions export exists.
- **Action-queue priority (Freeze §2.1):** EXIT → TRIM → HARVEST with reason-class chips RISK / SIZING / VALUATION — not a plain composite sort.
- **Evidence block (Freeze §3):** `evidence` in the holding schema (coverage / tier / missing_weight / critical_categories_missing / decision_cap) so the UI states *why* a decision was capped.

## 13.3 Testing additions
Invariant/property tests and exact-boundary tests per Freeze §11, plus the **Decision Determinism Guarantee** (same inputs + policy + engine version ⇒ same content_hash) in CI.

## 13.4 Canonical gate-precedence fixtures
Three mock holdings are the canonical gate-precedence trilogy, fixed and reused in every fixture set:
- **Golden Case A — Risk-cap precedence:** `SALASAR` (pledge 4.0 < 10%, allocation 9.8% > 3% cap, composite 87) → **G2 wins → TRIM-S**.
- **Golden Case B — Thesis-break precedence:** `ASHOKA` (pledge 12.4% > 10%, composite 48) → **G1 wins → EXIT**.
- **Golden Case C — Tax defer:** `LT` (22 days to LTCG, valuation subscore 40 < 85, composite 38 = WATCH band) → **G3 wins → HOLD** (defer).


