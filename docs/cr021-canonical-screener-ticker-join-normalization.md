# CAPITAL STEWARD ENGINE
# CR-021 — Canonical Screener Ticker Join Normalization

**Status:** PREPARATION AUTHORIZED · IMPLEMENTATION NOT AUTHORIZED  
**CR-020:** CLOSED  
**Scope:** Governance/implementation preparation only  

---

## 1. Authority basis

Authority authorized preparation of this named CR only.

This artifact does **not** authorize:

- implementation;
- implementation tests;
- changes to code, configuration, policy, CSVs, fixtures, or schemas;
- activation;
- certification;
- commit;
- push.

A separate exact-worded implementation gate is required before any runtime or test
changes occur.

---

## 2. Confirmed finding

CR-020 correctly makes the resolver return a normalized canonical ticker. The
subsequent screener dictionary in `app/pipeline.py` still uses the raw parsed
screener ticker:

```python
screener_by_ticker = {s["ticker"]: s for s in screener_rows}
```

The resulting latent defect is:

```text
normalized resolver identity
        ↓
raw screener dictionary key
        ↓
downstream join failure
```

A resolver can therefore return `INFY` while a raw screener key such as `infy` or
`I N F Y` remains inaccessible through the later `get("INFY")` lookup.

No currently checked-in fixture holding is affected. The defect is nevertheless
confirmed by read-only source and in-memory variant checks.

---

## 3. Proposed correction scope

If separately authorized for implementation, CR-021 would align the downstream
screener dictionary keys with the existing `normalize_ticker()` contract.

The intended correction is limited to the downstream screener index construction
and must preserve the existing canonical identity rules.

The correction must preserve:

- static company-name mappings;
- controlled aliases;
- normalized company-name resolution;
- explicit-ticker resolution;
- CR-020 canonical ticker resolution;
- ambiguity handling;
- fail-closed behavior;
- exchange-qualified tickers as distinct identities;
- genuine missing-screener partial-data behavior.

---

## 4. Explicit exclusions

CR-021 does not include:

- reopening or modifying CR-020;
- adding individual ticker mappings;
- bare-ticker versus exchange-qualified equivalence;
- AGI Greenpac missing-data handling;
- Stage 2 weight changes;
- scoring methodology changes;
- policy changes;
- CSV or source-data correction;
- schema redesign;
- unrelated symbol cleanup;
- activation;
- certification;
- commit;
- push.

---

## 5. Likely implementation surface

The future implementation surface is expected to be:

- `app/pipeline.py` — downstream `screener_by_ticker` construction;
- existing `normalize_ticker()` in `app/symbols.py` — reuse only, unless a later
  exact implementation gate states otherwise.

`app/symbols.py::resolve_instrument()` and CR-020 behavior must not be reopened or
changed under this CR.

No implementation change is made by this preparation artifact.

---

## 6. Minimum future regression scope

A later implementation gate would need to authorize the required tests for:

1. lowercase screener ticker normalization;
2. internal-whitespace ticker normalization;
3. boundary-whitespace behavior;
4. same-format exchange-qualified ticker joining;
5. bare-versus-qualified mismatch remaining unresolved;
6. existing display-name resolution;
7. existing explicit-ticker resolution;
8. CR-020 canonical ticker resolution;
9. genuinely missing screener rows remaining on the partial-data path;
10. ambiguity and fail-closed behavior remaining intact.

These tests are specified here only. No tests are added by CR-021 preparation.

---

## 7. Expected behavior if later implemented

For equivalent canonical ticker representations supported by the existing
normalizer, the resolver output and downstream screener lookup key would agree.

For example:

```text
resolver output:       INFY
normalized raw key:    INFY
result:                screener join succeeds
```

Exchange-qualified identity remains distinct:

```text
INFY     ≠ INFY.NS
```

A genuinely absent screener row continues to produce the existing partial-data
behavior. No Stage 2 methodology or weight changes are implied.

---

## 8. Governance sequence

```text
CR-021 preparation
    → separate exact-worded implementation authorization
    → implementation
    → separate testing/verification gate as required
    → separate activation authority, if applicable
    → separate certification authority, if applicable
    → separate commit/push gate
```

Preparation permission must not be treated as implementation permission.

---

## 9. Current gate state

```text
CR-021 preparation       = AUTHORIZED / RECORDED
CR-021 implementation    = NOT AUTHORIZED
CR-021 testing           = NOT AUTHORIZED
CR-021 activation        = NOT AUTHORIZED
CR-021 certification     = NOT AUTHORIZED
CR-021 commit/push       = NOT AUTHORIZED
```

CR-020 remains closed.

No code, configuration, policy, CSV, fixture, schema, or test file was modified by
this preparation. No activation, certification, commit, or push occurred.
