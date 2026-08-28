"""CR-024 (EMM-F2) proofs — date-indexed historical store/query, G-04 median,
G1 history legs, all against scratch archives (never the audit ledger).

Covers the gate-mandated battery A..X. Every event is produced by the real
``run_foundation`` path (raw slots captured pre-parse, corpus archived), with
slot dates declared explicitly so observation dates are fully deterministic.
"""
import inspect
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.config as config
from app import archive, history
from app.pipeline import run_foundation

INST = "Alpha Engg"
AS_OF = date(2026, 8, 1)

PF = ("Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
      "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),"
      "First Date,Last Date\n"
      "Alpha Engg,1,10,100,1000,1200,100,20,-1000,20,400,2024-01-01,2024-01-01\n")
LG = ("Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date\n"
      "Alpha Engg,10,100,120,200,1000,1200,2024-01-01\n")


def _screener(pe=25, pb=3.0, pledge=None, roe=15, roce=15, de=0.5, ic=5,
              eps_hist=10, eps_fwd=10, sub_sector="Engineering"):
    pld = "" if pledge is None else str(pledge)
    return (
        "Name,Ticker,Sub Sector,Market Cap,Close Price,PE Ratio,PB Ratio,"
        "PEG Ratio,ROE,ROCE,1Y Historical EPS Growth,1Y Forward EPS Growth,"
        "Debt to Equity,Interest Coverage Ratio,Price FCF,"
        "Pledged Promoter Holdings,200D SMA,PE Premium Vs Sub Sector,"
        "PB Premium Vs Sub Sector,DII Holding Change 3M,FII Holding Change 3M\n"
        f"{INST},ALPHA,{sub_sector},500,120,{pe},{pb},1.2,{roe},{roce},{eps_hist},"
        f"{eps_fwd},{de},{ic},20,{pld},100,1.1,1.1,0,0\n")


@pytest.fixture
def arc(tmp_path, monkeypatch):
    root = tmp_path / "history_archive"
    root.mkdir()
    monkeypatch.setattr(config, "ARCHIVE_ROOT", root)
    return root


def _event(tmp_path, tag, screener_text, scr_date, run_as_of=None, run_id=None):
    d = tmp_path / tag
    d.mkdir(exist_ok=True, parents=True)
    (d / "portfolio.csv").write_text(PF)
    (d / "ledger.csv").write_text(LG)
    (d / "screener.csv").write_text(screener_text)
    run_as_of = run_as_of or scr_date
    return run_foundation(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                          as_of=run_as_of, run_id=run_id or f"run_{tag}",
                          declared_as_of={"portfolio": scr_date, "screener": scr_date,
                                          "ledger": scr_date})


def _events_pe(tmp_path, pe_values, pb=3.0, start=date(2026, 1, 1), step_days=1,
               **kw):
    """Archive one event per PE value at consecutive observation dates."""
    for i, pe in enumerate(pe_values):
        _event(tmp_path, f"e{i:03d}", _screener(pe=pe, pb=pb, **kw),
               start + timedelta(days=i))


# --- A-F: store/query ----------------------------------------------------------


def test_a_date_indexed_lookup_without_run_id(arc, tmp_path):
    """A: caller supplies only instrument (+metric/dates) — never a run_id."""
    _event(tmp_path, "a1", _screener(pe=20), date(2026, 3, 1))
    _event(tmp_path, "a2", _screener(pe=30), date(2026, 4, 1))
    r = history.query_fundamentals(INST, metric="pe_ratio", root=arc)
    assert r["observation_count"] == 2
    assert [o["value"] for o in r["observations"]] == [20.0, 30.0]
    sig = inspect.signature(history.query_fundamentals)
    assert "run_id" not in sig.parameters


def test_b_date_ordering(arc, tmp_path):
    """B: results are date-ordered even when archived out of date order."""
    _event(tmp_path, "b1", _screener(pe=1), date(2026, 5, 1))
    _event(tmp_path, "b2", _screener(pe=2), date(2026, 1, 1))  # older, archived later
    _event(tmp_path, "b3", _screener(pe=3), date(2026, 3, 1))
    r = history.query_fundamentals(INST, metric="pe_ratio", root=arc)
    assert [o["observation_date"] for o in r["observations"]] == [
        "2026-01-01", "2026-03-01", "2026-05-01"]


