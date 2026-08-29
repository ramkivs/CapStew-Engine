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
| EMM-H3 (ACCUMULATE) | `docs/architecture-and-ui-guidelines.md` §11.3 + DEC-EMM-H3-001 — methodology **settled** (sub-state of HOLD); production-blocked on unfrozen inputs U-1…U-6 |
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
