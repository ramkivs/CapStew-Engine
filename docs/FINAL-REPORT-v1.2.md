# Capital Steward Engine — Final Report: Reliability Corrections for Local Personal Use

> **Rebrand note (2026-11-03):** the application is now branded **CapitalCompass**.
> This is a historical artifact produced under the former name *Capital Steward Engine*;
> the original text is preserved verbatim below for audit. The repository identifier
> remains `ramkivs/CapStew-Engine`.

**Repository:** `ramkivs/CapStew-Engine`
**Branch:** `arena/fed5107a-capstew-engine` (base `ffdf9cba`)
**Commits:** `58e36e5` (reliability corrections) · `e7ba3ea` (fixture date-range fix) · `7ff5c93`, `96299d0` (report) · `4389086` (Windows verification harness) — all pushed
**Companion:** [`docs/WINDOWS-VERIFICATION.md`](WINDOWS-VERIFICATION.md) — the PowerShell harness, its evidence layout, and the residual browser checks
**Scope:** dependable **personal, single-user, locally-hosted Windows** application.
No multi-tenant, SaaS, cloud, orchestration, or governance machinery was introduced.

---

## A. Initial State

Verified independently against the authoritative repository at `ffdf9cba`, not taken
from the prior assessment.

| Property | Observed at baseline |
|---|---|
| Backend tests | **450 passed** (259 of them the CR-012A/B parametrized sensitivity matrix) |
| Frontend tests | **0** — no test runner configured at all |
| `tsc --noEmit` | clean |
| `scripts/release_check.sh` | 9 checks, **9/9 passed** |
| `MANIFEST.sha256` | 70 entries, **30 failing**, **24 tracked files unlisted** (incl. `app/schema.py`, `app/symbols.py`) |
| `npm audit` | **2 high** (`vite` 8.2.x, `source-map-js`) |
| Engine version | `0.3.1-phase3`, while Git carries tags `v1.0.0` / `v1.1.0` |
| Unmerged branches | `arena/01a052a5` (542 tests), `arena/01a033db` (591 tests) — neither had a PR |

### Confirmed defects at baseline

| ID | Severity | Defect |
|---|---|---|
| D-01 | Critical | `POST /ingest` filename handling allowed **arbitrary file write** outside the upload directory (`../../` traversal accepted, HTTP 200) |
| D-02 | Critical | `PUT /policy` **overwrote the signed shipped policy** (`policy/policy.yaml`), destroying the frozen D-01…D-15 baseline; no key allowlist |
| D-03 | High | `content_hash` included **filesystem mtimes** → three runs of the same content produced three different hashes |
| D-04 | High | Run store used `INSERT OR REPLACE` — a repeated `run_id` silently **rewrote history**, breaking the append-only ADR-4 contract |
| D-05 | High | Fixture generator wrote CRLF on Windows → committed CSVs not reproducible; `pytest` dirtied the working tree |
| D-06 | High | Hysteresis N=2 confirmation state was **not persisted** — lost on restart |
| D-07 | High | A G0-blocked `NO-DECISION` holding omits `alloc_pct`, `gain_pct`, `lots`, `behavioral`, `data_completeness`; the UI read all five unconditionally → **one inconsistent CSV blanked the entire Decisions screen** |
| D-08 | High | `bands.*` and `review_cadence.*` declared in policy but **read by nothing** — editing them changed no behaviour |
| D-09 | Medium | Weight validation required only "sum > 0", so uniform inflation silently rescaled every score (SALASAR 65.2 → 56.8) |
| D-10 | Medium | Six handlers swallowed errors with empty `catch {}` — a failed call looked like empty data |
| D-11 | Medium | `MANIFEST.sha256` failing and incomplete (see above) |
| D-12 | Medium | Fixture generator compared `DD-MM-YYYY` **strings** with `min()`/`max()` → reversed First/Last Date, wrong holding period |
| D-13 | Medium | README claimed 126 backend tests (actual 450); `--host 0.0.0.0` documented as the run command |
| D-14 | Low | No Windows startup script; `WeightsView` hint said "must sum > 0"; `@types/react` 19 against React 18 |

---

## B. Corrections Implemented

All in commits `58e36e5` and `e7ba3ea`.

### Security