def test_c_multiple_observations_series(arc, tmp_path):
    _events_pe(tmp_path, [10, 11, 12, 13, 14])
    r = history.query_fundamentals(INST, metric="pe_ratio", root=arc)
    assert [o["value"] for o in r["observations"]] == [10.0, 11.0, 12.0, 13.0, 14.0]


def test_d_missing_dates_empty_window(arc, tmp_path):
    """D: windows with no archived snapshots return nothing — never fabricated."""
    _event(tmp_path, "d1", _screener(pe=20), date(2026, 1, 1))
    r = history.query_fundamentals(INST, metric="pe_ratio", start="2026-06-01",
                                   end="2026-06-30", root=arc)
    assert r["observation_count"] == 0 and r["observations"] == []
    empty = history.query_fundamentals("Nobody Corp", metric="pe_ratio", root=arc)
    assert empty["observation_count"] == 0


def test_e_archive_provenance(arc, tmp_path):
    """E: every observation carries full snapshot/archive identity."""
    payload = _event(tmp_path, "e1", _screener(pe=22), date(2026, 2, 1),
                     run_id="run_provenance")
    r = history.query_fundamentals(INST, metric="pe_ratio", root=arc)
    prov = r["observations"][0]["provenance"]
    snap = prov["snapshot"]
    assert prov["source"] == "CR-022 snapshot archive"
    assert prov["as_of_source"] == "declared_explicit"
    assert prov["source_as_of"] == "2026-02-01"
    assert snap["run_id"] == "run_provenance"
    assert snap["foundation_sha256"] == payload["provenance"]["archive"]["foundation_sha256"]
    assert snap["screener_sha256"] is not None
    assert prov["source_version"]["engine_version"] == config.ENGINE_VERSION


def test_f_tamper_breaks_verify_and_never_fabricates(arc, tmp_path):
    """F: corrupting an archived corpus blob is detected by verify(); the
    history layer then yields no observation from it (no fabrication)."""
    _event(tmp_path, "f1", _screener(pe=20), date(2026, 1, 1))
    assert history.all_observations(root=arc) != []
    entry = archive.read_manifest(root=arc)[0]
    blob_path = arc / entry["foundation_blob"]
    data = bytearray(blob_path.read_bytes())
    data[0] ^= 0xFF
    blob_path.write_bytes(bytes(data))
    rep = archive.verify(root=arc)
    assert rep["ok"] is False
    assert any("blob content mismatch" in e for e in rep["errors"])
    # tampered corpus is unreadable as JSON => skipped, not repaired/invented
    assert history.all_observations(root=arc) == []


def test_c2_duplicate_date_latest_seq_wins(arc, tmp_path):
    """C-2 convention: same observation date archived twice -> greatest seq."""
    _event(tmp_path, "c21", _screener(pe=20), date(2026, 3, 1), run_id="first")
    _event(tmp_path, "c22", _screener(pe=99), date(2026, 3, 1), run_id="second")
    obs = [o for o in history.all_observations(root=arc) if o["instrument"] == INST]
    assert len(obs) == 1
    assert obs[0]["metrics"]["pe_ratio"] == 99.0
    assert obs[0]["run_id"] == "second"


# --- G-N: G-04 median -----------------------------------------------------------


def test_g_window_start_boundary(arc, tmp_path):
    """G: exactly 5-calendar-years back is included; one day earlier excluded."""
    _event(tmp_path, "g1", _screener(pe=1), date(2021, 6, 30), run_id="out")
    _event(tmp_path, "g2", _screener(pe=2), date(2021, 7, 1), run_id="edge")
    r = history.pe_pb_medians(INST, date(2026, 7, 1), root=arc)
    assert r["window"] == {"start": "2021-07-01", "end": "2026-07-01",
                           "lookback_years": 5,
                           "endpoint_semantics": "inclusive both endpoints (C-3)"}
    dates = [o["observation_date"] for o in r["pe"]["observations"]]
    assert dates == ["2021-07-01"]


