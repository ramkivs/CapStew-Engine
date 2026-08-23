import copy
import csv
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import _LAST_FOUNDATION, _LAST_TAX, app
from app.pipeline import compute_tax_year, run_engine, run_foundation
from app.schema import DecisionPayloadValidationError, validate_decision_payload
from app.store import RunStore

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def _files():
    return {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }


@pytest.fixture
def payload():
    return run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="schema_test",
    )


def _holding(payload, instrument):
    return next(h for h in payload["holdings"] if h["instrument"] == instrument)


def _trim_holding(payload):
    return next(h for h in payload["holdings"] if h["trim"] is not None)


def _assert_invalid(payload, expected_path):
    with pytest.raises(DecisionPayloadValidationError) as exc:
        validate_decision_payload(payload)
    assert expected_path in "; ".join(exc.value.errors)


# ---- positive validation matrix ----


def test_valid_full_payload_passes(payload):
    assert validate_decision_payload(payload) is payload


def test_run_sample_payload_passes_and_persists():
    _LAST_FOUNDATION.clear()
    _LAST_TAX.clear()
    client = TestClient(app)
    response = client.post("/api/v1/run-sample")
    assert response.status_code == 200, response.text
    body = response.json()
    validate_decision_payload(body)
    assert "tax_year" in body

    decisions = client.get("/api/v1/decisions")
    assert decisions.status_code == 200, decisions.text
    assert decisions.json()["content_hash"] == body["content_hash"]


def test_run_endpoint_payload_passes():
    _LAST_FOUNDATION.clear()
    _LAST_TAX.clear()
    client = TestClient(app)
    response = client.post("/api/v1/run", files=_files())
    assert response.status_code == 200, response.text
    validate_decision_payload(response.json())


def test_what_if_payload_passes_after_run():
    _LAST_FOUNDATION.clear()
    _LAST_TAX.clear()
    client = TestClient(app)
    run_response = client.post("/api/v1/run", files=_files())
    assert run_response.status_code == 200, run_response.text

    what_if = client.post("/api/v1/what-if", json={"run_id": "schema", "policy_overrides": {}})
    assert what_if.status_code == 200, what_if.text
    body = what_if.json()
    assert body["run_id"] == "whatif_schema"
    validate_decision_payload(body)


def test_optional_tax_year_payload_passes():
    _LAST_FOUNDATION.clear()
    _LAST_TAX.clear()
    client = TestClient(app)
    files = _files()
    files["sold"] = ("sold_sample.csv", (FIXDIR / "sold_sample.csv").read_bytes(), "text/csv")
    response = client.post("/api/v1/run", files=files)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "tax_year" in body
    validate_decision_payload(body)


def test_tax_year_added_in_process_passes(payload):
    foundation = run_foundation(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="schema_tax",
    )
    payload["tax_year"] = compute_tax_year(foundation, FIXDIR / "sold_sample.csv")
    payload["portfolio_summary"]["tax"].update({
        "provisional": False,
        "ltcg_booked": payload["tax_year"]["summary"]["gross"]["ltcg"],
        "stcg_booked": payload["tax_year"]["summary"]["gross"]["stcg"],
        "ltcg_headroom": payload["tax_year"]["summary"]["exemption"]["headroom"],
        "stcl_harvestable": payload["tax_year"]["summary"]["gross"]["stcl"],
    })
    validate_decision_payload(payload)


def test_no_decision_holding_payload_passes(tmp_path):
    for name in ("portfolio.csv", "screener.csv", "ledger.csv"):
        (tmp_path / name).write_bytes((FIXDIR / name).read_bytes())

    rows = list(csv.DictReader(open(tmp_path / "ledger.csv", encoding="utf-8")))
    for row in rows:
        if row["Instrument"] == "Bank of Baroda":
            row["Buy Price"] = "999.00"
            break
    with open(tmp_path / "ledger.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    payload = run_engine(
        tmp_path / "portfolio.csv",
        tmp_path / "screener.csv",
        tmp_path / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="schema_no_decision",
    )
    blocked = _holding(payload, "Bank of Baroda")
    assert blocked["decision"] == "NO-DECISION"
    validate_decision_payload(payload)


def test_newly_stored_payload_passes_validation(payload):
    store = RunStore()
    try:
        store.save_run(payload, validate=True)
        stored = store.latest_run()
    finally:
        store.close()
    validate_decision_payload(stored)
    assert stored["content_hash"] == payload["content_hash"]


def test_historical_persisted_payloads_remain_readable(payload):
    historical = {"run_id": "legacy", "payload_shape": "predates-cr-001"}
    store = RunStore()
    try:
        store._conn.execute(
            "INSERT INTO runs "
            "(run_id, as_of, engine_version, policy_version, input_hash, content_hash, payload_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("legacy", "2026-08-22", "1.0.0", 1, "legacy-input", "legacy-hash",
             json.dumps(historical), "2026-08-22T00:00:00+00:00"),
        )
        store._conn.commit()
        assert store.get_run("legacy") == historical
    finally:
        store.close()


# ---- negative, boundary, and malformed-shape matrix ----