| ID | Correction | Files |
|---|---|---|
| FIX-01 | `_safe_dest()` **rejects** any upload filename containing a path separator or a `..` component (HTTP 400) rather than silently renaming it. Renaming was secure but wrong: `../../x.csv` became `x.csv` and returned 200. `Path.is_relative_to()` retained as defence in depth. | `app/main.py` |
| FIX-02 | `PUT /policy` writes to `data/policy.yaml` (user overlay) and never touches the signed shipped `policy/policy.yaml`. Commits validated against a key **allowlist** (unknown key → 422), weights must total **100**, band boundaries must be contiguous and ascending. Shipped file backed up to `data/backups/` before any write. Added `POST /policy/reset`. | `app/policy.py`, `app/config.py`, `app/main.py` |
| FIX-03 | Vite binds **127.0.0.1** by default. Previously `0.0.0.0`, which exposed the UI — and the `/api` proxy behind it — to every machine on the network. `--host` still overrides it explicitly. | `frontend/vite.config.ts` |
| FIX-04 | Uniform error envelope `{"error":{code,severity,message,details}}` with 7 codes; `?fy=` validated against `^\d{4}-\d{2}$` (404 + `available_fy`); `run_id=` honoured on `/holdings`; no silent 500s with bare tracebacks. | `app/main.py` |

### Determinism

| ID | Correction | Files |
|---|---|---|
| FIX-05 | mtime removed from the hashed payload. **Verified:** two copies of identical content with 2019 vs 2031 mtimes both hash to `cef1541f2fc0d5f3a80f417df5249759e87f90ea87fd73624fd575504992b317`. Baseline produced three distinct hashes. | `app/pipeline.py` |
| FIX-06 | `resolve_data_as_of()` drives staleness explicitly; `/run` and `/ingest` accept `as_of` / `data_as_of_*`. Thresholds: valuation 3 days, ledger 7 days. **Verified:** `data_as_of=2026-08-17` vs `as_of=2026-08-22` marks portfolio+screener stale, ledger not. | `app/pipeline.py`, `app/main.py` |
| FIX-07 | Generator writes with `lineterminator="\n"`. Regeneration now reproduces the committed CSVs **byte-for-byte** and `pytest` no longer dirties them. | `fixtures/generate_fixtures.py` |
| FIX-08 | Fixture date range: converted `DD-MM-YYYY` strings to `date` **before** `min()`/`max()`. Salasar's holding period was 112, correct value 121. | `fixtures/generate_fixtures.py`, `fixtures/portfolio.csv` |

Scoring methodology was **not** changed. `Hysteresis.transition()` thresholds (31/28/56/52/76/72) remain hardcoded — Freeze §6 pins those exact values and the enter/exit asymmetry is engine contract.

### Data integrity & persistence

| ID | Correction | Files |
|---|---|---|
| FIX-09 | Plain `INSERT`; a duplicate `run_id` raises `RunStoreError` instead of `INSERT OR REPLACE` quietly rewriting history. | `app/store.py` |
| FIX-10 | Hysteresis `previous_run.pending` carried in the persisted payload; `store.previous_holdings()` reads it back. Survives restart. | `app/hysteresis.py`, `app/decision.py`, `app/store.py` |

### Configuration consistency

| ID | Correction | Files |
|---|---|---|
| FIX-11 | `bands.*` wired into `band_of()`; `review_cadence.*` wired into `_review_date()`; `compute_penalties()` reads policy. These were declared and read by nothing. | `app/scoring.py`, `app/confidence.py`, `app/decision.py` |
| FIX-12 | The 8 keys that remain inert are tagged `[NOT CONSUMED]` inline with the reason. `tests/test_policy_keys.py` recomputes which keys `app/` actually reads and **fails if the tags drift** — so the documentation cannot quietly become a lie. | `policy/policy.yaml`, `tests/test_policy_keys.py` |

The 8 inert keys: `effective_from` (datestamp), `quality_drop_pts`, `pledge_qoq_pp` (both need QoQ series absent from the inputs), `rerating_strong_pct`, `rerating_critical_pct` (no re-rating feature), `participation_adv_pct` (needs 20d ADV), `hurdle_nifty_pct`, `hurdle_liquid_pct` (documented, not applied).

They were **documented rather than deleted**: each mirrors a signed D-05…D-14 decision in the Methodology Freeze, so removing them would make `policy/policy.yaml` a worse serialization of that policy. The brief's requirement — do not retain *misleading* configuration — is met by making the inertness explicit and self-verifying.

### API & UI