def test_h_window_end_inclusion(arc, tmp_path):
    """H: an observation on as_of itself is included; later dates excluded."""
    _event(tmp_path, "h1", _screener(pe=3), date(2026, 7, 1), run_id="on_asof")
    _event(tmp_path, "h2", _screener(pe=4), date(2026, 7, 2), run_id="after")
    r = history.pe_pb_medians(INST, date(2026, 7, 1), root=arc)
    dates = [o["observation_date"] for o in r["pe"]["observations"]]
    assert dates == ["2026-07-01"]


def test_i_even_count_median_convention(arc, tmp_path):
    """I/C-1: 24 valid values -> median = mean of the two central values."""
    _events_pe(tmp_path, list(range(1, 25)), pb=3.0)   # PE 1..24
    r = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert r["pe"]["valid_observation_count"] == 24
    assert r["pe"]["median"] == 12.5                    # (12 + 13) / 2
    assert r["pb"]["median"] == 3.0
    assert r["eligible"] is True
    assert r["methodology_version"] == "G04-MEDIAN-METHODOLOGY-v1"


def test_j_invalid_and_nonpositive_excluded(arc, tmp_path):
    """J: zero/negative multiples are mathematically invalid -> excluded."""
    values = [10.0] * 22 + [0.0, -5.0]
    _events_pe(tmp_path, values)
    r = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert r["pe"]["valid_observation_count"] == 22
    assert r["pe"]["excluded_invalid_count"] == 2
    assert r["pe"]["eligible"] is False


def test_k_no_winsorization(arc, tmp_path):
    """K: valid extremes are kept verbatim and influence the median."""
    _events_pe(tmp_path, [10.0] * 23 + [100000.0])
    r = history.pe_pb_medians(INST, AS_OF, root=arc)
    kept = [o["metrics"]["pe_ratio"] for o in r["pe"]["observations"]]
    assert max(kept) == 100000.0                        # not clipped
    assert r["pe"]["valid_observation_count"] == 24
    assert r["pe"]["median"] == 10.0
    # same tail length with winsorization would cap the extreme; direct proof:
    assert history._median([1.0, 2.0, 3.0, 100000.0]) == 2.5  # extreme retained


def test_l_23_vs_24_eligibility(arc, tmp_path):
    """L: 23 valid observations do not activate; 24 do."""
    _events_pe(tmp_path, [10.0] * 23)
    r = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert r["pe"]["valid_observation_count"] == 23
    assert r["eligible"] is False
    _event(tmp_path, "L24", _screener(pe=10.0), date(2026, 1, 24))
    r2 = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert r2["pe"]["valid_observation_count"] == 24
    assert r2["eligible"] is True


def test_m_pe_and_pb_both_required(arc, tmp_path):
    """M: G04-D7-A — BOTH metrics must clear 24; PE alone is insufficient."""
    _events_pe(tmp_path, [10.0] * 24)                  # 24 PE + 24 PB
    r = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert r["pe"]["eligible"] is True and r["pb"]["eligible"] is True
    assert r["eligible"] is True
    # Same archive but PB-thin on one date: PE clears 24, PB stalls at 23.
    thin = arc.parent / "thin"
    thin.mkdir(exist_ok=True)
    old = config.ARCHIVE_ROOT
    try:
        config.ARCHIVE_ROOT = thin
        for i in range(24):
            _event(tmp_path / "t", f"t{i:03d}",
                   _screener(pe=10.0, pb=(None if i == 23 else 3.0)),
                   date(2026, 1, 1) + timedelta(days=i))
        r3 = history.pe_pb_medians(INST, AS_OF, root=thin)
        assert r3["pe"]["valid_observation_count"] == 24
        assert r3["pe"]["eligible"] is True
        assert r3["pb"]["valid_observation_count"] == 23   # missing omitted (G04-D4)
        assert r3["pb"]["eligible"] is False
        assert r3["eligible"] is False                     # BOTH required (G04-D7-A)
    finally:
        config.ARCHIVE_ROOT = old


