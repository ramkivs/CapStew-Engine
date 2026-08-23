"""Phase 2 implementation audit — items A–J (reviewer audit gate) + adversarial tests.

Each test maps to a reviewer audit question:
  A determinism across processes   F golden trilogy + combinations
  B hysteresis survives restart    G trim adversarial cases
  C G0 blocks only affected        H behavior is caution-only
  D eligibility before renormalise I what-if isolation
  E confidence integer/rounding    J /run == /decisions
Plus: proxy-vs-missing distinction, gate override mid-history.
"""
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent

from app.pipeline import decide_on_foundation, run_engine, run_foundation  # noqa: E402
from app.policy import load_policy  # noqa: E402

POLICY = load_policy()


def _run(as_of=date(2026, 8, 22)):
    return run_engine(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                      as_of=as_of)


def _h(p, name):
    return next(h for h in p["holdings"] if h["instrument"] == name)


def _files():
    return {
        "portfolio": ("portfolio.csv", (FIXDIR / "portfolio.csv").read_bytes(), "text/csv"),
        "screener": ("screener.csv", (FIXDIR / "screener.csv").read_bytes(), "text/csv"),
        "ledger": ("ledger.csv", (FIXDIR / "ledger.csv").read_bytes(), "text/csv"),
    }


def _lots(n=3, ltp=100.0, buys=(90.0, 95.0, 100.0), qty=100, ltcg=(False, False, False)):
    return [
        {"lot_id": i + 1, "qty": qty, "buy_price": buys[i % len(buys)], "ltp": ltp,
         "ltcg_eligible": ltcg[i % len(ltcg)]}
        for i in range(n)
    ]


# ---- A — determinism across processes ----

def test_a_determinism_cross_process():
    p = _run()
    script = ROOT / "scripts" / "hash_engine.py"
    outs = set()
    for _ in range(2):
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                           cwd=ROOT, timeout=120)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert outs == {p["content_hash"]}


# ---- B — hysteresis survives "restart" ----

def test_b_persistence_survives_restart(tmp_path):
    from app import config as cfg
    from app.store import RunStore
    cfg.STORE_PATH = tmp_path / "engine.db"
    f = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                       as_of=date(2026, 8, 22))
    p1 = decide_on_foundation(f, apply_hysteresis=False)
    s = RunStore()
    s.save_run(p1)
    # fresh connection == simulated process restart
    s2 = RunStore()
    latest = s2.latest_run()
    assert latest["content_hash"] == p1["content_hash"]
    assert [(h["instrument"], h["decision"]) for h in latest["holdings"]] == \
           [(h["instrument"], h["decision"]) for h in p1["holdings"]]


def test_b_hysteresis_derives_from_persisted_history(tmp_path):
    from app import config as cfg
    from app.store import RunStore
    cfg.STORE_PATH = tmp_path / "engine.db"
    f = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                       as_of=date(2026, 8, 22))
    s = RunStore()
    s.save_run(decide_on_foundation(f, apply_hysteresis=False))
    history = s.previous_holdings()
    assert "Larsen & Toubro" in history
    p2 = decide_on_foundation(f, apply_hysteresis=True, history=history)
    # previous_run now populated from persisted history
    lt = _h(p2, "Larsen & Toubro")
    assert lt["previous_run"] is not None
    assert lt["previous_run"]["decision"] == "HOLD"


# ---- C — G0 blocks only the affected instrument ----

def test_c_g0_blocks_only_affected_instrument():
    import csv
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for fn in ("portfolio.csv", "screener.csv", "ledger.csv"):
            (tmp / fn).write_bytes((FIXDIR / fn).read_bytes())
        rows = list(csv.DictReader(open(tmp / "ledger.csv", encoding="utf-8")))
        for r in rows:
            if r["Instrument"] == "Bank of Baroda":
                r["Buy Price"] = "999.00"
                break
        with open(tmp / "ledger.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        p = run_engine(tmp / "portfolio.csv", tmp / "screener.csv", tmp / "ledger.csv",
                       as_of=date(2026, 8, 22))
    assert _h(p, "Bank of Baroda")["decision"] == "NO-DECISION"
    assert _h(p, "Salasar Techno Engg")["decision"] == "TRIM"   # unaffected


