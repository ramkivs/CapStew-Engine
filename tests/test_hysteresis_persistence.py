"""Freeze §6 N=2 hysteresis persistence across separate runs / process restarts.

Characterization + regression coverage for the remediation that makes the frozen
N=2 rule operational when state is restored from the persisted previous run.

Scope guard: nothing here is instrument-specific. Every scenario is expressed in
terms of (prior decision, composite, band) and uses synthetic in-test payloads,
so no fixture is read, written, or required to change.

The persisted pending shape is exactly the one Hysteresis.apply() already builds:

    {"band": "<HOLD|WATCH|TRIM|HARVEST>", "count": <integer>}
"""
from datetime import date

import pytest

from app.decision import decide_all
from app.hysteresis import Hysteresis
from app.pipeline import run_engine
from app.schema import validate_decision_payload
from app.scoring import band_of
from app.store import RunStore

D1, D2, D3, D4 = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4))

# --- synthetic instruments (in-test only; fixtures are never touched) ---------
#
# Both are single-lot, in-band, unpledged and far from LTCG so that no Stage-1
# gate can fire: the whole test surface is G4 + hysteresis.
_BASE_FUND = {
    "sub_sector": "Paper & Packaging", "market_cap_cr": 4200,
    "sma_200": 100.0, "peg_ratio": 1.5, "roe": 15.0, "roce": 14.0,
    "eps_growth_1y_hist": 10.0, "eps_growth_1y_fwd": 12.0,
    "debt_equity": 0.5, "interest_coverage": 6.0,
}
# low composite  -> G4 band HOLD
_LOW = {"close_price": 110.0, "pe_ratio": 12.0, "pe_premium_vs_subsector": 0.24}
# high composite -> G4 band TRIM
_HIGH = {"close_price": 102.0, "pe_ratio": 40.0, "pe_premium_vs_subsector": 1.2,
         "roe": 15.0, "roce": -4.0, "eps_growth_1y_fwd": -6.0}


def _instrument(name, profile):
    fund = {**_BASE_FUND, **profile}
    return {
        "instrument": name, "ticker": name.replace(" ", ""), "bucket": "small",
        "alloc_pct": 2.5, "gain_pct": 19.73, "current_value": 14120.0,
        "qty_held": 20, "pledge_pct": 0.0, "in_screener": True, "fundamentals": fund,
    }


def _foundation(as_of, run_id, name, profile):
    return {
        "run_id": run_id, "engine_version": "test", "as_of": as_of.isoformat(),
        "content_hash": "test", "data_as_of": {"stale_files": []},
        "reconciliation": {"ok": True, "blocking": [], "warnings": [], "checks": [],
                           "issues": []},
        "positions": [_instrument(name, profile)],
        "lots": [{"lot_id": 1, "instrument": name, "ticker": name.replace(" ", ""),
                  "trade_date": "2026-03-19", "qty": 20, "buy_price": 589.65,
                  "ltp": 706.0, "invested": 11793.0, "value": 14120.0, "pnl": 2327.0,
                  "pnl_pct": 19.73, "days_held": 162, "days_to_ltcg": 203,
                  "ltcg_eligible": False}],
        "warnings": [],
    }


def _run(store, as_of, run_id, name, profile):
    """One authoritative run: persisted history -> fresh Hysteresis -> save."""
    history = store.previous_holdings()
    hv = Hysteresis()
    payload = decide_all(_foundation(as_of, run_id, name, profile),
                         apply_hysteresis=True, history=history, hysteresis=hv)
    validate_decision_payload(payload)
    store.save_run(payload, validate=True)
    return payload["holdings"][0], hv


def _seed_run(store, as_of, run_id, name, profile, prior):
    """First run of a sequence, with an explicit persisted prior decision."""
    hv = Hysteresis()
    payload = decide_all(_foundation(as_of, run_id, name, profile),
                         apply_hysteresis=True,
                         history={name: {"decision": prior["decision"],
                                         "composite_score": prior["composite_score"],
                                         "as_of": prior["as_of"]}},
                         hysteresis=hv)
    validate_decision_payload(payload)
    store.save_run(payload, validate=True)
    return payload["holdings"][0], hv


