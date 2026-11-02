# Windows Verification Guide — Capital Steward Engine

Companion to `FINAL-REPORT-v1.2.md`. Covers the two things that report could not
close: driving the application on a real Windows machine, and the browser-level
UI checks.

**Nothing here has been executed on Windows yet.** The harness below is written
and statically validated, but the sandbox that produced it is Linux with no
PowerShell interpreter and no browser. Treat every result as pending until you
run it and the evidence directory agrees.

---

## 1. The verification script

**`scripts\verify-windows.ps1`** — 615 lines, PowerShell 5.1+ (ships with Windows 10/11).
A default run records **27 checks**; `-IncludeLauncher` makes it **28**.

### Run it

```powershell
cd C:\path\to\CapStew-Engine

# normal run
powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1

# also drive scripts\start.bat and scripts\stop.bat
powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1 -IncludeLauncher -Verbose
```

Exit code is `0` only if every check passed. A failure prints the failing check
and writes `90-error.txt`.

### Parameters

| Parameter | Default | Purpose |
|---|---|---|
| `-RepoRoot` | parent of `scripts\` | checkout to verify |
| `-EvidenceRoot` | `$env:USERPROFILE\CapStew-Verification` | where evidence lands |
| `-ExpectedBranch` | `main` | must match, or the run records a FAIL |
| `-ExpectedCommit` | *(empty)* | optional strict pin; empty records `HEAD` without rejecting it |
| `-BackendPort` / `-FrontendPort` | `8000` / `5173` | loopback ports |
| `-ReadyTimeoutSec` | `180` | polling budget for readiness |
| `-IncludeLauncher` | off | also exercise `start.bat` / `stop.bat` |
| `-AllowDirtyTree` | off | proceed despite uncommitted changes |

### Why the defaults are `main` and an empty commit pin

`-ExpectedBranch` defaults to **`main`** because that is the branch a laptop
holds once this work is merged. Verify a PR head instead by passing
`-ExpectedBranch arena/fed5107a-capstew-engine`.

`-ExpectedCommit` defaults to **empty** on purpose. A hardcoded default SHA is
self-defeating: the commit that sets it changes `HEAD` and instantly makes it
stale, so the harness would reject the very checkout it shipped in. With the pin
empty the script records `HEAD` in `02-git-state.txt` and instead proves the
checkout carries this release by **substance**:

- `ENGINE_VERSION` in `app\config.py` is `1.2.0`
- `scripts\verify-windows.ps1` and `docs\WINDOWS-VERIFICATION.md` are present

An old or wrong checkout fails those. To pin an exact release, pass
`-ExpectedCommit <sha>` (a prefix is enough) — that adds a strict match as a
further check rather than replacing the substance checks.

### Prerequisites

Run `scripts\start.bat` **once** first. That creates `.venv` and installs
`frontend\node_modules`; the verification script deliberately does not install
anything, so it tests the environment you actually have.

### What it is not

The script is **read-only with respect to the repository**. It never clones,
pulls, checks out, builds, regenerates fixtures, or edits a tracked file. It
appends runs to `data\engine.db` — because that is what running the engine does —
and then proves nothing that was already there was destroyed.

---

## 2. Evidence directory

```
%USERPROFILE%\CapStew-Verification\verify-YYYYMMDD-HHMMSS\
├── 00-summary.txt                     outcome, pass/fail table, processes started
├── 01-environment.txt                 OS, PowerShell, Python, Node, npm
├── 02-git-state.txt                   branch, commit, remote, status --porcelain
├── 03-ports.txt                       8000 / 5173 free or held, and by which PID
├── 10-backend.log                     uvicorn stdout
├── 10-backend.log.err                 uvicorn stderr
├── 11-frontend.log                    vite stdout
├── 11-frontend.log.err                vite stderr
├── 12-backend-after-restart.log       the restarted engine's stdout
├── 20-health.json                     GET  /api/v1/health
├── 21-ui-index.html                   the app shell served by vite
├── 22-proxy-health.json               GET  :5173/api/v1/health  (through the proxy)
├── 30-run-1.json                      POST /api/v1/run-sample   (before restart)
├── 31-golden-trilogy.txt              per-instrument expected vs actual
├── 40-runs-before-restart.json        GET  /api/v1/runs
├── 41-runs-before-restart-parsed.json parsed form of the above
├── 42-policy-before-restart.json      GET  /api/v1/policy
├── 43-runs-after-restart.json         GET  /api/v1/runs         (after restart)
├── 44-run-2-after-restart.json        POST /api/v1/run-sample   (after restart)
├── 45-diff.json                       GET  /api/v1/runs/{run2}/diff
├── 46-policy-after-restart.json       GET  /api/v1/policy
├── 50-data-before.txt                 data\ file list + SHA-256 before
├── 51-data-after.txt                  data\ file list + SHA-256 after
├── 52-preservation.txt                destroyed / changed / preserved breakdown
├── 60-launcher-start.txt              start.bat output   (-IncludeLauncher only)
├── 61-launcher-stop.txt               stop.bat output    (-IncludeLauncher only)
└── 90-error.txt                       only written if the run aborted
```

---

## 3. What the script verifies automatically

| # | Check | How |
|---|---|---|
| 1 | `app\main.py` present; remote and branch match; commit recorded (or pinned); working tree clean | `git rev-parse`, `git status --porcelain` |
| 1b | **Checkout carries v1.2** — `ENGINE_VERSION` is `1.2.0` and both verification artefacts exist | `app\config.py`, `Test-Path` |
| 2 | Python, Node, npm resolve; `frontend\node_modules` installed | `Get-Command`, `--version` |
| 3 | Ports 8000 and 5173 are free before starting | `Get-NetTCPConnection` |
| 4 | Both services start | `Start-Process`, PIDs recorded |
| 5 | **Real readiness**, not a fixed sleep — polls until HTTP 200 or the budget expires | `Wait-ForHttp` |
| 6 | `/health` returns `status: ok` | HTTP |
| 7 | The interface serves the app shell (`id="root"`) | HTTP |
| 8 | **The dev server proxies `/api` to the engine** | `:5173/api/v1/health` |
| 9 | **Golden trilogy** — SALASAR→TRIM/G2, ASHOKA→EXIT/G1, LT→HOLD/G3 | `/run-sample` |
| 10 | Run 1 appears in history | `/runs` |
| 11 | Engine stops on request, restarts, and is healthy again | `taskkill /T`, re-poll |
| 12 | **Run 1 survives the restart** | `/runs` after restart |
| 13 | **Hysteresis `previous_run` recovered from the store** for every holding | run 2 payload |
| 14 | **Diff links run 2 to run 1** | `/runs/{id}/diff.previous_run_id` |
| 15 | Policy identical across the restart | JSON equality |
| 16 | **No pre-existing file in `data\` was destroyed** | SHA-256 snapshot diff |
| 17 | Run store grew or held, never shrank (append-only) | run counts |
| 18 | `data\policy.yaml` override byte-identical | SHA-256 |
| 19 | `start.bat` brings both services up; `stop.bat` releases both ports | `-IncludeLauncher` |

It stops **only the PIDs it started**, via `taskkill /PID <pid> /T /F`. It never
kills by name, so an unrelated `python.exe` or `node.exe` on your machine is
untouched.

## 4. What it cannot verify

| Gap | Why | What to do |
|---|---|---|
| Anything rendered in a browser | The script speaks HTTP. The server returns only `<div id="root"></div>`; React draws everything client-side. Verified in this session: `SALASAR`, `TRIM`, `HOLD`, `Holdings` are all **absent** from the served bytes. | §5 below |
| Files actually landing in your Downloads folder | Requires a real browser | §5, step 2 |
| Visual appearance, focus order, responsive layout | Subjective | §5 |
| Behaviour with a genuinely dead backend | The script needs the backend up to test anything | §5, step 5 |
| Windows service semantics, reboot survival | Out of scope for a foreground app | n/a |

---

## 5. Browser checks — what is automated and what is left

Four of the six items in §F of the final report are now covered by automated
component tests (jsdom, via the existing vitest setup — **no new framework was
added**). The frontend suite went from 26 to **38 tests**.

| §F item | Automated coverage | Residual manual step |
|---|---|---|
| 1. Holdings sorting + NO-DECISION placement | `DecisionsView.test.tsx` — asc → desc → payload order; blocked rows stay last numerically | glance at the ▲/▼ indicators |
| 2. Decisions JSON/CSV content | `exportDecisions.test.ts` — provenance header, one row per holding, values verbatim, NO-DECISION row blank, RFC 4180 quoting | **confirm the file downloads** |
| 3. Holding detail incl. NO-DECISION reason | `HoldingDetail.test.tsx` (6 tests) | none |
| 4. Weights 99 blocked / 100 accepted | `WeightsView.test.tsx` (6 tests) | none |
| 5. Backend-unavailable error | `client.test.ts` — `ENGINE_UNREACHABLE`, envelope, non-JSON body | **confirm the banner appears** |
| 6. Restart, previous run, diff | `verify-windows.ps1` checks 12–14, at the API level | glance at the History tab |

Both new test files were proven to fail against the pre-fix code, not merely to
pass against the fixed code:

- Removing the weight guard makes 2 of 6 `WeightsView` tests fail.
- Restoring the original unguarded reads in `HoldingDetail` throws
  `TypeError: Cannot convert undefined or null to object` — the exact crash that
  blanked the Decisions screen.

### The three steps that still need a human

Start the app (`scripts\start.bat`), then at <http://127.0.0.1:5173>:

**A. Export actually downloads**

1. Decisions tab → click **Decisions CSV**.
2. Open the downloaded `decisions_run_*.csv` in Notepad.
3. Confirm the first five lines are `# run_id=…`, `# as_of=…`, `# engine_version=…`,
   `# policy_version=…`, `# content_hash=…`, then a header row, then one row per holding.
4. Repeat with **Decisions JSON** and confirm it parses.
   *Evidence:* save both files into the evidence directory next to `00-summary.txt`.

**B. Error is shown when the engine is down**

1. With the UI open, close the `CapitalSteward-API` window.
2. Click any tab that refetches (History, Tax, Weights).
3. Confirm a message naming `ENGINE_UNREACHABLE` appears — **not** a blank panel.
4. Run `scripts\start.bat` again and confirm the panel recovers.
   *Evidence:* screenshot into the evidence directory.

**C. Sorting and detail panel look right**

1. Decisions tab → click the **Composite** header three times: ascending,
   descending, back to the original order. The ▲/▼ indicator should follow.
2. Click any row → the detail panel opens with subscores and the FIFO lot table.
3. If a holding shows `NO-DECISION`, click it: you should see the reason
   (`G0 → NO-DECISION …`) and dashes where scores would be — never a blank panel.
   *Evidence:* screenshot into the evidence directory.

---

## 6. Reporting a problem

Send the whole `verify-YYYYMMDD-HHMMSS\` folder. `00-summary.txt` names the
failing check; `90-error.txt` (if present) carries the stack trace; the numbered
JSON files show exactly what the engine returned.