# ---- D — eligibility before renormalisation ----

def test_d_insufficient_tier_caps_to_watch(foundation):
    h = _h(_run(), "AGI Greenpac")
    assert h["evidence"]["tier"] == "INSUFFICIENT"
    assert h["decision"] == "WATCH"
    assert h["evidence"]["critical_categories_missing"]


def test_d_normal_tier_not_capped(foundation):
    h = _h(_run(), "Salasar Techno Engg")
    assert h["evidence"]["tier"] == "NORMAL"


# ---- E — confidence integer + rounding ----

def test_e_confidence_is_integer_in_payload(foundation):
    for h in _run()["holdings"]:
        if h["confidence"] is not None:
            assert isinstance(h["confidence"], int)
            assert 20 <= h["confidence"] <= 95


# ---- F — golden trilogy + precedence (decision level) ----

def test_f_golden_trilogy(foundation):
    p = _run()
    s = _h(p, "Salasar Techno Engg"); a = _h(p, "Ashoka Buildcon"); lt = _h(p, "Larsen & Toubro")
    assert (s["decision"], s["stage1"]["winning_gate"]) == ("TRIM", "G2")
    assert (a["decision"], a["stage1"]["winning_gate"]) == ("EXIT", "G1")
    assert (lt["decision"], lt["stage1"]["winning_gate"]) == ("HOLD", "G3")


# ---- G — adversarial trim ----

def test_g_trim_one_lot_partial():
    from app.trim import sell_plan
    plan = sell_plan([{"lot_id": 1, "qty": 100, "buy_price": 80.0, "ltp": 100.0, "ltcg_eligible": False}],
                     40.0, POLICY, 0.35)
    assert [l["lot_id"] for l in plan["fifo_lots_to_sell"]] == [1]
    assert plan["fifo_lots_to_sell"][0]["qty"] == 40.0


def test_g_trim_below_target_does_not_sell():
    from app.trim import trim_s
    pos = {"alloc_pct": 2.0, "qty_held": 100, "current_value": 20000.0, "bucket": "micro"}
    policy = {**POLICY, "participation_position_pct": 100}
    plan = trim_s(pos, _lots(n=1, ltp=200.0, buys=[180.0], qty=100), policy, 1_000_000.0)
    assert plan["suggested_qty"] == 0.0


def test_g_trim_tiny_position_no_dust():
    from app.trim import trim_s
    pos = {"alloc_pct": 8.0, "qty_held": 30, "current_value": 3000.0, "bucket": "micro"}
    policy = {**POLICY, "participation_position_pct": 100}
    plan = trim_s(pos, _lots(n=1, ltp=100.0, buys=[80.0], qty=30), policy, 1_000_000.0)
    assert plan["suggested_qty"] == 0.0


def test_g_trim_cap_and_dust_conflict_resolves():
    from app.trim import trim_s
    pos = {"alloc_pct": 8.0, "qty_held": 100, "current_value": 10000.0, "bucket": "micro"}
    policy = {**POLICY, "participation_position_pct": 25, "min_position_value": 8000}
    plan = trim_s(pos, _lots(n=1, ltp=100.0, buys=[80.0], qty=100), policy, 1_000_000.0)
    assert plan["suggested_qty"] <= 25.0            # participation cap respected
    assert 100 - plan["suggested_qty"] >= 80.0      # dust floor respected


def test_g_trim_tax_boundary_ltcg_vs_stcg():
    from app.trim import sell_plan
    lots = [
        {"lot_id": 1, "qty": 100, "buy_price": 50.0, "ltp": 100.0, "ltcg_eligible": True},
        {"lot_id": 2, "qty": 100, "buy_price": 60.0, "ltp": 100.0, "ltcg_eligible": False},
        {"lot_id": 3, "qty": 100, "buy_price": 70.0, "ltp": 100.0, "ltcg_eligible": False},
    ]
    plan = sell_plan(lots, 150.0, POLICY, 0.35)
    tb = plan["tax_breakdown"]
    assert tb["ltcg_gain"] == 5000.0   # lot 1 fully (100 shares)
    assert tb["stcg_gain"] == 2000.0   # lot 2 partially (50 shares)


# ---- H — behavior flag is caution-only, never an exit by itself ----

