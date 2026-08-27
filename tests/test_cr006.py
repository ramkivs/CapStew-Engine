"""CR-006 — G0 Portfolio↔Ledger canonical instrument join (acceptance battery).

Authority: docs/cr006-canonical-instrument-join.md (recorded decisions A–L).

The G0 identity join uses the EXISTING frozen canonical_name_key() as a
lookup identity only: exact raw matches are consumed first, canonical links
are made only 1↔1 per key, and every canonical collision fails closed with
the additive blocking code CANONICAL_NAME_COLLISION. Raw source names are
preserved; the numeric G0 checks and the ₹0.01 tolerance are unchanged.

Battery (prompt §7): A exact · B whitespace · C case · D punctuation ·
E A1 real shape through numeric G0 · F A2 stays NO_LOTS · G A3 stays
blocking · H portfolio-side collision · I ledger-side collision ·
J both-side duplication · K true orphan warning · L determinism ·
M tolerance · N CR-005 partial data · O goldens/exact fixtures ·
P lot propagation · Q decision tax/trim lookup · R raw-name preservation ·
S collision fail-closed (no arbitrary lot).
"""
from datetime import date
from decimal import Decimal

from app.decision import decide_all
from app.pipeline import decide_on_foundation, run_foundation
from app.reconcile import reconcile
from app.symbols import build_portfolio_ledger_link

D = Decimal
AS_OF = date(2026, 8, 22)


# --- synthetic row helpers (same shapes as parsed rows) ---------------------

def _p(instrument, qty=20, avg="589.65", invested="11793.00", cval="12000.00"):
    return {
        "instrument": instrument, "qty_held": qty, "avg_buy_price": D(avg),
        "invested": D(invested), "current_value": D(cval),
    }


def _l(instrument, qty=10, buy="589.65", ltp="600.00", tdate="2025-06-10"):
    q = D(str(qty))
    b = D(str(buy))
    p = D(str(ltp))
    return {
        "instrument": instrument, "qty": qty, "buy_price": b, "ltp": p,
        "invested": q * b, "curr_value": q * p, "trade_date": tdate,
    }


# A1 real export shape: identical economics, whitespace-divergent raw names.
PORTFOLIO_HEADER = (
    "Instrument,Transactions,Qty Held,Avg Buy Price,Invested,Current Value,"
    "Allocation %,Gain/Loss %,Net Cashflow,XIRR,Holding Period (Days),First Date,Last Date"
)
LEDGER_HEADER = "Instrument,Qty.,Buy Price,LTP,P&L,Invested,Curr value,Trade Date"
SCREENER_HEADER = (
    "Name,Ticker,Sub-Sector,Market Cap,Close Price,PE Ratio,PB Ratio,PEGRATIO,ROE,ROCE,"
    "1Y Historical EPS Growth,1Y Forward EPS Growth,Debt to Equity,Interest Coverage Ratio,"
    "Price/FCF,Pledged Promoter Holdings,200D SMA,PE Premium vs Sub-sector,"
    "PB Premium vs Sub-sector,DII Holding Change 3M,FII Holding Change 3M"
)


def _write_real_shape_csvs(base, p_name, l_name):
    """Deterministic A1 corpus: one position, two ledger lots, empty screener."""
    base.mkdir(parents=True, exist_ok=True)
    portfolio = base / "portfolio.csv"
    ledger = base / "ledger.csv"
    screener = base / "screener.csv"
    portfolio.write_text(
        PORTFOLIO_HEADER + "\n"
        f"{p_name},2,20,589.65,11793.00,12000.00,1.76,1.76,207.00,,439,2025-06-10,2025-07-15\n",
        encoding="utf-8",
    )
    ledger.write_text(
        LEDGER_HEADER + "\n"
        f"{l_name},10,589.65,600.00,103.50,5896.50,6000.00,10-06-2025\n"
        f"{l_name},10,589.65,600.00,103.50,5896.50,6000.00,15-07-2025\n",
        encoding="utf-8",
    )
    screener.write_text(SCREENER_HEADER + "\n", encoding="utf-8")
    return portfolio, screener, ledger


