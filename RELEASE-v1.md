# Capital Steward Engine — Release v1.0.0

**Release date:** 2026-08-22 · **Baseline:** tagged `v1.0.0` in git · **Status:** v1 product implementation COMPLETE

---

## Release scope

Capital Steward Engine is a portfolio decision system that stewards capital and
positions — **HOLD / WATCH / TRIM / HARVEST / EXIT** with **ACCUMULATE** as a secondary
tag. Profit booking is one of its actions, not its identity.

```
CSV parsers → normalize → reconcile (G0) → per-lot FIFO → FoundationPayload
   ↓
G0 → G1 → G2 → G3 → G4 (composite, eligibility-capped, hysteresis-gated)
   ↓
confidence → TRIM-S / TRIM-V → reason_tree + why_now → DecisionPayload
   ↓
React renderer (pure — never computes a decision, score, or tax number)
```

## Frozen baseline

| Component | Frozen at |
|---|---|
| Methodology (G0–G4 precedence, confidence eq., eligibility, trim, hysteresis, determinism) | `methodology-freeze-v1.md` |
| Policy defaults D-01…D-15 | `policy/policy.yaml` v1 |
| DecisionPayload contract | v1 (`frontend/src/types.ts` = serialization; `app/decision.py` = authority) |
| Decision semantics | HOLD / WATCH / TRIM / HARVEST / EXIT + ACCUMULATE tag |
| Domain separation | TaxLedger (`tax.py`) · RunHistory (`store.py`) · DecisionEngine (`decision.py`) |
| Browser-purity rule | ADR-1a — no decision/score/tax computation client-side |
| Golden decision fixtures | GOLDEN-G2-TRIM-S-SALASAR · GOLDEN-G1-EXIT-ASHOKA · GOLDEN-G3-HOLD-LT |
| Golden tax fixtures | LTCG · STCG · EXEMPTION · S74-SET-OFF · CROSS-FY |

## Release/Operational Readiness Gate — results (executed 2026-08-22)

| Gate | Check | Result |
|---|---|---|
| R-01 | Clean checkout | ✓ |
| R-02 | Backend deps (`requirements.txt`) + frontend deps (`npm ci` lockfile) | ✓ |
| R-03 | Fixture regeneration byte-identical (deterministic) | ✓ |
| R-04 | 126 backend tests, fresh venv | ✓ |
| R-05 | `tsc --noEmit` clean + Vite production build | ✓ |
| R-06 | API `/health` on fresh process | ✓ |
| R-07 | Demo acceptance (`run-sample`) | ✓ |
| R-08 | UI acceptance — golden trilogy exact | ✓ |
| R-09 | Persistence: run → restart → history → diff | ✓ |
| R-10 | Release artifact — this file + `MANIFEST.sha256` + git tag `v1.0.0` | ✓ |

**Result: 10/10 PASS.** Reproduce with `bash scripts/release_check.sh` (R-01…R-09).

## Verification totals

- 126 backend tests (unit · gates · scoring · confidence · trim · hysteresis · decision · audit · policy · tax · diff · API)
- Frontend TypeScript strict-mode clean · production build succeeds
- Determinism: same inputs + policy + engine version ⇒ same `content_hash` (cross-process proven)
- Tax subsystem: FIFO sell matching, S.74 set-off, ₹1.25L exemption, 8-year carry-forward/lapse

## Deferred to v1.1+ (deliberately out of v1)

- Runtime schema validation of DecisionPayload (types.ts is compile-time only)
- Live market data / NSE / Screener.in integration
- Authentication & multi-user support
- Packaging / deployment beyond local single-user
- Richer operational UX
- Additional data sources: own-5yr valuation median, quality score time-series,
  watchlist opportunity scores, relative strength vs index, realized-gains archive

## Change discipline

v1 is frozen. Any further change enters as a **named change request** against this
baseline; the golden decision + tax fixtures are permanent regression fixtures — if a
future change alters any golden result without an explicit methodology/policy change,
the change is broken.