def test_invalid_generated_payload_returns_generic_500(monkeypatch):
    import app.main as main

    def invalid_decision_payload(*_args, **_kwargs):
        return {"run_id": "invalid"}

    monkeypatch.setattr(main, "decide_on_foundation", invalid_decision_payload)
    client = TestClient(app)
    response = client.post("/api/v1/run", files=_files())

    assert response.status_code == 500
    error = response.json()["detail"]["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["severity"] == "blocking"
    assert "schema" not in error["code"].lower()


def test_missing_required_top_level_field_fails(payload):
    del payload["run_id"]
    _assert_invalid(payload, "$.run_id")


def test_invalid_decision_fails(payload):
    payload["holdings"][0]["decision"] = "SELL"
    _assert_invalid(payload, "holdings[0].decision")


def test_confidence_boundaries(payload):
    payload["holdings"][0]["confidence"] = 20
    validate_decision_payload(payload)
    payload["holdings"][0]["confidence"] = 95
    validate_decision_payload(payload)

    payload["holdings"][0]["confidence"] = 19
    _assert_invalid(payload, "holdings[0].confidence")
    payload["holdings"][0]["confidence"] = 96
    _assert_invalid(payload, "holdings[0].confidence")


def test_non_integer_confidence_fails(payload):
    payload["holdings"][0]["confidence"] = 75.5
    _assert_invalid(payload, "holdings[0].confidence")


def test_subscore_boundaries(payload):
    payload["holdings"][0]["subscores"]["position_sizing"] = 0
    validate_decision_payload(payload)
    payload["holdings"][0]["subscores"]["position_sizing"] = 100
    validate_decision_payload(payload)

    payload["holdings"][0]["subscores"]["position_sizing"] = -0.1
    _assert_invalid(payload, "subscores.position_sizing")
    payload["holdings"][0]["subscores"]["position_sizing"] = 100.1
    _assert_invalid(payload, "subscores.position_sizing")


def test_malformed_stage1_fails(payload):
    payload["holdings"][0]["stage1"]["fired"] = "yes"
    _assert_invalid(payload, "stage1.fired")


def test_malformed_evidence_fails(payload):
    payload["holdings"][0]["evidence"]["coverage"] = "full"
    _assert_invalid(payload, "evidence.coverage")


def test_malformed_trim_fails(payload):
    _trim_holding(payload)["trim"]["fifo_lots_to_sell"] = "lot-1"
    _assert_invalid(payload, "trim.fifo_lots_to_sell")


def test_malformed_lot_fails(payload):
    payload["holdings"][0]["lots"][0]["ltcg_eligible"] = "false"
    _assert_invalid(payload, "lots[0].ltcg_eligible")


def test_malformed_warnings_fail(payload):
    payload["warnings"][0]["message"] = 123
    _assert_invalid(payload, "warnings[0].message")


def test_malformed_action_queue_fails(payload):
    payload["portfolio_layer"]["action_queue"][0]["rank"] = "first"
    _assert_invalid(payload, "action_queue[0].rank")


# ---- non-mutation, determinism, golden, and CR-009 guards ----


def test_validation_is_non_mutating(payload):
    before = copy.deepcopy(payload)
    encoded_before = json.dumps(payload, sort_keys=True)
    content_hash = payload["content_hash"]

    assert validate_decision_payload(payload) is payload

    assert payload == before
    assert json.dumps(payload, sort_keys=True) == encoded_before
    assert payload["content_hash"] == content_hash


def test_content_hash_deterministic_for_identical_inputs():
    p1 = run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="hash_a",
    )
    p2 = run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="hash_b",
    )
    assert p1["content_hash"] == p2["content_hash"]
    validate_decision_payload(p1)
    validate_decision_payload(p2)


def test_golden_trilogy_and_agi_unchanged(payload):
    salasar = _holding(payload, "Salasar Techno Engg")
    ashoka = _holding(payload, "Ashoka Buildcon")
    lt = _holding(payload, "Larsen & Toubro")
    agi = _holding(payload, "AGI Greenpac")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"], salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"


def test_no_forbidden_post_cr009_fields_or_schema_version(payload):
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("opportunity_cost.source", "hurdle_d14", "schema_version"):
        assert forbidden not in serialized
    validate_decision_payload(payload)


def test_unknown_extra_fields_are_allowed(payload):
    payload["extra_top_level"] = {"allowed": True}
    payload["holdings"][0]["extra_holding_field"] = "allowed"
    payload["holdings"][0]["reason_tree"]["extra_reason_tree"] = {"allowed": True}
    validate_decision_payload(payload)


def test_run_equals_decisions_behavior_unchanged():
    _LAST_FOUNDATION.clear()
    _LAST_TAX.clear()
    client = TestClient(app)
    run_response = client.post("/api/v1/run", files=_files())
    assert run_response.status_code == 200, run_response.text
    decisions = client.get("/api/v1/decisions")
    assert decisions.status_code == 200, decisions.text
    assert decisions.json()["content_hash"] == run_response.json()["content_hash"]
    assert [h["decision"] for h in decisions.json()["holdings"]] == [
        h["decision"] for h in run_response.json()["holdings"]
    ]