def _collision_foundation():
    """Position facing a ledger-side canonical collision (nothing must link)."""
    portfolio_rows = [_p("Venus Textiles")]
    ledger_rows = [_l("Venus Textiles Ltd"), _l("Venus Textiles Limited")]
    recon = reconcile(portfolio_rows, ledger_rows, D("0.01"))
    lot = {
        "lot_id": 1, "ticker": None, "trade_date": "2025-06-10", "qty": 10.0,
        "buy_price": 589.65, "ltp": 600.0, "invested": 5896.5, "value": 6000.0,
        "pnl": 103.5, "pnl_pct": 1.76, "days_held": 438, "days_to_ltcg": 0,
        "ltcg_eligible": True,
    }
    lots = [
        {**lot, "instrument": "Venus Textiles Ltd"},
        {**lot, "instrument": "Venus Textiles Limited"},
    ]
    position = {
        "instrument": "Venus Textiles", "ticker": None, "bucket": "large",
        "qty_held": 20, "avg_buy_price": 589.65, "invested": 11793.0,
        "current_value": 12000.0, "alloc_pct": 25.0, "gain_pct": 1.76,
        "net_cashflow": 207.0, "first_date": None, "last_date": None,
        "lot_count": 0, "in_screener": False, "pledge_pct": None,
        "fundamentals": None,
    }
    return {
        "run_id": "run_cr006_s", "as_of": AS_OF.isoformat(), "content_hash": "x",
        "positions": [position], "lots": lots, "reconciliation": recon,
        "warnings": [], "data_as_of": {"stale_files": []},
    }


# --- builder semantics -------------------------------------------------------

def test_link_exact_match_consumed_before_canonical():
    # Exact pair "ABC"↔"ABC" is consumed first; "ABC Ltd" then has no
    # canonical counterpart and stays unlinked (downstream NO_LOTS).
    link = build_portfolio_ledger_link(["ABC", "ABC Ltd"], ["ABC"])
    assert link["portfolio_to_ledger"] == {"ABC": "ABC"}
    assert link["collisions"] == {}


def test_link_exact_and_canonical_pairs_coexist():
    # "ABC" exact; remaining "ABC Ltd"↔"ABC Limited" is a clean 1↔1 link.
    link = build_portfolio_ledger_link(["ABC", "ABC Ltd"], ["ABC", "ABC Limited"])
    assert link["portfolio_to_ledger"] == {"ABC": "ABC", "ABC Ltd": "ABC Limited"}
    assert link["ledger_to_portfolio"] == {"ABC": "ABC", "ABC Limited": "ABC Ltd"}
    assert link["collisions"] == {}


def test_link_collision_links_nothing_involved():
    link = build_portfolio_ledger_link(
        ["Venus Textiles"], ["Venus Textiles Ltd", "Venus Textiles Limited"])
    assert link["portfolio_to_ledger"] == {}
    assert set(link["collisions"]) == {"venustextiles"}
    assert link["collision_portfolio_names"] == {"Venus Textiles"}
    assert link["collision_ledger_names"] == {"Venus Textiles Ltd", "Venus Textiles Limited"}


# --- A. exact raw-name match -------------------------------------------------