def test_h_averaging_flag_is_caution_not_exit():
    from app.decision import decide_instrument
    from app.hysteresis import Hysteresis
    asof = date(2026, 8, 22)
    pos = {"instrument": "SYNTH", "ticker": "SYNTH", "bucket": "micro", "alloc_pct": 2.0,
           "qty_held": 40, "current_value": 4000.0, "in_screener": False,
           "pledge_pct": 0.0, "fundamentals": None}
    lots = []
    for i in range(4):
        lots.append({
            "lot_id": i + 1, "instrument": "SYNTH",
            "trade_date": (asof - timedelta(days=100 - i * 10)).isoformat(),
            "qty": 10, "buy_price": Decimal(110 - i), "ltp": Decimal(100),
            "pnl": Decimal(-(110 - i - 100) * 10),
            "days_to_ltcg": 200, "ltcg_eligible": False,
        })
    h = decide_instrument(pos, lots, POLICY, 1_000_000.0, asof, Hysteresis(), [], set(), False)
    assert h["behavioral_flags"][0].startswith("averaging")
    assert h["decision"] != "EXIT"          # caution flag, not a gate


# ---- I — what-if isolation ----

def test_i_what_if_does_not_persist_or_mutate_policy(tmp_path, monkeypatch):
    from app import config as cfg
    from app.store import RunStore
    import app.policy as pol
    cfg.STORE_PATH = tmp_path / "engine.db"
    monkeypatch.setattr(pol, "POLICY_PATH", tmp_path / "policy.yaml")
    import yaml
    (tmp_path / "policy.yaml").write_text(yaml.safe_dump(POLICY))

    f = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                       as_of=date(2026, 8, 22))
    base = decide_on_foundation(f, apply_hysteresis=False)
    s = RunStore(); s.save_run(base)
    n_before = s.count()
    policy_before = (tmp_path / "policy.yaml").read_bytes()

    wi = decide_on_foundation(f, policy_overrides={"max_single_stock_pct": 50.0,
                                                   "rebalance_trigger_multiple": 10.0},
                              apply_hysteresis=False)
    assert s.count() == n_before                       # no new run persisted
    assert wi["content_hash"] != base["content_hash"]  # but the what-if DID recompute
    assert (tmp_path / "policy.yaml").read_bytes() == policy_before  # policy untouched


# ---- J — /run payload identical via /decisions ----

def test_j_run_and_decisions_identical():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r1 = client.post("/api/v1/run", files=_files()).json()
    r2 = client.get("/api/v1/decisions").json()
    assert r1["content_hash"] == r2["content_hash"]
    assert [(h["instrument"], h["decision"]) for h in r1["holdings"]] == \
           [(h["instrument"], h["decision"]) for h in r2["holdings"]]


# ---- proxy vs missing distinction ----

def test_proxy_vs_missing_distinction(foundation):
    h_agi = _h(_run(), "AGI Greenpac")
    dq = h_agi["data_quality"]
    assert dq["valuation_stretch"] == "missing"
    assert dq["position_sizing"] == "proxy"  # CR-009: unknown bucket uses disclosed fallback basis
    assert dq["tax_efficiency"] == "authoritative"
    h_sal = _h(_run(), "Salasar Techno Engg")
    assert h_sal["data_quality"]["position_sizing"] == "authoritative"
    assert h_sal["data_quality"]["valuation_stretch"] == "proxy"


# ---- gate override mid-history (hysteresis sequences D/E) ----

def test_gate_override_mid_history_g1(foundation):
    history = {"Ashoka Buildcon": {"decision": "HOLD", "composite_score": 40.0, "as_of": "2026-08-20"}}
    p = decide_on_foundation(foundation, history=history, apply_hysteresis=True)
    assert _h(p, "Ashoka Buildcon")["decision"] == "EXIT"   # immediate, no N=2 wait


def test_gate_override_mid_history_g2(foundation):
    history = {"Salasar Techno Engg": {"decision": "HOLD", "composite_score": 40.0, "as_of": "2026-08-20"}}
    p = decide_on_foundation(foundation, history=history, apply_hysteresis=True)
    s = _h(p, "Salasar Techno Engg")
    assert s["decision"] == "TRIM" and s["stage1"]["winning_gate"] == "G2"
