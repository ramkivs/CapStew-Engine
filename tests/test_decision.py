"""End-to-end decision tests: FoundationPayload → DecisionPayload.

The golden trilogy is asserted at DECISION level using the generated fixtures:
  SALASAR (micro, alloc 5.2% > 1.5×3, pledge 4.0) → G2 → TRIM-S
  ASHOKA (pledge 12.4)                              → G1 → EXIT
  LT     (22d to LTCG, valuation 77 < 85)           → G3 → HOLD
"""
from datetime import date
from pathlib import Path

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _run(overrides=None, as_of=date(2026, 8, 22)):
    from app.pipeline import run_engine
    return run_engine(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                      as_of=as_of, policy_overrides=overrides)


def _h(payload, name):
    return next(h for h in payload["holdings"] if h["instrument"] == name)


def test_golden_salasar_g2_trim_s(foundation):
    payload = _run()
    h = _h(payload, "Salasar Techno Engg")
    assert h["decision"] == "TRIM"
    assert h["stage1"]["winning_gate"] == "G2"
    assert h["trim"]["mode"] == "S"


def test_golden_ashoka_g1_exit(foundation):
    h = _h(_run(), "Ashoka Buildcon")
    assert h["decision"] == "EXIT"
    assert h["stage1"]["winning_gate"] == "G1"
    assert "averaging_block_adds" in h["behavioral_flags"]


def test_golden_lt_g3_hold(foundation):
    h = _h(_run(), "Larsen & Toubro")
    assert h["decision"] == "HOLD"
    assert h["stage1"]["winning_gate"] == "G3"
    assert h["stage1"]["tax_defer_suppressed"] is False


def test_agi_insufficient_evidence_watch(foundation):
    h = _h(_run(), "AGI Greenpac")
    assert h["decision"] == "WATCH"
    assert h["evidence"]["tier"] == "INSUFFICIENT"
    assert h["evidence"]["critical_categories_missing"]


def test_required_contract_fields_present(foundation):
    h = _h(_run(), "Salasar Techno Engg")
    for field in ("decision", "composite_score", "confidence", "confidence_breakdown",
                  "stage1", "reason_tree", "why_now", "evidence", "trim"):
        assert field in h, field
    assert h["stage1"]["winning_gate"] is not None
    assert h["reason_tree"]["decision_path"]
    assert h["why_now"]["primary_trigger"]
    assert "fifo_lots_to_sell" in h["trim"]


def test_decision_payload_audit_fields(foundation):
    p = _run()
    assert p["engine_version"].startswith("0.3")
    assert p["policy_version"] == 1
    assert p["input_hash"] == foundation["content_hash"]
    assert p["content_hash"]


def test_action_queue_risk_first(foundation):
    p = _run()
    queue = p["portfolio_layer"]["action_queue"]
    orders = {"EXIT": 0, "TRIM": 1, "HARVEST": 2}
    assert queue, "expected non-empty action queue"
    # EXIT (ASHOKA) must rank first
    assert queue[0]["decision"] == "EXIT" and queue[0]["reason"] == "RISK"
    keys = [orders[q["decision"]] for q in queue]
    assert keys == sorted(keys), "queue must respect EXIT > TRIM > HARVEST"


def test_determinism_replay(foundation):
    a = _run()
    b = _run()
    assert a["content_hash"] == b["content_hash"]


def test_what_if_policy_override_changes_decisions(foundation):
    # Raising the absolute cap from 10% to 50% should stop G2 firing on pure-cap names
    from app.pipeline import decide_on_foundation
    base = decide_on_foundation(foundation, apply_hysteresis=False)
    override = decide_on_foundation(
        foundation,
        policy_overrides={"max_single_stock_pct": 50.0, "rebalance_trigger_multiple": 10.0},
        apply_hysteresis=False,
    )
    assert override["content_hash"] != base["content_hash"]
    # Bank of Baroda (10.67% > 10 cap) flips from TRIM-S to a composite decision
    bob_before = _h(base, "Bank of Baroda")["decision"]
    bob_after = _h(override, "Bank of Baroda")["decision"]
    assert bob_before == "TRIM" and bob_after != "TRIM"


def test_g0_broken_reconciliation_is_no_decision():
    # corrupt the ledger so Bank of Baroda's invested no longer reconciles
    from app.pipeline import run_engine
    import tempfile, csv
    from pathlib import Path as P
    with tempfile.TemporaryDirectory() as tmp:
        tmp = P(tmp)
        # copy fixtures
        for f in ("portfolio.csv", "screener.csv", "ledger.csv"):
            (tmp / f).write_bytes((FIXDIR / f).read_bytes())
        # corrupt: bump one BoB buy price
        rows = list(csv.DictReader(open(tmp / "ledger.csv", encoding="utf-8")))
        for r in rows:
            if r["Instrument"] == "Bank of Baroda":
                r["Buy Price"] = "999.00"
                break
        with open(tmp / "ledger.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        payload = run_engine(tmp / "portfolio.csv", tmp / "screener.csv", tmp / "ledger.csv",
                             as_of=date(2026, 8, 22))
    bob = _h(payload, "Bank of Baroda")
    assert bob["decision"] == "NO-DECISION"
    assert bob["stage1"]["winning_gate"] == "G0"
