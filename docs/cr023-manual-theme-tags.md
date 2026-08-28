# CR-023 — Manual theme-tag layer (EMM-H2 / G-14)

**Status:** ~~IMPLEMENTED + FIXTURE-VALIDATED — closure pending authority-side
real-data UAT.~~ **CLOSED (2026-08-28).** Real-data Windows UAT PASS accepted;
committed `9e3bd12a…`; EMM-H2 CLOSED (disposition A). Themes capability =
**COMPLETE-BUT-VACANT** (DEC-C14-001): taxonomy signed off; assignments absent-by-design
pending the separate authority tag-pass/data-entry act. Original point-in-time header
preserved via strikethrough (CR-025/S2 convention).
**Authority chain:** EMM-H2 discovery → H2-D1…D10 dispositions (all ACCEPTED)
→ CR-023 taxonomy sign-off (HARDCHECKPOINT, 2026-08-28) → implementation gate.
**Branch:** `arena/01a033db-capstew-engine`.

## What CR-023 builds

A small, **authority-controlled** manual factor-theme layer for the **theme
concentration surface only**:

```
themes/themes.yaml   (schema_version 1 · document_version 1 · effective_from
                      2026-08-28 · 6 signed-off taxonomy themes · assignments [])
```

* **Taxonomy (SIGNED OFF by authority, 2026-08-28):** `RATE_FIN` rate-sensitive
  financials · `PSU_GOV` PSU/government-linked · `CAPEX_INFRA` capex/
  infrastructure · `CONSUMPTION` · `PHARMA_HEALTH` · `IT_EXPORT`. Boundary
  rules per theme are in the document. `microcap-momentum` was deliberately
  declined for v1 (bucket axis, not a correlation factor). No commodity theme
  in v1.
* **H2-D2-A precedence:** manual theme is the primary grouping **for theme
  concentration only**; `sub_sector` remains a secondary classification and is
  **untouched globally** (`_is_financial()`, fundamentals, peer premiums).
* **H2-D3-A fallback:** an unmapped holding groups by `sub_sector` and is
  honestly labelled `fallback_sub_sector` (never re-labelled manual).
* **H2-D4-A threshold:** `>20%` exactly — now authority-confirmed. No 15%, no
  per-theme bands (`app/decision.py` `THEME_BREACH_THRESHOLD_PCT = 20.0`;
  exactly 20% is NOT a breach).
* **H2-D5-A ownership:** the document is standalone, not in `policy.yaml`,
  not user-editable (no API/ UI mutation surface; `GET /api/v1/themes` is
  read-only).
* **H2-D6-A effective dating / replay:** document + assignments are
  effective-dated; every run captures the document's exact bytes into the
  CR-022 archive (`themes_document` slot, sha256 recorded in the ingest
  manifest and as `themes_sha256` in `provenance.archive`), so the
  classification input used by any historical run is recoverable.
* **H2-D7 provenance:** assignments require instrument/theme/owner/source/
  effective_from/version/change_id (+ optional rationale); duplicates and
  unknown themes are rejected (strict validation, no silent repair —
  `app/themes.py`).
* **H2-D8 cardinality:** exactly one manual theme per holding per document
  version.
* **H2-D9 rename:** renames require a new document version with a
  `rename_history` entry; historical payloads/archives are never re-labelled
  (immutably stored).
* **H2-D10 effect:** breach is informational/rebalance evidence only — zero
  downstream consumers (no decision/gate/queue/sizing/tax/cadence effect).

## As-built mechanics

- `app/themes.py` — deterministic loader, strict validator, pure resolver
  (same document bytes + instrument + as_of ⇒ same result; document and
  assignment effective dates honoured; missing document ⇒ documented
  empty/fallback semantics).
- `app/pipeline.py` — per-position `theme` + `theme_source` resolution and
  CR-022-style archive capture of the document bytes inside `run_foundation`.
- `app/decision.py` — concentration groups by position `theme` (legacy
  foundations fall back to the historical sub_sector derivation); rows carry
  additive `source` (`manual` | `fallback_sub_sector`).
- `app/schema.py` — additive optional validation only.
- UI — Decisions tile labels rows `manual theme (G-14)` / `sub-sector
  fallback`; Inputs screen shows a read-only "Theme mapping" readout
  (version, effective_from, sha256, taxonomy, assignments). No editor.

## VP-1

`ENGINE_VERSION 0.4.0-phase3 → 0.5.0-phase3` (payload-visible: per-position
theme fields, `themes_sha256`, concentration row `source`, grouping switch).
`CALCULATION_VERSION 2.1`, `NORMALIZATION_VERSION 1.0`, `policy_version 1`
unchanged — no scoring/decision mathematics changed.

## Functional invariants (fixture-proven, tests/test_cr023.py 16–20)

With the shipped v1 document (zero assignments) the concentration output is
**byte-identical** to the pre-CR-023 sub_sector grouping (pinned row list in
the suite). With a fully-tagged synthetic document on identical inputs, every
holding's decision, composite, confidence, subscores (incl. quality_drift —
`_is_financial` intact), stage-1 gates, trim, alloc, tax_status, tax summary,
tax sequencing, and next_review_date are **unchanged**; the decision
distribution and six-state enum are unchanged. The ONLY functional change is
the theme-concentration grouping (manual where assigned, fallback elsewhere).

## Real-data UAT protocol (authority Windows environment, before closure)

1. `GET /api/v1/themes` → taxonomy v1 listed, document sha256 =
   sha256(themes.yaml bytes), `assignments: []`.
2. `POST /run` with the real three-file export → every theme-concentration
   row shows `source: "fallback_sub_sector"`, values identical to the
   pre-CR-023 run for the same inputs (grouping still `sub_sector`); decisions
   and six-state distribution unchanged; payload `provenance.archive` shows
   `themes_sha256` matching the document hash; manifest carries the
   `themes_document` record (`as_of_source: "authority_document"`,
   declared 2026-08-28).
3. Optional authority tag pass (new document version with real assignments)
   is a SEPARATE authority act — the engine will group per it deterministically
   and archive it, but no tag assignment is bundled with CR-023.
4. Privacy firewall preserved: no real exports enter Git; `data/` stays local.