| ID | Correction | Files |
|---|---|---|
| FIX-13 | `/lots/{name}` accepts a ticker as well as an instrument name; `/runs` adds `holdings_count` + `gates_fired`; `/health` adds `data_as_of` + `last_run_id`. | `app/main.py` |
| FIX-14 | Errors surfaced instead of swallowed: `ApiRequestError` (carries `code` and `details`), `isNotFound()`, `errMessage()`, `ENGINE_UNREACHABLE` wired into all six handlers. | `frontend/src/api/client.ts`, `frontend/src/App.tsx` |
| FIX-15 | **D-07 crash fixed.** The five absent fields are optional in `types.ts`, so the compiler now forces every read site to guard. `tsc` flagged 11 unguarded reads across `DecisionsView` and `HoldingDetail`; all are guarded. | `frontend/src/types.ts`, `DecisionsView.tsx`, `HoldingDetail.tsx` |
| FIX-16 | `WeightsView` states the real rule ("must equal 100") and blocks commit otherwise. | `frontend/src/components/WeightsView.tsx` |
| FIX-17 | `@types/react` 19.2.18 → 18.3.x to match React 18.3.1. | `frontend/package.json` |
| FIX-18 | `npm audit`: **0 vulnerabilities** (was 2 high). `vite` → 8.3.5, `source-map-js` → 1.2.2. Note: the first attempt pinned `vitest@3`, which *introduced* 2 critical advisories (`tinypool` prototype pollution); `vitest@5.0.5` resolved it. | `frontend/package.json`, `package-lock.json` |

### Release & tooling