@pytest.fixture()
def store():
    s = RunStore()          # conftest._tmp_store points STORE_PATH at tmp_path
    yield s
    s.close()


# --- the synthetic instruments really do sit in the bands the tests assume ----

def test_synthetic_instruments_have_the_expected_g4_bands():
    low = decide_all(_foundation(D1, "lo", "LOW INST", _LOW), apply_hysteresis=False)
    high = decide_all(_foundation(D1, "hi", "HIGH INST", _HIGH), apply_hysteresis=False)
    lo, hi = low["holdings"][0], high["holdings"][0]
    assert lo["stage1"]["fired"] is False and lo["stage1"]["gates_fired"] == []
    assert hi["stage1"]["fired"] is False and hi["stage1"]["gates_fired"] == []
    assert lo["evidence"]["tier"] == "NORMAL" and lo["evidence"]["coverage"] == 1.0
    assert hi["evidence"]["tier"] == "NORMAL" and hi["evidence"]["coverage"] == 1.0
    assert band_of(lo["composite_score"]) == "HOLD"
    assert band_of(hi["composite_score"]) == "TRIM"


# --- A. WATCH prior + current HOLD -------------------------------------------
#
# The run that restores the persisted WATCH prior IS observation 1 of the new
# band, so it exposes pending {band: HOLD, count: 1}. The next distinct as_of is
# observation 2 and commits. That is exactly Freeze §6: "composite must sit in
# the new band for N = 2 consecutive runs (distinct as_of dates)".

PRIOR_WATCH = {"decision": "WATCH", "composite_score": 14.9, "as_of": "2026-08-31"}


def test_a_first_distinct_run_keeps_watch_and_exposes_pending_1(store):
    h, hv = _seed_run(store, D1, "a0", "LOW INST", _LOW, PRIOR_WATCH)
    assert h["decision"] == "WATCH"                       # retained, N=2 not yet met
    assert band_of(h["composite_score"]) == "HOLD"        # current G4 band disagrees
    assert h["previous_run"]["pending"] == {"band": "HOLD", "count": 1}
    assert hv.state["LOW INST"]["pending"] == {"band": "HOLD", "count": 1}


def test_a_second_distinct_run_resolves_watch_to_hold(store):
    _seed_run(store, D1, "b0", "LOW INST", _LOW, PRIOR_WATCH)
    second, hv = _run(store, D2, "b1", "LOW INST", _LOW)
    assert second["decision"] == "HOLD"                   # N=2 satisfied -> committed
    assert hv.state["LOW INST"]["pending"] is None
    assert "pending" not in second["previous_run"]        # omitted when null
    assert second["previous_run"]["decision"] == "WATCH"  # reporting meaning preserved


def test_a_full_sequence_watch_then_hold_then_stable(store):
    first, _ = _seed_run(store, D1, "c0", "LOW INST", _LOW, PRIOR_WATCH)
    seq = [first["decision"]]
    seq += [_run(store, d, f"c{i}", "LOW INST", _LOW)[0]["decision"]
            for i, d in enumerate((D2, D3, D4), start=1)]
    assert seq == ["WATCH", "HOLD", "HOLD", "HOLD"]


# --- B. same as_of must not increment N=2 ------------------------------------

def test_b_same_as_of_does_not_increment_the_counter(store):
    _seed_run(store, D1, "d0", "LOW INST", _LOW, PRIOR_WATCH)   # observation 1
    again, hv = _run(store, D1, "d1", "LOW INST", _LOW)         # SAME as_of
    assert again["decision"] == "WATCH"
    assert hv.state["LOW INST"]["pending"] == {"band": "HOLD", "count": 1}
    distinct, _ = _run(store, D2, "d2", "LOW INST", _LOW)       # distinct as_of
    assert distinct["decision"] == "HOLD"


