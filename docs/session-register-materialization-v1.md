# Session-Register Materialization v1 (CR-025 / scope S4)

**Created:** 2026-08-28 under **CR-025 / scope S4 (conflict-register item C-7)** —
register-hygiene recording only. This file materializes, in-repo, the *existence* of
session-register identifiers that previously had **no in-repo anchor**. It creates no
requirement, no methodology, and no assignment, and it infers nothing.

## Rule applied (per gate)

The authority gate instructed: use the exact verbatim definitions **supplied by the
authority**; if no verbatim definitions are supplied, record
**"definition not supplied — carried as-is"**. Do not infer or author replacement
definitions.

**No verbatim definitions were supplied by the authority at the CR-025 gate.**

## Register entries

| Identifier | First appearance (session record) | Status |
|---|---|---|
| **EMM-F5** | session register (prior EMM-era authority gates) | definition not supplied — carried as-is |
| **EMM-F7** | session register (prior EMM-era authority gates) | definition not supplied — carried as-is |
| **EMM-C3** | session register (prior EMM-era authority gates) | definition not supplied — carried as-is |

## Cross-reference — register identifiers that DO have in-repo anchors

| Identifier | Anchor |
|---|---|
| EMM-H2 (manual theme tags) | `themes/themes.yaml` header + `docs/cr023-manual-theme-tags.md` — CLOSED; ~~COMPLETE-BUT-VACANT~~ **WP-1 ACTIVATED 2026-08-29** (v2; 9 fixture-holding assignments; 163 real-data unassigned → fallback) — see CR-027 addendum below |
| EMM-H3 (ACCUMULATE) | `docs/architecture-and-ui-guidelines.md` §11.3 + DEC-EMM-H3-001 — methodology **settled** (sub-state of HOLD); ~~production-blocked on unfrozen inputs U-1…U-6~~ **IMPLEMENTED + TESTED** (CR-029/G2, commit `fa80eae…`, 2026-08-30; `app/accumulate.py` + Q-i1 carrier in `ingest`/`lot_engine`/`decision`); `high_threshold: 70` INSTALLED as policy-data (G1, `3d9dd8a…`); **NOT ACTIVATED** (requires separate authority activation gate + declared Quality/Growth conviction inputs); **NOT CERTIFIED** — see "Update — EMM-H3 G1/G2 (2026-08-30)" addendum below |
| EMM-F2 (snapshot archive / history) | `docs/cr022-snapshot-archive.md` + `docs/cr024-historical-fundamentals.md` — CLOSED |

## Standing recorded residuals (CR-025 / S5)

- **R-SORT-001** — Decisions-table sorting: ~~**OPEN / NOT IMPLEMENTED**~~ **CLOSED (CR-026,
  2026-08-29)** — see CR-027 addendum below (presentation-only
  requirement over fields Instrument · Bucket · Alloc · Gain/Loss · Final decision ·
  Gate state · Composite · Confidence · Review; ~~future UI/product authority gate; no
  implementation authorized~~ gate executed: CR-026 implementation + ORV/UAT PASS).
- **P-07 run overlay** — evidence limitation retained: **NOT OBSERVABLE / NOT REPLAYABLE**
  (C-4 accepted-as-PASS record; not promoted).
- **G-04** — IMPLEMENTED / REAL-DATA-VERIFIED evidence path / **NOT ACTIVATED**.
- **G1 historical legs** — evidence-only; production gate semantics unchanged.
- **Themes assignments** — ~~absent-by-design; population requires a separate authority
  data-entry act plus a separate exact-worded commit/push gate~~ **populated 2026-08-29
  under WP-1** (authority tag-pass → gated commit `020f3ba8…`; `document_version 2`,
  9 fixture-holding assignments; 163 real-data holdings unassigned → fallback, authority
  intent) — see CR-027 addendum below.

## Next authority action (for F5/F7/C3)

Supply the exact verbatim definitions in any later gate; the sandbox will transcribe them
verbatim into this record (or the authority may dispose of the identifiers: keep / merge /
retire). Until then they remain open session-register items — not requirements.

## Update — CR-027 (2026-08-29)

Dated, non-destructive addendum recording states completed after this file's CR-025
materialization (originals above preserved via strikethrough):

- **R-SORT-001 — CLOSED.** Implemented under **CR-026** (presentation-only decisions-table
  sorting; `frontend/src/utils/sort.ts` + `DecisionsView`); ORV/UAT **PASS** (S1-A
  service-level, S1-B/S2 authority-executed); commit
  `74a3ebd85aaf67ef3afa0761e23a0f4279e817c5`. No multi-column sorting, no persistence, no
  decision-logic change. Closed, not redesigned.