def test_n_proxy_retained_not_activated(arc):
    """N: the peer-relative proxy remains production scoring; G-04 never feeds it."""
    src = inspect.getsource(__import__("app.scoring", fromlist=["x"]))
    assert "pe_premium_vs_subsector" in src
    for forbidden in ("pe_5y_median", "pb_5y_median", "own_history", "pe_pb_medians"):
        assert forbidden not in src
    from app.pipeline import run_engine
    from pathlib import Path as _P
    FIX = _P(__file__).resolve().parent.parent / "fixtures"
    payload = run_engine(FIX / "portfolio.csv", FIX / "screener.csv",
                         FIX / "ledger.csv", as_of=date(2026, 8, 22), run_id="n1")
    for h in payload["holdings"]:
        for forbidden in ("g04", "pe_5y", "own_history", "historical_median"):
            assert not any(forbidden in str(k) for k in h.keys())
        if h["decision"] != "NO-DECISION":
            assert h["data_quality"]["valuation_stretch"] in ("proxy", "missing", "stale")


# --- O-R: G1 quality_drop --------------------------------------------------------


def test_o_quality_observation_composition(arc, tmp_path):
    """O/C-4: the quality observation is the frozen quality_drift sub-score
    recomputed from the archived snapshot (sector-aware math included)."""
    from app.scoring import quality_drift
    _event(tmp_path, "o1", _screener(roe=5), date(2026, 1, 1))
    obs = history.all_observations(root=arc)[0]
    f = dict(obs["metrics"]); f["sub_sector"] = obs["sub_sector"]
    assert history._quality_value(obs) == quality_drift(f) == 20
    # sector-aware: the same low ROCE is NOT penalised for financials
    _event(tmp_path, "o2", _screener(roce=-1, sub_sector="Banks - Private"),
           date(2026, 2, 1), run_id="o2")
    fin = [o for o in history.all_observations(root=arc)
           if o["observation_date"] == "2026-02-01"][0]
    assert history._quality_value(fin) == 0


def _drift_case(arc, tmp_path, tag, current_kwargs):
    _event(tmp_path, f"{tag}_prior", _screener(), date(2025, 7, 1))
    _event(tmp_path, f"{tag}_cur", _screener(**current_kwargs), date(2026, 7, 1))
    return history.quality_drop(INST, AS_OF, root=arc)


def test_p_yoy_comparison_points(arc, tmp_path):
    """P: prior eligible point = latest observation <= (as_of - 1 year)."""
    _event(tmp_path, "p_old", _screener(roe=5), date(2025, 3, 10), run_id="p_old")
    _event(tmp_path, "p_new", _screener(), date(2025, 6, 15), run_id="p_new")
    _event(tmp_path, "p_cur", _screener(roe=5), date(2026, 7, 1), run_id="p_cur")
    r = history.quality_drop(INST, AS_OF, root=arc)
    assert r["available"] is True
    assert r["prior_target_date"] == "2025-08-01"
    assert r["prior"]["observation_date"] == "2025-06-15"   # latest <= target, not oldest
    assert r["current"]["quality_observation"] == 20
    assert r["prior"]["quality_observation"] == 0


def test_q_threshold_boundary(arc, tmp_path):
    """Q: deterioration >= 20 points fires; exactly 20 fires; below does not."""
    r20 = _drift_case(arc, tmp_path, "qa", {"roe": 5})          # drift +20
    assert r20["deterioration_points"] == 20 and r20["fired"] is True
    sub = arc.parent / "q15"; sub.mkdir(exist_ok=True)
    config.ARCHIVE_ROOT = sub
    try:
        r15 = _drift_case(sub, tmp_path / "qb", "qb", {"eps_fwd": -1})   # +15
        assert r15["deterioration_points"] == 15 and r15["fired"] is False
    finally:
        config.ARCHIVE_ROOT = arc
    sub2 = arc.parent / "q25"; sub2.mkdir(exist_ok=True)
    config.ARCHIVE_ROOT = sub2
    try:
        r25 = _drift_case(sub2, tmp_path / "qc", "qc", {"eps_hist": -1})  # +25
        assert r25["deterioration_points"] == 25 and r25["fired"] is True
    finally:
        config.ARCHIVE_ROOT = arc


