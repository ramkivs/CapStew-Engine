#!/usr/bin/env bash
# Capital Steward Engine — Release/Operational Readiness Gate (R-01…R-09).
# Verifies the v1 baseline from a CLEAN checkout: reproducible deps, fresh fixture
# regeneration (determinism), fresh tests, fresh build, fresh API process, demo + UI
# acceptance, and persistence across restart. Run from the repo root.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/cs-release-XXXX)"
PASS=0; FAIL=0
ok(){  echo "  ✓ $1"; PASS=$((PASS+1)); }
bad(){ echo "  ✗ $1"; FAIL=$((FAIL+1)); }
check(){ if [ "$2" = "0" ]; then ok "$1"; else bad "$1"; fi; }

echo "== R-01/R-02 — clean checkout + dependency reproducibility =="
echo "  work dir: $WORK"
cp -r "$REPO" "$WORK/src"
cd "$WORK/src"
rm -rf .git .pytest_cache data frontend/node_modules $(find . -name __pycache__ -type d) dist build

python3 -m venv "$WORK/venv" >/dev/null 2>&1
"$WORK/venv/bin/pip" install -q -r requirements.txt >/dev/null 2>&1
check "backend deps installed from requirements.txt" $?

( cd frontend && npm ci --silent >/dev/null 2>&1 )
check "frontend deps installed via npm ci (lockfile)" $?

echo "== R-03 — fixture regeneration (determinism) =="
"$WORK/venv/bin/python" fixtures/generate_fixtures.py "$WORK/fx1" >/dev/null 2>&1
"$WORK/venv/bin/python" fixtures/generate_fixtures.py "$WORK/fx2" >/dev/null 2>&1
if diff -r "$WORK/fx1" "$WORK/fx2" >/dev/null 2>&1; then ok "fixtures regenerate byte-identically (deterministic)"; else bad "fixture regeneration non-deterministic"; fi

echo "== R-04 — backend tests (fresh venv) =="
if "$WORK/venv/bin/python" -m pytest -q >/dev/null 2>&1; then
  N=$("$WORK/venv/bin/python" -m pytest -q 2>/dev/null | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
  ok "backend tests pass in fresh env (${N:-?} tests)"
else
  bad "backend tests failed in fresh env"
fi

echo "== R-05 — frontend type + build verification (fresh node_modules) =="
( cd frontend && npx tsc --noEmit >/dev/null 2>&1 ); check "tsc --noEmit clean" $?
( cd frontend && npm run build >/dev/null 2>&1 ); check "vite production build succeeds" $?

echo "== R-06 — API startup (fresh process) =="
"$WORK/venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >/dev/null 2>&1 &
UVPID=$!
sleep 3
if curl -s http://127.0.0.1:8001/api/v1/health | grep -q '"status":"ok"'; then ok "API /health on fresh process"; else bad "API health failed"; fi

echo "== R-07/R-08 — demo + UI acceptance (golden trilogy) =="
RESP=$(curl -s -X POST http://127.0.0.1:8001/api/v1/run-sample)
python3 - "$RESP" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
want = {'Salasar Techno Engg': ('TRIM','G2'), 'Ashoka Buildcon': ('EXIT','G1'), 'Larsen & Toubro': ('HOLD','G3')}
ok = all(h['decision']==want[h['instrument']][0] and h['stage1']['winning_gate']==want[h['instrument']][1]
         for h in d['holdings'] if h['instrument'] in want)
print('  ' + ('✓' if ok else '✗') + ' golden trilogy: SALASAR→TRIM/G2 · ASHOKA→EXIT/G1 · LT→HOLD/G3')
sys.exit(0 if ok else 1)
PY
check "demo acceptance (run-sample) golden trilogy" $?

echo "== R-09 — persistence across restart =="
curl -s -X POST http://127.0.0.1:8001/api/v1/run-sample >/dev/null
kill $UVPID 2>/dev/null; wait $UVPID 2>/dev/null || true
"$WORK/venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >/dev/null 2>&1 &
UVPID=$!
sleep 3
RID=$(curl -s http://127.0.0.1:8001/api/v1/runs | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['run_id'] if r else '')")
if [ -n "$RID" ]; then
  DIFF=$(curl -s "http://127.0.0.1:8001/api/v1/runs/$RID/diff")
  echo "$DIFF" | grep -q 'previous_run_id' && ok "history + diff survive process restart" || bad "diff after restart failed"
else
  bad "no runs persisted across restart"
fi
kill $UVPID 2>/dev/null; wait $UVPID 2>/dev/null || true

echo
echo "════ RESULT: $PASS passed, $FAIL failed ════"
[ "$FAIL" = "0" ]