def test_b_same_as_of_unit_level():
    h = Hysteresis()
    h.seed("X", "WATCH", 14.9, D1.isoformat())
    assert h.apply("X", "HOLD", 14.9, D2) == "WATCH"
    assert h.apply("X", "HOLD", 14.9, D2) == "WATCH"      # same date, still 1
    assert h.state["X"]["pending"] == {"band": "HOLD", "count": 1}
    assert h.apply("X", "HOLD", 14.9, D3) == "HOLD"       # distinct date commits


# --- C. survives save_run / new RunStore / previous_holdings / new seed -------

def test_c_pending_survives_a_full_store_round_trip(tmp_path):
    from app import config as cfg
    cfg.STORE_PATH = tmp_path / "engine.db"

    s1 = RunStore()
    first, _ = _seed_run(s1, D1, "e0", "LOW INST", _LOW, PRIOR_WATCH)
    assert first["previous_run"]["pending"] == {"band": "HOLD", "count": 1}
    prior_composite = first["composite_score"]
    s1.close()                                            # <-- process ends

    s2 = RunStore()                                       # brand new connection
    history = s2.previous_holdings()
    assert history["LOW INST"]["pending"] == {"band": "HOLD", "count": 1}
    hv = Hysteresis()                                     # brand new Hysteresis
    payload = decide_all(_foundation(D2, "e1", "LOW INST", _LOW),
                         apply_hysteresis=True, history=history, hysteresis=hv)
    s2.close()

    h = payload["holdings"][0]
    assert h["decision"] == "HOLD"                        # committed after the restart
    assert hv.state["LOW INST"]["pending"] is None
    assert h["previous_run"]["decision"] == "WATCH"
    assert h["previous_run"]["composite_score"] == prior_composite


def test_c_get_prev_carries_pending_and_omits_it_when_null():
    h = Hysteresis()
    h.seed("X", "WATCH", 14.9, D1.isoformat())
    assert "pending" not in h.get_prev("X")               # omitted when null
    h.apply("X", "HOLD", 14.9, D2)
    assert h.get_prev("X")["pending"] == {"band": "HOLD", "count": 1}


# --- D. every normal transition still needs two distinct as_of runs ----------

@pytest.mark.parametrize("prior,score,enter_at,target", [
    ("HOLD", 45.0, 45.0, "WATCH"),       # HOLD  -> WATCH  (enter >= 31)
    ("WATCH", 60.0, 60.0, "TRIM"),       # WATCH -> TRIM   (enter >= 56)
    ("TRIM", 80.0, 80.0, "HARVEST"),     # TRIM  -> HARVEST(enter >= 76)
    ("HARVEST", 60.0, 60.0, "TRIM"),     # HARVEST -> TRIM (revert < 72)
    ("WATCH", 14.9, 14.9, "HOLD"),       # WATCH -> HOLD   (revert < 28)
    ("TRIM", 45.0, 45.0, "WATCH"),       # TRIM  -> WATCH  (revert < 52)
])
def test_d_restored_pending_commits_on_the_second_distinct_run(
        prior, score, enter_at, target):
    h = Hysteresis()
    h.seed("X", prior, score, D1.isoformat())
    assert h.apply("X", band_of(enter_at), enter_at, D2) == prior
    assert h.state["X"]["pending"] == {"band": target, "count": 1}
    # restart: only the persisted triple + pending are available
    restored = h.get_prev("X")
    h2 = Hysteresis()
    h2.seed("X", restored["decision"], restored["composite_score"],
            restored["as_of"], restored.get("pending"))
    assert h2.state["X"]["pending"] == {"band": target, "count": 1}
    assert h2.apply("X", band_of(enter_at), enter_at, D3) == target


@pytest.mark.parametrize("prior,score", [
    ("HOLD", 45.0), ("WATCH", 60.0), ("TRIM", 80.0), ("HARVEST", 60.0),
    ("WATCH", 14.9), ("TRIM", 45.0),
])
def test_d_without_a_restored_pending_the_first_run_never_commits(prior, score):
    h = Hysteresis()
    h.seed("X", prior, score, D1.isoformat())             # legacy: no pending
    assert h.apply("X", band_of(score), score, D2) == prior
    assert h.state["X"]["pending"]["count"] == 1