| ID | Correction | Files |
|---|---|---|
| FIX-19 | `MANIFEST.sha256` re-baselined: **110 entries, 0 failures, 0 unlisted** (was 70/30 failing/24 unlisted). `scripts/make_manifest.sh` regenerates it over the full tracked set. | `MANIFEST.sha256`, `scripts/make_manifest.sh` |
| FIX-20 | `release_check.sh` gained 4 checks and no longer aborts half-finished. `; check "..." $?` ran under `set -e`, so the **first failing check exited the script silently** — the gate could report "9/9" while never having run the later stages. Now uses the `if` idiom. | `scripts/release_check.sh` |
| FIX-21 | `ENGINE_VERSION` `0.3.1-phase3` → `1.2.0`, matching the `v1.0.0`/`v1.1.0` tags. `test_decision.py` now pins the constant instead of a stale `startswith("0.3")`. | `app/config.py`, `tests/test_decision.py` |
| FIX-22 | `scripts/start.bat` + `stop.bat`: loopback-only startup, first-run venv/`npm install`, health-gated browser launch, port-conflict detection. | `scripts/start.bat`, `scripts/stop.bat` |
| FIX-23 | README corrected: real test counts, loopback run commands, Windows quick-start. | `README.md` |
| FIX-24 | `scripts/verify-windows.ps1` — 30-check local verification harness: repo/branch/commit/tree state, prerequisites, port availability, loopback startup, poll-until-ready, health, app shell, `/api` proxy, golden trilogy, restart with previous-run recovery and diff, SHA-256 preservation of `data\`, optional `start.bat`/`stop.bat` exercise. Timestamped evidence directory; stops only the PIDs it started. | `scripts/verify-windows.ps1` |
| FIX-25 | Four of the six §F manual UI items automated with the existing vitest/jsdom setup — no new framework. Both files proven to fail against the pre-fix code. Frontend suite 26 → 38. | `frontend/src/components/WeightsView.test.tsx`, `HoldingDetail.test.tsx` |

---

## C. Branch Reconciliation

Neither branch was merged wholesale. `git merge-tree` confirmed each merges clean
into `main` individually but produces **7 conflicts** together; CR-020…026 are
implemented twice with different meanings across the two branches. Only CR-026 is
genuinely the same feature.

### Reused (correct and compatible — taken as-is)

| Item | Source | Evidence |
|---|---|---|
| **CR-025 hysteresis persistence** | `arena/01a052a5` @ `ba9834b` | Reviewed line by line: clean, validated, backwards-compatible. Applied verbatim plus its **34-test suite** (`tests/test_hysteresis_persistence.py`). Not reimplemented. |
| **CR-026 sorting + payload export** | `arena/01a052a5` | `utils/sort.ts`, `utils/exportDecisions.ts` — presentation-only, ADR-1a compliant (no locale collation, sorts a copy, exports the authoritative payload verbatim). Wired into `DecisionsView`. |
| **CR-024 G4 re-entry after EXIT** | `arena/01a052a5` @ `56893e4` | A genuine 1-line defect fix. Integrated with its 4 tests (renamed `test_exit_reentry.py` to avoid a CR-number collision). |

### Integrated selectively

| Item | Note |
|---|---|
| `DecisionsView` `NO-DECISION` guards | The branch bundled these with CR-022. Only the guards were taken — the rest of its CR-022 assumes a payload shape `main` does not emit. |

### Intentionally excluded

| Item | Reason |
|---|---|
| `app/themes.py`, `themes.yaml` | New feature, not a correction. Out of scope. |
| `app/archive.py`, `app/history.py` | Snapshot archiver — enterprise-flavoured; the existing run store already persists history. |
| `app/accumulate.py` (EMM-H3 ACCUMULATE) | Implemented and tested on `01a033db` but **not activated** there either. Adds a sixth decision state — a methodology change, explicitly not authorised. |
| Historical fundamentals, canonical instrument join, CR-020/021/023 identity resolution | Duplicate, conflicting implementations of concepts `main` already handles. |

No duplicate implementation was created; no change-register governance was added.

---

## D. Testing Results

Every figure below was **actually executed** in this session. Nothing is projected.

| Suite | Command | Result |
|---|---|---|
| Backend | `pytest -q` | **557 passed, 0 failed, 0 skipped** (5.7s) |
| Backend, fresh venv + clean checkout | inside `release_check.sh` | **557 passed** |
| Frontend unit | `npx vitest run` | **38 passed** (6 files) |
| Frontend types | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | clean, 193 kB (59.6 kB gzip) |
| Dependency audit | `npm audit` | **0 vulnerabilities** |
| Release gate | `bash scripts/release_check.sh` | **13 passed, 0 failed** |

Backend suite composition (557): `test_cr012b` 217 · `test_cr012a` 42 ·
`test_hysteresis_persistence` 34 · `test_schema` 27 · `test_audit` 19 ·
`test_api_contract` 19 · `test_security` 17 · `test_cr019` 15 ·
`test_determinism_repro` 14 · `test_scoring` 13 · `test_policy_keys` 12 ·
`test_tax` 11 · `test_policy` 11 · `test_gates` 10 · `test_decision` 10 · remainder
across 15 smaller files.

New tests added: **107 backend** (baseline 450 → 557) — 103 in new files and
golden-fixture guards (hysteresis persistence 34, exit/re-entry 4, security 17,
determinism/reproducibility 14, API contract 19, policy keys 12, fixture
self-consistency 3), plus a net +4 from rewriting `tests/test_policy.py` (7 → 11
tests) for the corrected allowlist/weight-sum contract. Plus **38 frontend** tests,
from a baseline of zero — the last 12 (`WeightsView` 6, `HoldingDetail` 6) were added
while preparing the Windows verification pass, to automate four of the six items
that §F had listed as manual.

### Release gate detail (13/13, from a clean checkout)

```
R-01/R-02  ✓ backend deps from requirements.txt   ✓ frontend deps via npm ci
R-03       ✓ fixtures regenerate byte-identically ✓ …and reproduce the committed CSVs
R-03b      ✓ MANIFEST verifies (110 entries)      ✓ every tracked file covered (0 unlisted)
R-04       ✓ 557 backend tests in a fresh venv
R-05       ✓ tsc clean  ✓ production build  ✓ frontend unit tests
R-06       ✓ API /health on a fresh process
R-07/R-08  ✓ golden trilogy SALASAR→TRIM/G2 · ASHOKA→EXIT/G1 · LT→HOLD/G3
R-09       ✓ history + diff survive process restart
```

### Live local-app validation

Executed against a real running pair of processes, not mocks:

| Step | Result |
|---|---|
| Engine start | `uvicorn app.main:app --host 127.0.0.1 --port 8000` → `/health` HTTP 200 |
| Engine run | `POST /run-sample` → HTTP 200, 36,042 bytes, 9 holdings, golden trilogy correct |
| UI start | Vite on 5173 → HTTP 200 |
| Proxy | `GET :5173/api/v1/health` → HTTP 200 (single origin, no CORS surface) |
| Shutdown | Clean `SIGTERM`; uvicorn logged full graceful shutdown |
| **Restart** | 2 runs survived; `previous_run` recovered for **9/9** holdings |
| Diff across restart | `previous_run_id` correct, 0 changed / 0 added / 0 removed |

### Determinism evidence

```
copy A mtimes set to 2019-01-01   →  cef1541f2fc0d5f3a80f417df5249759e87f90ea87fd73624fd575504992b317
copy B mtimes set to 2031-06-15   →  cef1541f2fc0d5f3a80f417df5249759e87f90ea87fd73624fd575504992b317
```

### Regression guards proven to fail on the old code

Two guards were deliberately verified against the pre-fix code rather than assumed:

- **Policy tags** — with `rerating_*` tagged only on a block comment above the keys, `test_policy_keys` failed; moving the tags inline made it pass.
- **Fixture dates** — with the old generator, `test_portfolio_first_date_precedes_last_date` fails with `assert '2026-05-02' <= '2026-04-23'`; passes with the fix.

---

## E. Remaining Issues

Genuine only. Cosmetic findings and false positives are listed separately.

| # | Issue | Impact on personal use | Suggested handling |
|---|---|---|---|
| E-01 | **Backend dependencies are unpinned.** `requirements.txt` uses `>=` with no lockfile (the frontend has `package-lock.json`). A future `pip install` may resolve an incompatible major. | Real but low — the app works today; risk appears only when reinstalling months later. | Pin with `pip freeze` into a `requirements.lock` when next reinstalling. Not done here: it would need a Windows-generated freeze to be meaningful. |
| E-02 | **Three browser-only checks remain.** Four of the six items originally listed as manual are now automated (§F). No browser automation exists in this environment — the server returns only `<div id="root"></div>`, so no HTTP-level tool can observe rendered output. | Low — the residual items are download-to-disk, the dead-backend banner, and visual confirmation. | §5 of `docs/WINDOWS-VERIFICATION.md` gives exact steps and an evidence-capture method. |
| E-07 | **The Windows harness has not been executed.** `scripts/verify-windows.ps1` is written and statically validated (no `else`/`elseif`/`finally`; balanced delimiters; every API path it calls confirmed against `app/main.py`; its `npm run dev -- --host --port` passthrough confirmed working), but this sandbox is Linux with no PowerShell interpreter — the release-assets host is not reachable, so none could be installed. | Real: the script is unproven on its target platform. | Run it (§1 of the guide) and send back the evidence directory. |
| E-03 | **No CI.** Nothing runs the suite on push. | Low for a single user; `release_check.sh` is the substitute. | Optional. Running `bash scripts/release_check.sh` before tagging is sufficient. |
| E-04 | **No `LICENSE` file** in the repository. | None functionally; matters only if the repo is shared. | Out of scope for this brief. |
| E-05 | `holding_period_days` is parsed in `ingest.py:72` but consumed nowhere. | None. | Left as-is: it is part of the input contract and harmless. |
| E-06 | `arena/01a033db` remains unmerged, holding themes, the snapshot archiver and EMM-H3 ACCUMULATE. | None — deliberately excluded (§C). | Available if those features are ever wanted. |

**Checked and found benign (not defects):**

- `ruff` reports 65 findings, but the repo has no ruff configuration and none are correctness bugs in the paths that run. The two that looked real were examined: **B023** at `reconcile.py:48-59` is a false positive — the `check()` closure is invoked inside the same loop iteration, before `name` is rebound, and is never stored for later use. The `F401` unused imports in `ingest.py:11` and `normalize.py:12` are cosmetic.
- `pip-audit`: clean.
- `/decisions` has no pagination. At 9 holdings the payload is 36 kB and `/run-sample` measures ~19 ms median; it scales linearly and is a non-issue at personal-portfolio size.

---

## F. Local Operating Instructions (Windows)

### Start

Double-click **`scripts\start.bat`**, or from a terminal:

```bat
cd C:\path\to\CapStew-Engine
scripts\start.bat
```

First run creates `.venv`, installs Python and frontend dependencies (a few
minutes). Later runs start immediately. Two minimised windows hold the logs:

| Window | Service | Address |
|---|---|---|
| `CapitalSteward-API` | engine | http://127.0.0.1:8000 |
| `CapitalSteward-UI` | interface | http://127.0.0.1:5173 |

The browser opens at **http://127.0.0.1:5173** once the dev server answers.
Both services bind loopback only — nothing is reachable from other machines.

### Stop

```bat
scripts\stop.bat
```

Or close the two windows. Stored runs and policy backups are untouched.

### Where your data lives

```
data\engine.db       run history (append-only SQLite) — the hysteresis source of truth
data\policy.yaml     your committed policy overrides (the shipped policy is never written)
data\backups\        timestamped copy of the previous policy, made before each commit
```

`data\` is git-ignored. **Backing up that one folder is a complete backup** of
everything the app stores; restoring it is a complete recovery. Stop the engine
first, copy the folder, restart.

### Verifying an install

```bat
bash scripts\release_check.sh     :: 13 checks, from a clean checkout (~35 s)
```

Re-baseline the manifest after committed changes, before tagging:

```bat
bash scripts\make_manifest.sh
```

### Windows verification harness and residual UI checks

Full instructions, the evidence-directory layout, and the coverage matrix are in
[`docs/WINDOWS-VERIFICATION.md`](WINDOWS-VERIFICATION.md). In brief:

`scripts\verify-windows.ps1` runs 30 automated checks (33 with `-IncludeLauncher`) — repository state,
prerequisites, port availability, loopback startup, poll-until-ready (never a
fixed sleep), health, app shell, the `/api` proxy, the golden trilogy, run
history, a full restart with previous-run recovery and diff, byte-level
preservation of `data\`, and optionally the shipped `start.bat`/`stop.bat`. It
records every HTTP response and log to a timestamped evidence directory and stops
only the PIDs it started.

Of the six UI items above, **four are now automated** and two-and-a-bit remain:

| Item | Status |
|---|---|
| 1. Sorting + `NO-DECISION` placement | automated (`DecisionsView.test.tsx`) |
| 2. Export payload content | automated (`exportDecisions.test.ts`); *the download itself is manual* |
| 3. Detail view incl. `NO-DECISION` reason | automated (`HoldingDetail.test.tsx`, 6 tests) |
| 4. Weights 99 blocked / 100 accepted | automated (`WeightsView.test.tsx`, 6 tests) |
| 5. Backend-unavailable error | client layer automated (`client.test.ts`); *the banner is manual* |
| 6. Restart, previous run, diff | automated at the API level by the harness (checks 12–14) |

The three genuinely manual steps are in §5 of the guide: confirm a file lands in
Downloads, confirm the dead-engine banner appears, and glance at the sort
indicators and detail panel.

---

## G. Final Assessment

### **READY WITH MINOR KNOWN LIMITATIONS**

**Evidence for readiness:**

- Every Critical and High defect from §A is fixed and each fix has a test that
  fails against the pre-fix code where that was checkable (D-01, D-02, D-03,
  D-05, D-06, D-07, D-08, D-12 all have such a guard).
- **557 backend + 38 frontend tests pass**, plus `tsc` clean, production build
  clean, and `npm audit` at 0 vulnerabilities (down from 2 high).
- **`release_check.sh` 13/13 from a clean checkout**, covering dependency
  reproducibility, fixture byte-reproducibility, manifest integrity and coverage,
  both test suites, a fresh API process, golden-trilogy acceptance, and
  persistence across a process restart.
- The app was **run for real** as two processes: started, exercised, shut down
  cleanly, restarted, with all 9 holdings' hysteresis state recovered.
- Determinism holds across deliberately divergent filesystem mtimes.
- The golden trilogy is unchanged: `SALASAR→TRIM/G2 · ASHOKA→EXIT/G1 · LT→HOLD/G3`.
  Scoring methodology was not altered.

**Why "minor limitations" rather than fully ready:**

- **E-02** — three browser-only checks remain (download-to-disk, the dead-engine
  banner, visual confirmation). Four of the six originally-manual items are now
  automated, and both new test files were proven to fail against the pre-fix
  code rather than merely passing against the fixed code.
- **E-07** — `scripts/verify-windows.ps1` has not been executed. It is the
  deliverable that must be run on your laptop before Windows behaviour can be
  called verified.
- **E-01** — backend dependencies are unpinned, so a fresh install months from
  now could resolve differently from the verified one.

Neither affects the correctness of any decision the engine produces today. Both
are cheap to close and neither blocks personal use.

**Not claimed:** no browser-driven end-to-end test was executed, and no Windows
artefact has been executed. `start.bat`, `stop.bat` and `verify-windows.ps1` were
each checked as far as this Linux sandbox allows — every command they invoke was
run for real (venv creation, dependency probe, uvicorn launch, `/health` polling,
Vite launch, the `/api` proxy, the `npm run dev -- --host --port` passthrough),
and the PowerShell was statically validated — but their platform control flow is
unproven. Run the harness first; it is the artefact that closes the gap.