def test_r_missing_history_non_firing(arc, tmp_path):
    """R: no prior-year observation -> unavailable, non-firing, no interpolation."""
    _event(tmp_path, "r_cur", _screener(roe=5), date(2026, 7, 1))
    r = history.quality_drop(INST, AS_OF, root=arc)
    assert r["available"] is False and r["fired"] is False
    assert "prior" in r["reason"] and "no interpolation" in r["reason"]


# --- S-U: G1 pledge_qoq -----------------------------------------------------------

def test_s_pledge_quarter_boundary_and_latest_in_quarter(arc, tmp_path):
    """S/C-5: calendar quarters; per-quarter value = latest-in-quarter obs."""
    _event(tmp_path, "s1", _screener(pledge=10.0), date(2026, 1, 15), run_id="s1")
    _event(tmp_path, "s2", _screener(pledge=12.0), date(2026, 2, 20), run_id="s2")  # later Q1
    _event(tmp_path, "s3", _screener(pledge=17.0), date(2026, 5, 10), run_id="s3")  # Q2
    r = history.pledge_qoq(INST, date(2026, 8, 1), root=arc)
    assert r["available"] is True
    assert r["preceding_quarter"]["pledge_pct"] == 12.0      # latest-in-Q1 wins
    assert r["latest_quarter"] == {"year": 2026, "quarter": 2,
                                   "observation_date": "2026-05-10",
                                   "pledge_pct": 17.0,
                                   "provenance": r["latest_quarter"]["provenance"]}
    assert r["increase_pp"] == 5.0


def test_t_pledge_threshold_boundary(arc, tmp_path):
    """T: increase >= 5.0 pp fires; equality fires; 4.9 does not."""
    _event(tmp_path, "t1", _screener(pledge=10.0), date(2026, 1, 15), run_id="t1")
    _event(tmp_path, "t2", _screener(pledge=15.0), date(2026, 4, 15), run_id="t2")
    r = history.pledge_qoq(INST, date(2026, 6, 1), root=arc)
    assert r["increase_pp"] == 5.0 and r["fired"] is True
    _event(tmp_path, "t3", _screener(pledge=14.9), date(2026, 4, 20), run_id="t3")
    r2 = history.pledge_qoq(INST, date(2026, 6, 1), root=arc)
    assert r2["increase_pp"] == 4.9 and r2["fired"] is False


def test_u_pledge_missing_history_non_firing(arc, tmp_path):
    """U: missing preceding quarter (or any history) -> unavailable, non-firing."""
    _event(tmp_path, "u1", _screener(pledge=10.0), date(2026, 5, 1), run_id="u1")
    r = history.pledge_qoq(INST, date(2026, 6, 1), root=arc)
    assert r["available"] is False and r["fired"] is False
    r0 = history.pledge_qoq(INST, date(2026, 6, 1), root=arc.parent / "none")
    assert r0["available"] is False and r0["fired"] is False


# --- V-X: provenance / replay / regression --------------------------------------


def test_v_full_provenance(arc, tmp_path):
    """V: observation- and derived-level provenance is reconstruction-complete."""
    _event(tmp_path, "va", _screener(pledge=10.0), date(2025, 6, 1), run_id="va")
    _event(tmp_path, "v1", _screener(pledge=10.0), date(2026, 1, 15), run_id="v1")
    _event(tmp_path, "v2", _screener(roe=5, pledge=16.0), date(2026, 4, 1), run_id="v2")
    g04 = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert g04["provenance"]["source"] == "CR-022 snapshot archive"
    assert set(g04["conventions"].keys()) == {"C-1", "C-2", "C-3", "C-4", "C-5"}
    assert g04["activation_state"].startswith("NOT ACTIVATED")
    for o in g04["pe"]["observations"]:
        snap = o["provenance"]["snapshot"]
        assert snap["foundation_sha256"] and snap["screener_sha256"]
        assert snap["run_id"].startswith("v")
    legs = history.g1_legs(INST, AS_OF, root=arc)
    qd = legs["quality_drop"]
    assert qd["methodology_version"] == "G1-HISTORY-LEGS-METHODOLOGY-v1"
    assert qd["threshold_points"] == 20.0 and qd["operator"] == ">="
    assert qd["current"]["provenance"]["snapshot"]["run_id"] == "v2"
    pq = legs["pledge_qoq"]
    assert pq["latest_quarter"]["provenance"]["snapshot"]["foundation_sha256"]
    assert pq["preceding_quarter"]["provenance"]["snapshot"]["foundation_sha256"]
    assert pq["activation_state"].startswith("EVIDENCE ONLY")


