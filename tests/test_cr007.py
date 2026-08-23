"""CR-007 — Opportunity Cost provenance while preserving PEG proxy semantics."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from app.pipeline import run_engine
from app.policy import load_policy
from app.schema import DecisionPayloadValidationError, validate_decision_payload
from app.scoring import (
    OPPORTUNITY_COST_SOURCE_MISSING,
    OPPORTUNITY_COST_SOURCE_PEG_PROXY,
    opportunity_cost,
    opportunity_cost_evidence,
    opportunity_cost_source,
)

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
POLICY = load_policy()


def _run():
    return run_engine(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
        run_id="cr007",
    )


def _h(payload, name):
    return next(h for h in payload["holdings"] if h["instrument"] == name)


def _oc_evidence(holding):
    return holding["reason_tree"]["stage2"]["opportunity_cost"]


def test_peg_proxy_source_is_disclosed_for_fundamentals_holdings():
    payload = _run()
    salasar = _h(payload, "Salasar Techno Engg")

    evidence = _oc_evidence(salasar)
    assert evidence["source"] == OPPORTUNITY_COST_SOURCE_PEG_PROXY
    assert evidence["score"] == salasar["subscores"]["opportunity_cost"]
    assert salasar["data_quality"]["opportunity_cost"] == "proxy"
    assert POLICY["weights"]["opportunity_cost"] == 10


def test_missing_source_is_disclosed_when_fundamentals_are_absent():
    payload = _run()
    agi = _h(payload, "AGI Greenpac")

    evidence = _oc_evidence(agi)
    assert evidence == {"source": OPPORTUNITY_COST_SOURCE_MISSING, "score": None}
    assert agi["subscores"]["opportunity_cost"] is None
    assert agi["data_quality"]["opportunity_cost"] == "missing"
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"


def test_peg_missing_and_invalid_remain_neutral_peg_proxy():
    missing = {"peg_ratio": None}
    zero = {"peg_ratio": 0}
    negative = {"peg_ratio": -1}

    for fundamentals in (missing, zero, negative):
        assert opportunity_cost(fundamentals) == 50
        assert opportunity_cost_source(fundamentals) == OPPORTUNITY_COST_SOURCE_PEG_PROXY
        assert opportunity_cost_evidence(fundamentals) == {
            "source": OPPORTUNITY_COST_SOURCE_PEG_PROXY,
            "score": 50,
        }


def test_valid_peg_proxy_score_and_source_are_preserved():
    fundamentals = {"peg_ratio": 2.0}

    assert opportunity_cost(fundamentals) == 70
    assert opportunity_cost_source(fundamentals) == OPPORTUNITY_COST_SOURCE_PEG_PROXY
    assert opportunity_cost_evidence(fundamentals) == {
        "source": OPPORTUNITY_COST_SOURCE_PEG_PROXY,
        "score": 70,
    }


def test_no_fundamentals_remains_missing_not_peg_proxy():
    assert opportunity_cost(None) is None
    assert opportunity_cost_source(None) == OPPORTUNITY_COST_SOURCE_MISSING
    assert opportunity_cost_evidence(None) == {
        "source": OPPORTUNITY_COST_SOURCE_MISSING,
        "score": None,
    }


def test_schema_validates_opportunity_cost_source_when_present():
    payload = _run()
    validate_decision_payload(payload)

    invalid = copy.deepcopy(payload)
    _h(invalid, "Salasar Techno Engg")["reason_tree"]["stage2"]["opportunity_cost"]["source"] = "hurdle_d14"
    with pytest.raises(DecisionPayloadValidationError):
        validate_decision_payload(invalid)


def test_no_d14_watchlist_or_backtest_runtime_behavior_entered():
    serialized = json.dumps(_run(), sort_keys=True)

    for forbidden in ("hurdle_d14", "D-14", "backtest", "schema_version"):
        assert forbidden not in serialized
    assert '"source": "watchlist"' not in serialized
    assert '"source": "peg_proxy"' in serialized
    assert '"source": "missing"' in serialized


def test_golden_trilogy_and_agi_remain_unchanged_under_cr007():
    payload = _run()
    salasar = _h(payload, "Salasar Techno Engg")
    ashoka = _h(payload, "Ashoka Buildcon")
    lt = _h(payload, "Larsen & Toubro")
    agi = _h(payload, "AGI Greenpac")

    assert (salasar["decision"], salasar["stage1"]["winning_gate"], salasar["trim"]["mode"]) == ("TRIM", "G2", "S")
    assert (ashoka["decision"], ashoka["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")
    assert agi["decision"] == "WATCH"
    assert agi["evidence"]["tier"] == "INSUFFICIENT"
    assert agi["bucket"] is None
    assert agi["bucket_basis"] == "assumed_small_micro"
    assert agi["band_basis"] == "assumed_small_micro"
    assert agi["data_quality"]["position_sizing"] == "proxy"