def test_d_thresholds_are_unchanged():
    t = Hysteresis.transition
    assert (t("HOLD", 30), t("HOLD", 31)) == ("HOLD", "WATCH")
    assert (t("WATCH", 28), t("WATCH", 27)) == ("WATCH", "HOLD")
    assert (t("WATCH", 55), t("WATCH", 56)) == ("WATCH", "TRIM")
    assert (t("TRIM", 52), t("TRIM", 51)) == ("TRIM", "WATCH")
    assert (t("TRIM", 75), t("TRIM", 76)) == ("TRIM", "HARVEST")
    assert (t("HARVEST", 72), t("HARVEST", 71)) == ("HARVEST", "TRIM")


def test_d_watch_to_trim_commits_end_to_end_over_two_runs(store):
    first, _ = _seed_run(store, D1, "f0", "HIGH INST", _HIGH,
                         {"decision": "WATCH", "composite_score": 31.2,
                          "as_of": "2026-08-31"})
    assert band_of(first["composite_score"]) == "TRIM"
    assert first["decision"] == "WATCH"
    assert first["previous_run"]["pending"] == {"band": "TRIM", "count": 1}
    second, hv = _run(store, D2, "f1", "HIGH INST", _HIGH)
    assert second["decision"] == "TRIM"
    assert hv.state["HIGH INST"]["pending"] is None


# --- E. a fired Stage-1 EXIT still bypasses hysteresis immediately ------------

def test_e_gate_exit_bypasses_immediately_and_clears_pending():
    h = Hysteresis()
    h.seed("X", "WATCH", 31.2, D1.isoformat())
    h.apply("X", "TRIM", 60.0, D2)
    assert h.state["X"]["pending"] == {"band": "TRIM", "count": 1}
    assert h.bypass("X", "EXIT", 60.0, D3) == "EXIT"
    assert h.state["X"]["decision"] == "EXIT"
    assert h.state["X"]["pending"] is None
    assert "pending" not in h.get_prev("X")


def test_e_gate_bypass_end_to_end_uses_the_bundled_g1_instrument(foundation):
    from app.pipeline import decide_on_foundation
    store = RunStore()
    history = {"Ashoka Buildcon": {"decision": "WATCH", "composite_score": 31.2,
                                   "as_of": D1.isoformat(),
                                   "pending": {"band": "TRIM", "count": 1}}}
    p = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
    store.save_run(p, validate=True)
    a = next(h for h in p["holdings"] if h["instrument"] == "Ashoka Buildcon")
    assert a["decision"] == "EXIT"                        # immediate, no N=2 wait
    assert a["stage1"]["fired"] is True and "G1_governance" in a["stage1"]["gates_fired"]
    assert "pending" not in (a["previous_run"] or {})     # bypass cleared it
    store.close()


# --- F. prior EXIT + no current Stage-1 EXIT (certified CR-024 semantics) -----

def test_f_prior_exit_from_persisted_history_reenters_g4_immediately():
    h = Hysteresis()
    h.seed("X", "EXIT", 69.0, D1.isoformat())             # restored from a run payload
    assert h.apply("X", "WATCH", 31.2, D2) == "WATCH"     # adopts the current band at once
    assert h.state["X"]["decision"] == "WATCH"
    assert h.state["X"]["pending"] is None                # no N=2 wait on re-entry


def test_f_normal_n2_resumes_after_exit_readoption():
    h = Hysteresis()
    h.seed("X", "EXIT", 69.0, D1.isoformat())
    assert h.apply("X", "WATCH", 31.2, D2) == "WATCH"
    assert h.apply("X", "TRIM", 60.0, D3) == "WATCH"      # now N=2 applies again
    assert h.state["X"]["pending"] == {"band": "TRIM", "count": 1}
    restored = h.get_prev("X")
    h2 = Hysteresis()
    h2.seed("X", restored["decision"], restored["composite_score"],
            restored["as_of"], restored.get("pending"))
    assert h2.apply("X", "TRIM", 60.0, D4) == "TRIM"


