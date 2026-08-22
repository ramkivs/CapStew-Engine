# Design & Governance Artifacts

The authoritative documentation for Capital Steward Engine. Read order:

| # | Document | Role |
|---|---|---|
| 1 | `methodology-freeze-v1.md` | **Authority.** Frozen decision methodology: G0–G4 gate precedence, confidence equation, missing-data eligibility, trim optimisation (TRIM-S/V), hysteresis, determinism, decision semantics (HOLD/WATCH/TRIM/HARVEST/EXIT), and the signed D-01…D-15 policy. `policy/policy.yaml` is the operational serialization of this. |
| 2 | `architecture-and-ui-guidelines.md` | Sections 11–12: system architecture (ADRs, modules, API contract, DecisionPayload v1 schema) and UI/UX design guidelines (tokens, screen specs, component tree). |
| 3 | `profit-booking-engine-analysis.md` | Historical findings/gaps/implementation-plan analysis produced during the review cycle (superseded where the freeze differs). |
| 4 | `profit-booking-engine-ui-prototype.html` | Clickable single-file UI prototype — the visual source of truth for the React frontend. Open in any browser; self-contained (no network). |

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