def test_a_exact_raw_name_match_still_reconciles():
    r = reconcile([_p("AGI Greenpac")],
                  [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15")],
                  D("0.01"))
    assert r["ok"] is True and r["blocking"] == 0 and r["issues"] == []
    statuses = {c["check"]: c["status"] for c in r["checks"]}
    assert statuses == {"qty": "pass", "invested": "pass",
                        "avg_price": "pass", "value": "pass"}


# --- B. whitespace-only canonical-equivalent match ---------------------------

def test_b_whitespace_only_canonical_match_reconciles():
    # Real export divergence: "AGI   Greenpac" (portfolio) vs "AGI Greenpac" (ledger).
    r = reconcile([_p("AGI   Greenpac")],
                  [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15")],
                  D("0.01"))
    assert r["ok"] is True and r["issues"] == []
    assert {c["instrument"] for c in r["checks"]} == {"AGI   Greenpac"}


# --- C. case canonicalization (already supported by canonical_name_key) ------

def test_c_case_canonical_match_reconciles():
    r = reconcile([_p("agi greenpac")],
                  [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15")],
                  D("0.01"))
    assert r["ok"] is True and r["issues"] == []


# --- D. punctuation canonicalization (already supported) ---------------------

def test_d_punctuation_canonical_match_reconciles():
    r = reconcile(
        [_p("Larsen and Toubro", qty=10, avg="100.00", invested="1000.00", cval="1200.00")],
        [_l("Larsen & Toubro", qty=10, buy="100.00", ltp="120.00")],
        D("0.01"),
    )
    assert r["ok"] is True and r["issues"] == []
    r2 = reconcile(
        [_p("Coca Cola", qty=10, avg="100.00", invested="1000.00", cval="1200.00")],
        [_l("Coca-Cola", qty=10, buy="100.00", ltp="120.00")],
        D("0.01"),
    )
    assert r2["ok"] is True and r2["issues"] == []


# --- E. A1 canonical-equivalent real shape proceeds through numeric G0 -------

def test_e_a1_real_shape_proceeds_through_g0_and_decides(tmp_path):
    paths = _write_real_shape_csvs(tmp_path / "a1", "AGI   Greenpac", "AGI Greenpac")
    foundation = run_foundation(*paths, as_of=AS_OF)
    assert foundation["reconciliation"]["ok"] is True
    assert foundation["reconciliation"]["blocking"] == 0
    payload = decide_on_foundation(foundation)
    holding = next(h for h in payload["holdings"] if h["instrument"] == "AGI   Greenpac")
    assert holding["decision"] != "NO-DECISION"
    assert holding["reason_tree"]["decision_path"] != "G0 → NO-DECISION (reconciliation blocked)"


# --- F. A2 missing canonical ledger counterpart stays NO_LOTS -----------------

def test_f_a2_missing_ledger_stays_no_lots_blocking():
    r = reconcile([_p("No Ledger Corp")], [], D("0.01"))
    assert r["ok"] is False
    issue = next(i for i in r["issues"] if i["instrument"] == "No Ledger Corp")
    assert issue["code"] == "NO_LOTS" and issue["severity"] == "blocking"


# --- G. A3 numeric mismatch remains RECONCILE_MISMATCH/blocking ---------------

def test_g_a3_numeric_mismatch_stays_blocking():
    # Linked canonically, but invested is genuinely off by ₹207.00.
    r = reconcile([_p("AGI   Greenpac", invested="12000.00")],
                  [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15")],
                  D("0.01"))
    assert r["ok"] is False
    assert any(i["code"] == "RECONCILE_MISMATCH" and i["severity"] == "blocking"
               for i in r["issues"])
    failed = {c["check"] for c in r["checks"] if c["status"] == "fail"}
    assert failed == {"invested"}


# --- H. portfolio-side collision blocks --------------------------------------

def test_h_portfolio_side_collision_blocks():
    r = reconcile([_p("Mercury Labs"), _p("Mercury Labs Ltd")],
                  [_l("Mercury Labs Co")], D("0.01"))
    assert r["ok"] is False
    col = [i for i in r["issues"] if i["code"] == "CANONICAL_NAME_COLLISION"]
    assert {i["instrument"] for i in col} == {
        "Mercury Labs", "Mercury Labs Ltd", "Mercury Labs Co"}
    assert all(i["severity"] == "blocking" for i in col)
    assert r["checks"] == []  # no numeric link was made for any involved name
    assert not any(i["code"] in ("NO_LOTS", "LEDGER_ONLY_LOTS") for i in r["issues"])


# --- I. ledger-side collision blocks -----------------------------------------

def test_i_ledger_side_collision_blocks():
    r = reconcile([_p("Venus Textiles")],
                  [_l("Venus Textiles Ltd"), _l("Venus Textiles Limited")],
                  D("0.01"))
    assert r["ok"] is False
    flagged = {(i["code"], i["instrument"]) for i in r["issues"]}
    assert ("CANONICAL_NAME_COLLISION", "Venus Textiles") in flagged
    assert ("CANONICAL_NAME_COLLISION", "Venus Textiles Ltd") in flagged
    assert ("CANONICAL_NAME_COLLISION", "Venus Textiles Limited") in flagged
    assert r["checks"] == []


# --- J. both-side duplication blocks deterministically ------------------------

def test_j_both_side_duplication_blocks():
    portfolio = [_p("A One Pharma"), _p("A  One Pharma")]
    ledger = [_l("A-One Pharma"), _l("A.One Pharma")]
    r = reconcile(portfolio, ledger, D("0.01"))
    assert r["ok"] is False
    assert {i["instrument"] for i in r["issues"]
            if i["code"] == "CANONICAL_NAME_COLLISION"} == {
        "A One Pharma", "A  One Pharma", "A-One Pharma", "A.One Pharma"}
    assert r["checks"] == []


# --- K. true ledger-only orphan remains LEDGER_ONLY_LOTS warning --------------

def test_k_true_ledger_only_orphan_stays_warning():
    r = reconcile([_p("AGI Greenpac")],
                  [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15"),
                   _l("Zodiac Orphan Mills", qty=5, buy="10.00", ltp="12.00")],
                  D("0.01"))
    assert r["ok"] is True
    orphans = [i for i in r["issues"] if i["code"] == "LEDGER_ONLY_LOTS"]
    assert len(orphans) == 1
    assert orphans[0]["instrument"] == "Zodiac Orphan Mills"
    assert orphans[0]["severity"] == "warning"


# --- L. determinism ------------------------------------------------------------

def test_l_repeated_identical_inputs_identical_results():
    portfolio = [_p("AGI   Greenpac"), _p("Mercury Labs"), _p("Mercury Labs Ltd")]
    ledger = [_l("AGI Greenpac"), _l("Mercury Labs Co"),
              _l("Zodiac Orphan Mills", qty=5, buy="10.00", ltp="12.00")]
    runs = [reconcile(portfolio, ledger, D("0.01")) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    link1 = build_portfolio_ledger_link(
        [p["instrument"] for p in portfolio], [r["instrument"] for r in ledger])
    link2 = build_portfolio_ledger_link(
        [p["instrument"] for p in portfolio], [r["instrument"] for r in ledger])
    assert link1 == link2


def test_l_foundation_content_determinism_with_canonical_link(tmp_path):
    paths = _write_real_shape_csvs(tmp_path / "det", "AGI   Greenpac", "AGI Greenpac")
    f1 = run_foundation(*paths, as_of=AS_OF, run_id="run_a")
    f2 = run_foundation(*paths, as_of=AS_OF, run_id="run_b")
    assert f1["content_hash"] == f2["content_hash"]


# --- M. existing ₹0.01 tolerance unchanged ------------------------------------

def test_m_tolerance_boundary_unchanged_under_canonical_link():
    ledger = [_l("AGI Greenpac"), _l("AGI Greenpac", tdate="2025-07-15")]
    within = reconcile([_p("AGI   Greenpac", invested="11793.01")], ledger, D("0.01"))
    assert within["ok"] is True  # 0.01 diff still passes
    beyond = reconcile([_p("AGI   Greenpac", invested="11793.02")], ledger, D("0.01"))
    assert beyond["ok"] is False  # 0.02 diff still fails
    assert any(i["code"] == "RECONCILE_MISMATCH" for i in beyond["issues"])


# --- N. CR-005 partial screener behavior unchanged -----------------------------

def test_n_cr005_partial_data_behavior_unchanged(tmp_path):
    canonical = _write_real_shape_csvs(tmp_path / "canon", "AGI   Greenpac", "AGI Greenpac")
    exact = _write_real_shape_csvs(tmp_path / "exact", "AGI Greenpac", "AGI Greenpac")
    f_canon = run_foundation(*canonical, as_of=AS_OF)
    f_exact = run_foundation(*exact, as_of=AS_OF)
    assert f_canon["positions"][0]["in_screener"] is False
    assert f_exact["positions"][0]["in_screener"] is False
    p_canon = decide_on_foundation(f_canon)
    p_exact = decide_on_foundation(f_exact)
    codes = {w["code"] for w in p_canon["warnings"]}
    assert "PARTIAL_DATA" in codes  # screener absence stays a warning, never a blocker
    h_canon = p_canon["holdings"][0]
    h_exact = p_exact["holdings"][0]
    # Canonical path must behave exactly like the exact-match path did.
    assert h_canon["decision"] == h_exact["decision"] != "NO-DECISION"
    assert h_canon["subscores"] == h_exact["subscores"]
    assert (p_canon["portfolio_summary"]["decision_distribution"]
            == p_exact["portfolio_summary"]["decision_distribution"])


# --- O. existing exact-match fixtures/goldens unaffected -----------------------

def test_o_existing_exact_match_fixtures_unaffected(foundation):
    recon = foundation["reconciliation"]
    assert recon["ok"] is True and recon["blocking"] == 0
    assert all(i["code"] != "CANONICAL_NAME_COLLISION" for i in recon["issues"])
    # golden data facts still hold through the link path
    pos = {p["instrument"]: p for p in foundation["positions"]}
    assert pos["AGI Greenpac"]["lot_count"] == 2
    assert pos["Ashoka Buildcon"]["lot_count"] == 16
    assert pos["Larsen & Toubro"]["bucket"] == "large"


# --- P. lot propagation through derive_positions --------------------------------

def test_p_canonical_link_feeds_position_lot_rollup(tmp_path):
    paths = _write_real_shape_csvs(tmp_path / "lots", "AGI   Greenpac", "AGI Greenpac")
    foundation = run_foundation(*paths, as_of=AS_OF)
    pos = foundation["positions"][0]
    assert pos["lot_count"] == 2
    assert pos["first_date"] == "2025-06-10"  # from linked ledger lots
    assert pos["last_date"] == "2025-07-15"
    lots = [l for l in foundation["lots"] if l["instrument"] == "AGI Greenpac"]
    assert len(lots) == 2
    assert all(l["ticker"] == "AGIGREENPAC" for l in lots)


# --- Q. decision tax/trim lot lookup uses canonical lots -------------------------

def _g2_foundation():
    position = {
        "instrument": "Alpha  Industries", "ticker": None, "bucket": "large",
        "qty_held": 100, "avg_buy_price": 100.0, "invested": 10000.0,
        "current_value": 25000.0, "alloc_pct": 25.0, "gain_pct": 150.0,
        "net_cashflow": 15000.0, "first_date": "2024-01-15",
        "last_date": "2024-06-15", "lot_count": 2, "in_screener": False,
        "pledge_pct": None, "fundamentals": None,
    }

    def lot(lot_id, tdate):
        return {
            "lot_id": lot_id, "instrument": "Alpha Industries", "ticker": None,
            "trade_date": tdate, "qty": 50.0, "buy_price": 100.0, "ltp": 250.0,
            "invested": 5000.0, "value": 12500.0, "pnl": 7500.0, "pnl_pct": 150.0,
            "days_held": 900, "days_to_ltcg": 0, "ltcg_eligible": True,
        }

    return {
        "run_id": "run_cr006_q", "as_of": AS_OF.isoformat(), "content_hash": "x",
        "positions": [position], "lots": [lot(1, "2024-01-15"), lot(2, "2024-06-15")],
        "reconciliation": {"ok": True, "blocking": 0, "warnings": 0,
                           "checks": [], "issues": []},
        "warnings": [], "data_as_of": {"stale_files": []},
    }


def test_q_decision_tax_trim_lookup_uses_canonical_lots():
    payload = decide_all(_g2_foundation())
    h = payload["holdings"][0]
    assert h["instrument"] == "Alpha  Industries"
    assert h["decision"] == "TRIM" and h["stage1"]["winning_gate"] == "G2"
    # trim_s received the canonically linked lots (FIFO sell plan exists)
    assert h["trim"] is not None and h["trim"]["mode"] == "S"
    assert h["trim"]["fifo_lots_to_sell"]
    # decision payload carries the linked lots under their raw Ledger names
    assert {l["instrument"] for l in h["lots"]} == {"Alpha Industries"}
    # tax.rank_candidates (keyed by position name) resolved the same link
    seq = [r for r in payload["portfolio_layer"]["tax_sequencing"]
           if r["instrument"] == "Alpha  Industries"]
    assert seq and seq[0]["ltcg_gain"] > 0


# --- R. raw-name preservation ----------------------------------------------------

def test_r_raw_names_preserved_end_to_end(tmp_path):
    paths = _write_real_shape_csvs(tmp_path / "raw", "AGI   Greenpac", "AGI Greenpac")
    foundation = run_foundation(*paths, as_of=AS_OF)
    payload = decide_on_foundation(foundation)
    assert foundation["positions"][0]["instrument"] == "AGI   Greenpac"
    assert {l["instrument"] for l in foundation["lots"]} == {"AGI Greenpac"}
    assert payload["holdings"][0]["instrument"] == "AGI   Greenpac"
    assert {c["instrument"] for c in foundation["reconciliation"]["checks"]} == {
        "AGI   Greenpac"}
    # diagnostics/provenance keep the raw Portfolio name verbatim
    sym = [w for w in payload["warnings"] if w["code"] == "SYMBOL_UNMATCHED"]
    assert any("AGI   Greenpac" in (w["message"] or "") for w in sym)


def test_r_collision_messages_preserve_raw_names():
    r = reconcile([_p("Venus Textiles")],
                  [_l("Venus Textiles Ltd"), _l("Venus Textiles Limited")],
                  D("0.01"))
    messages = [i["message"] for i in r["issues"]
                if i["code"] == "CANONICAL_NAME_COLLISION"]
    assert messages
    assert any("Venus Textiles Ltd" in m and "Venus Textiles Limited" in m
               for m in messages)


# --- S. collision fail-closed: no arbitrary lot, decision is NO-DECISION ---------

def test_s_collision_fail_closed_no_arbitrary_lot_or_decision():
    foundation = _collision_foundation()
    assert foundation["reconciliation"]["ok"] is False
    payload = decide_all(foundation)
    h = payload["holdings"][0]
    assert h["decision"] == "NO-DECISION"
    assert h["reason_tree"]["decision_path"] == "G0 → NO-DECISION (reconciliation blocked)"
    assert "lots" not in h or not h["lots"]  # nothing was arbitrarily selected


# --- T/U/V. CR-006 remediation: G0 NO-DECISION must not seed G4 hysteresis ------
#
# Root cause: a persisted G0 NO-DECISION was seeded into the G4 hysteresis
# state machine, so a currently unblocked holding spent N=2 persistence
# "leaving" G0 (first run returned NO-DECISION, e.g. real-run AGI Greenpac:
# composite 14.8, raw band HOLD, output NO-DECISION). The remediation treats
# historical NO-DECISION as an audit status only: previous_run is preserved
# verbatim, but the current raw band establishes the current G4 state.

def _remediation_foundation():
    fundamentals = {
        "pe_ratio": 12.0, "pb_ratio": 1.8, "peg_ratio": 0.8, "roe": 20.0,
        "roce": 18.0, "eps_growth_1y_hist": 15.0, "eps_growth_1y_fwd": 12.0,
        "debt_equity": 0.3, "interest_coverage": 10.0, "price_fcf": 20.0,
        "pe_premium_vs_subsector": 0.6, "pb_premium_vs_subsector": 0.9,
        "dii_change_3m": 0.0, "fii_change_3m": 0.0, "sma_200": 100.0,
        "close_price": 110.0, "market_cap_cr": 50000.0,
        "sub_sector": "Industrials",
    }
    position = {
        "instrument": "Trace Industries", "ticker": None, "bucket": "large",
        "qty_held": 20, "avg_buy_price": 100.0, "invested": 2000.0,
        "current_value": 2200.0, "alloc_pct": 6.0, "gain_pct": 10.0,
        "net_cashflow": 200.0, "first_date": "2025-10-15",
        "last_date": "2025-11-02", "lot_count": 2, "in_screener": True,
        "pledge_pct": 0.0, "fundamentals": fundamentals,
    }

    def lot(lot_id, tdate, days_held, days_to_ltcg):
        return {
            "lot_id": lot_id, "instrument": "Trace Industries", "ticker": None,
            "trade_date": tdate, "qty": 10.0, "buy_price": 100.0, "ltp": 110.0,
            "invested": 1000.0, "value": 1100.0, "pnl": 100.0, "pnl_pct": 10.0,
            "days_held": days_held, "days_to_ltcg": days_to_ltcg,
            "ltcg_eligible": False,
        }

    return {
        "run_id": "run_cr006_t", "as_of": "2026-08-27", "content_hash": "x",
        "positions": [position],
        "lots": [lot(1, "2025-10-15", 316, 49), lot(2, "2025-11-02", 298, 67)],
        "reconciliation": {"ok": True, "blocking": 0, "warnings": 0,
                           "checks": [], "issues": []},
        "warnings": [], "data_as_of": {"stale_files": []},
    }


_NO_DECISION_HISTORY = {
    "Trace Industries": {"decision": "NO-DECISION", "composite_score": None,
                         "as_of": "2026-08-20"},
}


def test_t_g0_no_decision_history_does_not_seed_g4_hysteresis():
    # Persisted previous decision NO-DECISION; current run unblocked; current
    # raw G4 band = HOLD. ONE run must suffice — no N=2 wait to leave G0.
    payload = decide_all(_remediation_foundation(), history=_NO_DECISION_HISTORY)
    h = payload["holdings"][0]
    assert h["decision"] == "HOLD"
    assert h["composite_score"] is not None and h["composite_score"] <= 30  # HOLD band
    assert h["evidence"]["tier"] == "NORMAL"  # full coverage, as in the real AGI case
    assert h["reason_tree"]["decision_path"].startswith("G4 → HOLD (composite")
    # historical audit field preserved verbatim
    assert h["previous_run"]["decision"] == "NO-DECISION"
    assert h["previous_run"]["composite_score"] is None
    assert h["previous_run"]["as_of"] == "2026-08-20"


def test_u_legitimate_g4_hysteresis_n2_unchanged():
    # Control: previous decision WATCH is a legitimate G4 state — the frozen
    # N=2 machinery must still hold it on the first run (raw band HOLD,
    # transition WATCH→HOLD requires 2 distinct as_of dates).
    history = {"Trace Industries": {"decision": "WATCH", "composite_score": 20.0,
                                    "as_of": "2026-08-20"}}
    payload = decide_all(_remediation_foundation(), history=history)
    h = payload["holdings"][0]
    assert h["decision"] == "WATCH"  # N=2 persistence intact
    assert h["previous_run"]["decision"] == "WATCH"


def test_v_gate_bypass_with_no_decision_history_unchanged():
    # Control: a Stage-1 gate bypasses hysteresis regardless of seeded
    # NO-DECISION history — behavior must be identical to pre-remediation.
    foundation = _remediation_foundation()
    foundation["positions"][0]["pledge_pct"] = 12.4  # above the G1 10% threshold
    payload = decide_all(foundation, history=_NO_DECISION_HISTORY)
    h = payload["holdings"][0]
    assert h["decision"] == "EXIT"
    assert h["stage1"]["winning_gate"] == "G1"
    assert h["previous_run"]["decision"] == "NO-DECISION"