- **Themes (EMM-H2 / C-14) — WP-1 ACTIVATED (fixture lane).** Authority tag-pass complete:
  `document_version 2`, `effective_from 2026-08-29`, 9 fixture-holding authority
  assignments (`themes/themes.yaml` sha256 `3422577b…`, commit
  `020f3ba870686f109b5dd37e5094acc56ae84fc5`). Real-data 163 holdings remain unassigned →
  sub-sector fallback (authority intent; no manual assignments implied). Provenance (R2):
  document-level `source` = v1 taxonomy lineage; per-assignment `source` = "WP-1 authority
  tag-pass". IMPL ≠ ACTIVATED ≠ CERTIFIED preserved.
- **C-5 (table virtualization) — CLOSED / NON-REQUIRED.** 163-holding real-data rendering
  accepted at C-4 with no observed rendering/performance defect; virtualization not
  currently required; P-15 per-row metrics remain an explicit evidence gap (not
  reconstructed); reopen trigger preserved: holdings > 400 OR measurable rendering/jank in
  a future ORV. R-SORT-001 remains separate and is now implemented/closed (CR-026).
  Stale §12.8 virtualization wording corrected in
  `docs/architecture-and-ui-guidelines.md` under CR-027/S4.
- **S4 UI coverage note R-S4-OBS-1 — CLOSED (Option A).** Tab 01 readout scope accepted
  as-built; document-level `change_id` remains authoritative via `GET /api/v1/themes`.
- **R1/T-R1 residue:** the `themes/themes.yaml:3` header prose ("HOLDINGS-FREE v1…")
  remains byte-preserved in the fenced themes document; correction requires a separately
  gated themes-document action (not a docs CR).

## Update — EMM-H3 G1/G2 (2026-08-30)

Dated, non-destructive addendum recording states completed under the CR-029 /
RD-004…RD-011 authority chain after the CR-027 addendum (originals above preserved
via strikethrough):

- **EMM-H3 (ACCUMULATE) — IMPLEMENTED + TESTED / NOT ACTIVATED / NOT CERTIFIED.**
  Inputs no longer unfrozen: U-1 transport pinned (RD-009 — declared per-holding run
  input, exact fields `conviction_score`, `conviction_score_source`,
  `conviction_score_effective_date`, `conviction_score_version`; RD-010 Q-i1 carrier
  contract); U-2 threshold INSTALLED as policy-data `high_threshold: 70` (RD-004;
  G1, commit `3d9dd8a1a76bf273f3425f23b8f82ed85538c4cc`; read only via policy —
  never hard-coded); U-3 valuation basis/mapping pinned (RD-007 basis C-A
  `pe_premium_vs_subsector` / `pb_premium_vs_subsector`; RD-009 mapping ≤ 1.0;
  RD-010 Q-i3 deterministic BOTH-rule; no MOS; no G-04); U-4…U-6 recorded
  closed/non-required (RD-004-AUTH-001). Implementation (CR-029 election
  IMPLEMENT-UNDER-NAMED-CR): G2 commit `fa80eaeddaa8f31e21df828a7b8fbf211cd79d35`
  — 5 files (`app/accumulate.py` pure evaluator; Q-i1 carrier in `app/ingest.py`,
  `app/lot_engine.py`, `app/decision.py`; `tests/test_g2_accumulate.py` ×20);
  suite 571 → 591 passed / 0 failed; fixture decisions/distribution/composites
  byte-identical to pre-G2 pins; six-state decision enum unchanged; additive
  per-holding `tags` + `accumulate_evidence` only (Q-i2 non-blocking fail-safe
  with full provenance echo).
- **Activation boundary:** fixture corpus yields `tags == []` on all 9 holdings
  (reasons: `conviction_missing` on the sole HOLD, `decision_not_hold` otherwise)
  — the fail-safe working as designed. Neither any repository fixture nor any
  production lane supplies the four conviction carrier fields; no Quality/Growth
  producer lane exists in-repo. Production activation requires (a) an actual
  declared-conviction producer/input lane AND (b) a separate exact-worded
  authority activation gate. Implementation existence confers no activation.
- **VP-1 version-constant question — OPEN (explicitly unresolved; no change made
  or proposed):** whether G1's policy-key addition and G2's additive payload
  surface (`tags`, `accumulate_evidence`) implicate `policy_version` /
  `ENGINE_VERSION` bumps. Current pins retained: `ENGINE_VERSION 0.6.0-phase3`,
  `policy_version 1`.
- **Policy header tension:** remains parked, unchanged — G1's `high_threshold: 70`
  introduction versus the existing policy header wording is not corrected here or
  anywhere without a separately gated disposition.
- **Docs refreshed under the same reconciliation package:** EMM-H3 rows in
  `README.md` (standing open register) and this file (cross-reference table) by
  strikethrough-and-supersede; `docs/architecture-and-ui-guidelines.md:126`
  "GAP — never implemented" superseded; `README.md` epochs table gains the
  `fa80eae` current row (591 collected); suite-count lines updated 571 → 591.