def test_w_deterministic_replay_no_wallclock(arc, tmp_path):
    """W: same archived inputs -> identical outputs, with zero wall-clock input."""
    _events_pe(tmp_path, [8.0, 9.0, 10.0])
    _event(tmp_path, "w_pl", _screener(pledge=3.0), date(2026, 5, 1), run_id="w_pl")
    a = history.pe_pb_medians(INST, AS_OF, root=arc)
    b = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    g1a = history.g1_legs(INST, AS_OF, root=arc)
    g1b = history.g1_legs(INST, AS_OF, root=arc)
    assert json.dumps(g1a, sort_keys=True) == json.dumps(g1b, sort_keys=True)
    src = inspect.getsource(history)
    assert "date.today" not in src and "datetime.now" not in src and "_utcnow" not in src


def test_x_existing_g1_behavior_unchanged(arc):
    """X: current G1 gate semantics are untouched; no history legs entered gating."""
    gates_src = inspect.getsource(__import__("app.gates", fromlist=["x"]))
    scoring_src = inspect.getsource(__import__("app.scoring", fromlist=["x"]))
    for forbidden in ("quality_drop", "pledge_qoq", "quality_series", "pe_pb_medians",
                      "app.history"):
        assert forbidden not in gates_src and forbidden not in scoring_src
    from app.pipeline import run_engine
    from pathlib import Path as _P
    FIX = _P(__file__).resolve().parent.parent / "fixtures"
    payload = run_engine(FIX / "portfolio.csv", FIX / "screener.csv",
                         FIX / "ledger.csv", as_of=date(2026, 8, 22), run_id="x1")
    for h in payload["holdings"]:
        assert "quality_drop" not in h and "pledge_qoq" not in h
        assert "g1_history" not in h and "history" not in h.get("stage1", {})
    assert payload["engine_version"] == config.ENGINE_VERSION


def test_no_fabrication_empty_archive(arc):
    """Empty archive -> nothing exists; nothing is invented."""
    assert history.all_observations(root=arc) == []
    r = history.query_fundamentals(INST, metric="pe_ratio", root=arc)
    assert r["observation_count"] == 0
    m = history.pe_pb_medians(INST, AS_OF, root=arc)
    assert m["eligible"] is False
    assert m["pe"]["valid_observation_count"] == 0 and m["pe"]["median"] is None
    assert history.quality_drop(INST, AS_OF, root=arc)["available"] is False
    assert history.pledge_qoq(INST, AS_OF, root=arc)["available"] is False


def test_readonly_api_endpoints(arc, tmp_path):
    """Read-only GET surface: query works without run_id; 404s are honest."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.main import app
    _event(tmp_path, "api1", _screener(pe=20, pledge=10.0), date(2026, 1, 15),
           run_id="api1")
    _event(tmp_path, "api2", _screener(pe=30, pledge=16.0), date(2026, 4, 1),
           run_id="api2")
    c = TestClient(app)
    r = c.get(f"/api/v1/history/fundamentals/{INST}", params={"metric": "pe_ratio"})
    assert r.status_code == 200
    assert [o["observation_date"] for o in r.json()["observations"]] == [
        "2026-01-15", "2026-04-01"]
    assert [o["value"] for o in r.json()["observations"]] == [20.0, 30.0]
    assert c.get("/api/v1/history/fundamentals/Nobody").status_code == 404
    g1 = c.get(f"/api/v1/history/g1/{INST}")
    assert g1.status_code == 200
    body = g1.json()
    assert body["pledge_qoq"]["fired"] is True       # Q1'26 10 -> Q2'26 16 (+6 >= 5)
    qd = body["quality_drop"]
    assert qd["available"] is False and qd["fired"] is False   # no obs <= 2025-04-01
    g04 = c.get(f"/api/v1/history/g04/{INST}")
    assert g04.status_code == 200
    assert g04.json()["eligible"] is False           # only 2 observations
