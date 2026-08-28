# CR-024 — date-indexed historical fundamentals store/query + G-04 own-history median + G1 history legs (EMM-F2)

**Status:** IMPLEMENTED + FIXTURE-VALIDATED — UNCOMMITTED/UNPUSHED; commit/push and
closure-by-UAT are separate gates.
**Authority lineage:** EMM-F2 discovery → F2-D1…D9 dispositions → G-04 median
methodology gate (**G04-MEDIAN-METHODOLOGY-v1**) → G1 history-legs definition gate
(**G1-HISTORY-LEGS-METHODOLOGY-v1**) → EMM-F2 implementation authorization
(F2-I1…I8, all A) → CR-024 implementation gate.
**Branch:** `arena/01a033db-capstew-engine`. Baseline `9e3bd12a…` (0.5.0) →
post-CR-024 `ENGINE_VERSION = 0.6.0-phase3` (VP-1; capability surface added,
**no scoring/decision input changed**: CALCULATION_VERSION 2.1,
NORMALIZATION_VERSION 1.0, policy_version 1 unchanged).

## What CR-024 builds (exactly three authorized surfaces)

1. **Date-indexed historical fundamentals store/query** (`app/history.py`,
   F2-D1-A): every ingestion event's archived foundation corpus (CR-022) is
   readable by instrument / effective date — **no run_id required**
   (`query_fundamentals`, `all_observations`). Event-driven capture retained
   (F2-D2-A); no periodic capture; nothing is fabricated — dates without an
   archived snapshot simply have no observations; pre-CR-022 history remains
   permanently unavailable (F2-D6-A). Read-only: zero writes to the archive;
   the CR-022 integrity model is untouched (tamper detection proven intact,
   test F).

2. **G-04 own-history PE/PB median** (`pe_pb_medians`) — exactly
   G04-MEDIAN-METHODOLOGY-v1: separate PE/PB medians; trading-day observation
   dates; trailing five-calendar-year window ending at as-of; ≥24 valid
   observations per metric; **both** required; missing omitted; invalid
   (non-finite/≤0) excluded; **no winsorization**; full observation- and
   median-level provenance. **IMPLEMENTED — NOT ACTIVATED** (F2-I5-A): the
   peer-relative premium stays the production scoring input
   (`tests/test_cr024.py::test_n_proxy_retained_not_activated`).

3. **G1 history legs** (`quality_drop`, `pledge_qoq`, `g1_legs`) — exactly
   G1-HISTORY-LEGS-METHODOLOGY-v1: quality_drop = current quality observation
   vs prior eligible comparable observation, **year-over-year**, fires at
   deterioration **≥ 20** (equality fires); missing history ⇒ unavailable /
   non-firing, no interpolation. pledge_qoq = promoter pledge percentage,
   **latest calendar quarter vs immediately preceding quarter**, fires at
   increase **≥ 5 pp** (equality fires); missing either quarter ⇒ unavailable /
   non-firing, no inference. Full observation + derived-leg provenance.
   **IMPLEMENTED AS EVIDENCE — current G1 gate semantics unchanged** (F2-I6-A;
   `test_x_existing_g1_behavior_unchanged` guards gates.py/scoring.py carry no
   history identifiers and decision rows gain no history keys).

Read-only API (no POST/PUT/DELETE — evidence is not user-editable):

* `GET /api/v1/history/fundamentals/{instrument}?metric=&start=&end=&as_of=`
  (404 when no observations exist — honest, never fabricated)
* `GET /api/v1/history/g04/{instrument}?as_of=`
* `GET /api/v1/history/g1/{instrument}?as_of=`

`as_of` defaults to the latest archived `run_as_of` (deterministic; never
wall-clock). All computation is a pure function of archive content + explicit
arguments (`test_w_deterministic_replay_no_wallclock` asserts zero
`date.today`/`datetime.now` usage in the module).

## Implementation-defined conventions (F2-I2 / F2-I3 — SURFACED FOR AUTHORITY REVIEW)

These five conventions were explicitly **unfrozen** by the methodology records
and authorized to be defined by this CR, documented, tested, and surfaced
before closure:

