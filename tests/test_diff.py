"""Run history + run diff (Phase 3B)."""
import json
from datetime import date

from app.pipeline import decide_on_foundation, run_foundation
from app.store import RunStore

FIX = None  # set lazily via fixture


def _foundation():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "fixtures"
    return run_foundation(p / "portfolio.csv", p / "screener.csv", p / "ledger.csv",
                          as_of=date(2026, 8, 22))


def test_diff_detects_decision_changes(tmp_path):
    f = _foundation()
    run_a = decide_on_foundation(f, apply_hysteresis=False)
    # make a changed payload: flip Salasar's decision for the second run
    run_b = json.loads(json.dumps(run_a))
    run_b["run_id"] = "run_second"
    for h in run_b["holdings"]:
        if h["instrument"] == "Salasar Techno Engg":
            h["decision"] = "HARVEST"
            h["composite_score"] = 88.0
    store = RunStore(tmp_path / "engine.db")
    store.save_run(run_a)
    store.save_run(run_b)

    d = store.diff(run_b["run_id"])
    assert d["previous_run_id"] == run_a["run_id"]
    changes = {c["instrument"]: c for c in d["changed"]}
    assert changes["Salasar Techno Engg"]["decision"] == {"from": "TRIM", "to": "HARVEST"}
    assert changes["Salasar Techno Engg"]["score"] == {"from": 66.5, "to": 88.0}


def test_diff_no_changes_when_identical(tmp_path):
    f = _foundation()
    run_a = decide_on_foundation(f, apply_hysteresis=False)
    run_b = json.loads(json.dumps(run_a))
    run_b["run_id"] = "run_second"
    store = RunStore(tmp_path / "engine.db")
    store.save_run(run_a)
    store.save_run(run_b)
    d = store.diff(run_b["run_id"])
    assert d["changed"] == []


def test_diff_reports_added_and_removed(tmp_path):
    f = _foundation()
    run_a = decide_on_foundation(f, apply_hysteresis=False)
    run_b = json.loads(json.dumps(run_a))
    run_b["run_id"] = "run_second"
    # drop one holding, add another
    run_b["holdings"] = [h for h in run_b["holdings"] if h["instrument"] != "Bajaj Finance"]
    run_b["holdings"].append({"instrument": "NEWCO", "decision": "WATCH",
                              "composite_score": 44.0, "stage1": {"winning_gate": None}})
    store = RunStore(tmp_path / "engine.db")
    store.save_run(run_a)
    store.save_run(run_b)
    d = store.diff(run_b["run_id"])
    assert any(c["status"] == "added" and c["instrument"] == "NEWCO" for c in d["changed"])
    assert "Bajaj Finance" in d["removed_holdings"]


def test_diff_oldest_run_has_no_predecessor(tmp_path):
    f = _foundation()
    run_a = decide_on_foundation(f, apply_hysteresis=False)
    store = RunStore(tmp_path / "engine.db")
    store.save_run(run_a)
    d = store.diff(run_a["run_id"])
    assert d["previous_run_id"] is None
