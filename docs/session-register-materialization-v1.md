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
| EMM-H2 (manual theme tags) | `themes/themes.yaml` header + `docs/cr023-manual-theme-tags.md` — CLOSED; COMPLETE-BUT-VACANT (DEC-C14-001) |
| EMM-H3 (ACCUMULATE) | `docs/architecture-and-ui-guidelines.md` §11.3 + DEC-EMM-H3-001 — methodology **settled** (sub-state of HOLD); production-blocked on unfrozen inputs U-1…U-6 |
| EMM-F2 (snapshot archive / history) | `docs/cr022-snapshot-archive.md` + `docs/cr024-historical-fundamentals.md` — CLOSED |

## Standing recorded residuals (CR-025 / S5)

- **R-SORT-001** — Decisions-table sorting: **OPEN / NOT IMPLEMENTED** (presentation-only
  requirement over fields Instrument · Bucket · Alloc · Gain/Loss · Final decision ·
  Gate state · Composite · Confidence · Review; future UI/product authority gate; no
  implementation authorized).
- **P-07 run overlay** — evidence limitation retained: **NOT OBSERVABLE / NOT REPLAYABLE**
  (C-4 accepted-as-PASS record; not promoted).
- **G-04** — IMPLEMENTED / REAL-DATA-VERIFIED evidence path / **NOT ACTIVATED**.
- **G1 historical legs** — evidence-only; production gate semantics unchanged.
- **Themes assignments** — absent-by-design; population requires a separate authority
  data-entry act plus a separate exact-worded commit/push gate.

## Next authority action (for F5/F7/C3)

Supply the exact verbatim definitions in any later gate; the sandbox will transcribe them
verbatim into this record (or the authority may dispose of the identifiers: keep / merge /
retire). Until then they remain open session-register items — not requirements.
