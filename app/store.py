"""Append-only run store (SQLite) — ADR-4 / architecture §11.5 `decisions`.

Runs are immutable once written. This is what makes hysteresis auditable across
process restarts: the engine's "previous run" state is derived from persisted
history, never from process memory.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .schema import validate_decision_payload

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    policy_version INTEGER,
    input_hash TEXT,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class RunStore:
    def __init__(self, path=None):
        self.path = Path(path or config.STORE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save_run(self, payload, *, validate=False):
        if validate:
            validate_decision_payload(payload)
        self._conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(run_id, as_of, engine_version, policy_version, input_hash, content_hash, payload_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                payload["run_id"],
                payload["as_of"],
                payload["engine_version"],
                payload.get("policy_version"),
                payload.get("input_hash"),
                payload["content_hash"],
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def get_run(self, run_id):
        row = self._conn.execute(
            "SELECT payload_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def latest_run(self):
        row = self._conn.execute(
            "SELECT payload_json FROM runs ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def previous_holdings(self):
        """instrument -> {decision, composite_score, as_of[, pending]} from the latest run.

        `pending` is the N=2 hysteresis confirmation counter that run left behind
        (Freeze §6). It is carried only when present, so records written before
        the counter was persisted keep resolving exactly as they did before.
        """
        latest = self.latest_run()
        if not latest:
            return {}
        as_of = latest.get("as_of")
        history = {}
        for h in latest.get("holdings", []):
            state = {
                "decision": h["decision"],
                "composite_score": h["composite_score"],
                "as_of": as_of,
            }
            prev = h.get("previous_run") or {}
            if prev.get("pending"):
                state["pending"] = prev["pending"]
            history[h["instrument"]] = state
        return history

    def list_runs(self):
        rows = self._conn.execute(
            "SELECT run_id, as_of, engine_version, policy_version, input_hash, content_hash, created_at "
            "FROM runs ORDER BY created_at DESC").fetchall()
        cols = ("run_id", "as_of", "engine_version", "policy_version",
                "input_hash", "content_hash", "created_at")
        return [dict(zip(cols, r)) for r in rows]

    def count(self):
        return self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def diff(self, run_id):
        """Diff a run against its immediate predecessor (by created_at)."""
        rows = self._conn.execute(
            "SELECT run_id, created_at FROM runs ORDER BY created_at DESC, rowid DESC").fetchall()
        ids = [r[0] for r in rows]
        if run_id not in ids:
            return None
        i = ids.index(run_id)
        if i + 1 >= len(ids):
            return {"run_id": run_id, "previous_run_id": None,
                    "note": "no previous run to diff against"}
        prev_id = ids[i + 1]
        cur = self.get_run(run_id)
        prev = self.get_run(prev_id)

        prev_map = {h["instrument"]: h for h in prev["holdings"]}
        cur_map = {h["instrument"]: h for h in cur["holdings"]}
        changed = []
        for inst, h in cur_map.items():
            p = prev_map.get(inst)
            if p is None:
                changed.append({"instrument": inst, "status": "added",
                                "decision": h["decision"]})
            elif (p["decision"], p["composite_score"], p["stage1"].get("winning_gate")) != \
                 (h["decision"], h["composite_score"], h["stage1"].get("winning_gate")):
                changed.append({
                    "instrument": inst, "status": "changed",
                    "decision": {"from": p["decision"], "to": h["decision"]},
                    "score": {"from": p["composite_score"], "to": h["composite_score"]},
                    "gate": {"from": p["stage1"].get("winning_gate"),
                             "to": h["stage1"].get("winning_gate")},
                })
        removed = [inst for inst in prev_map if inst not in cur_map]
        return {
            "run_id": run_id,
            "previous_run_id": prev_id,
            "as_of": {"from": prev.get("as_of"), "to": cur.get("as_of")},
            "changed": sorted(changed, key=lambda c: c["instrument"]),
            "removed_holdings": sorted(removed),
            "distribution": {
                "from": prev.get("portfolio_summary", {}).get("decision_distribution", {}),
                "to": cur.get("portfolio_summary", {}).get("decision_distribution", {}),
            },
        }

    def close(self):
        self._conn.close()