def test_f_prior_exit_never_persists_a_pending_counter(store):
    first, hv = _seed_run(store, D1, "g0", "LOW INST", _LOW,
                          {"decision": "EXIT", "composite_score": 69.0,
                           "as_of": "2026-08-31"})
    assert first["decision"] == "HOLD"                    # band adopted on the first run
    assert hv.state["LOW INST"]["pending"] is None
    assert "pending" not in (first["previous_run"] or {})


# --- G. legacy records without pending stay readable and safe -----------------

def test_g_legacy_three_field_record_defaults_to_pending_none():
    h = Hysteresis()
    h.seed("X", "WATCH", 14.9, D1.isoformat())            # no pending argument at all
    assert h.state["X"]["pending"] is None
    assert h.apply("X", "HOLD", 14.9, D2) == "WATCH"      # conservative: needs 2 runs
    assert h.state["X"]["pending"] == {"band": "HOLD", "count": 1}


def test_g_malformed_pending_is_discarded_not_trusted():
    for bad in (None, {}, {"band": "HOLD"}, {"band": "NOPE", "count": 1},
                {"band": "HOLD", "count": 0}, {"band": "HOLD", "count": "1"},
                {"band": "HOLD", "count": True}, "HOLD", 7):
        h = Hysteresis()
        h.seed("X", "WATCH", 14.9, D1.isoformat(), bad)
        assert h.state["X"]["pending"] is None, bad


def test_g_previous_holdings_omits_pending_for_legacy_payloads(store):
    from app.pipeline import decide_on_foundation
    p = decide_on_foundation(_foundation(D1, "h0", "LOW INST", _LOW),
                             apply_hysteresis=False)      # no history at all
    store.save_run(p, validate=True)
    history = store.previous_holdings()
    assert "LOW INST" in history
    assert "pending" not in history["LOW INST"]
    assert set(history["LOW INST"]) == {"decision", "composite_score", "as_of"}


def test_g_historical_payload_shapes_remain_readable(store):
    import json
    legacy = {"run_id": "legacy", "as_of": D1.isoformat(), "holdings": [
        {"instrument": "OLD", "decision": "WATCH", "composite_score": 14.9}]}
    store._conn.execute(
        "INSERT INTO runs (run_id, as_of, engine_version, policy_version, input_hash,"
        " content_hash, payload_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
        ("legacy", D1.isoformat(), "1.0.0", 1, "i", "h",
         json.dumps(legacy), "2026-09-01T00:00:00+00:00"))
    store._conn.commit()
    history = store.previous_holdings()
    assert history["OLD"] == {"decision": "WATCH", "composite_score": 14.9,
                              "as_of": D1.isoformat()}


def test_g_payload_carrying_pending_passes_validation(store):
    h, _ = _seed_run(store, D1, "i0", "LOW INST", _LOW, PRIOR_WATCH)
    assert h["previous_run"]["pending"] == {"band": "HOLD", "count": 1}
    validate_decision_payload(store.latest_run())         # raises if the shape is wrong


# --- H. no fixture mutation is required / golden output is untouched ---------

def test_h_no_history_means_no_previous_run_and_no_pending_anywhere():
    """`run_engine` (the golden/no-history path) must stay byte-identical."""
    import json
    from pathlib import Path
    fix = Path(__file__).resolve().parent.parent / "fixtures"
    payload = run_engine(fix / "portfolio.csv", fix / "screener.csv",
                         fix / "ledger.csv", as_of=date(2026, 8, 22))
    for holding in payload["holdings"]:
        assert holding["previous_run"] is None
        assert "pending" not in holding
    assert "pending" not in json.dumps(payload)


def test_h_what_if_never_carries_pending_forward():
    """what-if runs with apply_hysteresis=False and no history."""
    from app.pipeline import decide_on_foundation
    p = decide_on_foundation(_foundation(D2, "j0", "LOW INST", _LOW),
                             apply_hysteresis=False)
    h = p["holdings"][0]
    assert h["decision"] == band_of(h["composite_score"])  # raw band, no hysteresis
    assert h["previous_run"] is None
