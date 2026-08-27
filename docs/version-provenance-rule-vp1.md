# VP-1 — Version Provenance Rule

**Status:** ESTABLISHED (record-level) — E2E-017-PD R4, codified under CR-020 (2026-08-27).
**Authority basis:** E2E-017-PD disposition R4. Binding on all CRs authorized after the
E2E-017-PD countersignature. **Scope is future-only:** no epoch at or before
`arena/01a033db-capstew-engine @ e473417` is retroactively re-versioned.

## Problem addressed (recorded limitation P2)

The version constants are static across every epoch so far:

| Constant | Location | Value (pinned, unchanged by this rule) |
|---|---|---|
| `ENGINE_VERSION` | `app/config.py` | `0.3.1-phase3` |
| `NORMALIZATION_VERSION` | `app/config.py` | `1.0` |
| `CALCULATION_VERSION` | `app/config.py` | `2.1` |
| `policy_version` | `policy/policy.yaml` | `1` |

Payloads from materially different engine builds (e.g. pre- vs post-CR-006 remediation)
are therefore indistinguishable by version string alone; provenance has relied on
out-of-band git SHA + test-ledger evidence.

## Rule (binding on future engine-mutating CRs)

1. **Any named CR that mutates decision-path behavior must change `ENGINE_VERSION` in the
   same commit set.**
2. If the CR changes scoring math, thresholds, hurdles, or trim/confidence numerics, it
   must **additionally change `CALCULATION_VERSION`**.
3. If the CR changes normalization/identity semantics (`app/normalize.py`,
   `app/symbols.py`), it must change **`NORMALIZATION_VERSION`**.
4. If the CR changes `policy/policy.yaml` semantics, it must bump **`policy_version`**
   under the existing governance sign-off discipline. **Comment-only policy edits are
   exempt** (e.g. CR-020's D-04 comment correction) — no bump for zero-semantic-change
   edits.
5. The version change is part of the CR's **closure evidence**; a CR that mutates covered
   behavior without the corresponding bump has incomplete closure evidence and is not
   closable.

Comment-only source edits (no bytecode-relevant change) are exempt from rules 1–3.

## Mapping table

| Change area (files) | Required bump |
|---|---|
| `decision.py`, `gates.py`, `hysteresis.py`, `trim.py`, `behavior.py`, `pipeline.py`, `lot_engine.py`, `reconcile.py` (behavior-affecting) | `ENGINE_VERSION` |
| `scoring.py`, `confidence.py` numeric/sub-score/threshold logic | `ENGINE_VERSION` + `CALCULATION_VERSION` |
| `normalize.py`, `symbols.py` (identity/normalization semantics) | `NORMALIZATION_VERSION` |
| Payload shape/semantics | per existing schema discipline (CR-001 validator) + `ENGINE_VERSION` if behavior-visible |
| `policy/policy.yaml` semantics | `policy_version` (+ governance sign-off) |
| Comments/docs/tests only | none |

## Notes

- First application: the next engine-mutating named CR. Until then the pinned values
  above remain correct for every existing epoch.
- This rule does not create or imply any certification level; certification remains
  governed by the release-gate process (v1.0.0 remains the only CERTIFIED epoch;
  v1.1.0 remains RELEASE-DOCUMENTED MILESTONE per E2E-017-PD R1-B).