| # | Convention (deterministic) | Tests |
|---|----------------------------|-------|
| **C-1** even-count median | arithmetic mean of the two central order statistics | `test_i_even_count_median_convention`, `test_k_no_winsorization` |
| **C-2** observation-date derivation | archived corpus `provenance.sources.screener.as_of` (engine-resolved F2-D3 dual timestamp); duplicate dates → greatest manifest `seq` wins (latest ingestion supersedes); no dates exist outside archived snapshots | `test_c2_duplicate_date_latest_seq_wins`, `test_e_archive_provenance` |
| **C-3** calendar endpoints | trailing `[as_of − 5 calendar years, as_of]`, **both endpoints inclusive**; leap clamp Feb 29 → Feb 28 | `test_g_window_start_boundary`, `test_h_window_end_inclusion` |
| **C-4** quality-observation composition | the frozen `scoring.quality_drift` sub-score (0–100 badness; sector-aware) recomputed from each archived snapshot's fundamentals; deterioration = **point increase**; "20%" = **20.0 points** on the 0–100 scale. Rationale: identical math production/historical; relative-% on sign-crossing fundamentals is ill-defined | `test_o_quality_observation_composition`, `test_p_yoy_comparison_points`, `test_q_threshold_boundary` |
| **C-5** pledge quarter boundary | **calendar quarters** (Q1 Jan–Mar … Q4 Oct–Dec); per-quarter value = latest-in-quarter observation; latest quarter = quarter of newest observation ≤ as_of; preceding = immediately prior calendar quarter | `test_s_pledge_quarter_boundary_and_latest_in_quarter`, `test_t_pledge_threshold_boundary`, `test_u_pledge_missing_history_non_firing` |

None of these alters the frozen methodology; any authority amendment will be
applied under a new instruction, not silently.

## Fences honored

- G-04 NOT activated; peer proxy in force (`test_n_…`; guard
  `test_g04_proxy_labels_preserved` unchanged).
- G1 gate behavior, decision enum/distribution, queue, sizing, cadence,
  thresholds: **untouched** (`test_x_…`; full 571-suite green incl. the
  CR-023 LINEAR_LEGACY pins and determinism suite).
- No broad quality/composite/valuation **series** (F2-I4-A): only the exact
  leg/median computations above exist.
- Forbidden surfaces untouched: `policy/`, freeze/governance docs,
  `MANIFEST.sha256`, `RELEASE-v1.md`, fixtures/goldens, `store.py`,
  `scoring.py`, `gates.py`, `trim.py`, `tax.py`, `decision.py`, `pipeline.py`,
  frontend (zero frontend changes — read-only API was deemed the minimal
  render channel; any UI panel is a future gate).

## Validation summary

* Suite: **571 passed, 0 failed** (544 baseline + 27 CR-024 proofs).
* Determinism twin-run A==B (fixtures, as_of 2026-08-22): foundation
  `d975a90f045f437b5d9e0f24c452f8144414f36d8d8373132b2ab952e68839e3`,
  decision `0fa722b2b464d62569a07ce242bf2164f0dbb256df67ebc5efcb2273c0f10be7`
  (new pins expected: ENGINE_VERSION is payload-visible under VP-1).
* Scratch-archive `verify()` ok; tamper test F proves corruption ⇒ verify
  errors AND zero fabrication by the history layer.
* VP-1 pin moves: `tests/test_cr022.py` 0.5→0.6 (×3), `tests/test_decision.py`
  prefix 0.5→0.6. No other existing assertions touched; no test weakened; no
  fixture/golden changes.

## Real-data UAT (authority-side, BEFORE closure — F2-I7-A required set)

1. Windows checkout at the CR-024 commit SHA; `/api/v1/health` →
   `0.6.0-phase3`.
2. `GET /api/v1/history/fundamentals/{instrument}?metric=pe_ratio` returns the
   observations accumulated from the authority's real-data archive (CR-022
   activation forward), no run_id supplied.
3. `GET /api/v1/history/g04/{instrument}` shows window/methodology/provenance
   and `eligible` consistent with the accumulated observation count
   (expected: **false** until ≥24 valid observations per metric exist).
4. `GET /api/v1/history/g1/{instrument}` shows the legs' availability states
   consistent with accumulated history (likely unavailable until prior-period
   observations exist).
5. Deterministic replay: same archived inputs → identical medians/legs
   (repeat query, byte-identical JSON).
6. Archive linkage: `archive.verify()` ok; observations' snapshot identities
   match manifest entries.
7. **Proxy retained:** decision payload unchanged vs pre-CR-024 baseline
   (six-state strip, distribution, gates, queue, trim, sizing, tax,
   review cadence) — G-04 must yield NO scoring change.
8. No decision/gate behavior changes vs baseline.

Closure requires this UAT plus authority review of conventions C-1…C-5 and a
separate closure gate. G-04/G1 **activation** is a further separate authority
decision beyond closure.
