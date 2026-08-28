# Design & Governance Artifacts

The authoritative documentation for Capital Steward Engine. Read order:

| # | Document | Role |
|---|---|---|
| 1 | `methodology-freeze-v1.md` | **Authority.** Frozen decision methodology: G0–G4 gate precedence, confidence equation, missing-data eligibility, trim optimisation (TRIM-S/V), hysteresis, determinism, decision semantics (HOLD/WATCH/TRIM/HARVEST/EXIT), and the signed D-01…D-15 policy. `policy/policy.yaml` is the operational serialization of this. |
| 2 | `architecture-and-ui-guidelines.md` | Sections 11–12: system architecture (ADRs, modules, API contract, DecisionPayload v1 schema) and UI/UX design guidelines (tokens, screen specs, component tree). |
| 3 | `profit-booking-engine-analysis.md` | Historical findings/gaps/implementation-plan analysis produced during the review cycle (superseded where the freeze differs). |
| 4 | `profit-booking-engine-ui-prototype.html` | Clickable single-file UI prototype — the visual source of truth for the React frontend. Open in any browser; self-contained (no network). |

### Related governance & rule records (added CR-020, 2026-08-27)

| Document | Role |
|---|---|
| `v1.1-authority-decisions-v1.md` | Frozen authority-decision record for the v1.1 cycle (V1.1-A). |
| `version-provenance-rule-vp1.md` | VP-1 version-bump/provenance rule binding future engine-mutating CRs (E2E-017-PD R4). |
| `backtest-methodology-addendum-v1.md` | CR-015 backtest methodology addendum (signed-provisional). |
| `cr006-canonical-instrument-join.md` · `cr012a-weight-only-sensitivity.md` · `cr012b-g2-sensitivity-characterization.md` | Named-CR specification / closure records. |
| `cr022-snapshot-archive.md` | CR-022 (EMM-F2) snapshot archiver: content-addressed input evidence store, integrity model, dual-timestamp semantics, G-04/G-05 status and real-data UAT protocol. |
| `cr023-manual-theme-tags.md` | CR-023 (EMM-H2/G-14) manual theme-tag layer: signed-off taxonomy, precedence/fallback/threshold dispositions, document format, replay/provenance pattern, real-data UAT protocol. |
| `cr024-historical-fundamentals.md` | CR-024 (EMM-F2) date-indexed historical fundamentals store/query + G-04 own-history median + G1 history legs: frozen methodology lineage, five surfaced implementation conventions (C-1…C-5), activation fences, replay/provenance pattern, real-data UAT protocol. |

## Authority chain

```
methodology-freeze-v1.md   (frozen)
        ↓
policy.yaml                (D-01…D-15, signed)
        ↓
DecisionPayload v1         (frontend/src/types.ts = serialization, app/decision.py = authority)
        ↓
React renderer             (pure — never computes a decision, score, or tax)
```

The browser-purity rule (ADR-1a) applies to tax as well as decisions: the UI renders
authoritative backend numbers and never calculates them.
