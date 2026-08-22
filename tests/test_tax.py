"""Tax golden fixtures — the second fixture family (Phase 3).

  GOLDEN-TAX-LTCG        — a >12mo gain realises as LTCG
  GOLDEN-TAX-STCG        — a ≤12mo gain realises as STCG
  GOLDEN-TAX-EXEMPTION   — ₹1.25L exemption applied, 12.5% above it
  GOLDEN-TAX-S74-SET-OFF — STCL offsets STCG then LTCG; LTCL offsets LTCG only
  GOLDEN-TAX-CROSS-FY    — carried-forward losses (8y) offset later gains; lapse at 8
Plus FIFO matching and tax-aware sequencing.
"""
from datetime import date
from decimal import Decimal

from app.tax import (
    classify_gain,
    match_sells_fifo,
    rank_candidates,
    tax_year_summary,
    unrealized_split,
)


def _r(kind, amount):
    # realized records carry SIGNED gain (negative for losses)
    gain = -Decimal(amount) if kind in ("LTCL", "STCL") else Decimal(amount)
    return {"type": kind, "gain": gain}


def _gross(summary):
    return summary["gross"]


# ---------------- golden tax fixtures ----------------

def test_golden_tax_ltcg():
    s = tax_year_summary([_r("LTCG", 100_000)])
    assert _gross(s)["ltcg"] == 100_000.0
    assert s["exemption"]["used"] == 100_000.0
    assert s["exemption"]["headroom"] == 25_000.0
    assert s["taxable"]["ltcg"] == 0.0
    assert s["tax"]["total"] == 0.0


def test_golden_tax_stcg():
    s = tax_year_summary([_r("STCG", 50_000)])
    assert _gross(s)["stcg"] == 50_000.0
    assert s["exemption"]["used"] == 0.0          # STCG has no exemption
    assert s["tax"]["stcg"] == 10_000.0           # 20%
    assert s["tax"]["total"] == 10_000.0


def test_golden_tax_exemption():
    s = tax_year_summary([_r("LTCG", 200_000)])
    assert s["exemption"]["used"] == 125_000.0
    assert s["taxable"]["ltcg"] == 75_000.0
    assert s["tax"]["ltcg"] == 9_375.0            # 12.5% of 75,000


def test_golden_tax_s74_stcl_offsets_stcg_then_ltcg():
    # STCL 60k > STCG 40k → 20k leftover offsets LTCG 100k → LTCG 80k → exempt → 0 tax
    s = tax_year_summary([_r("STCG", 40_000), _r("STCL", 60_000), _r("LTCG", 100_000)])
    assert s["net"]["stcg"] == 0.0
    assert s["net"]["ltcg"] == 80_000.0
    assert s["tax"]["total"] == 0.0
    assert s["set_off"]["stcl_used_against_stcg"] == 40_000.0
    assert s["set_off"]["stcl_used_against_ltcg"] == 20_000.0


def test_golden_tax_s74_ltcl_offsets_ltcg_only():
    # LTCL 30k offsets LTCG 100k → 70k (exempt). STCG 50k is NOT offset by LTCL → 20% tax.
    s = tax_year_summary([_r("LTCL", 30_000), _r("LTCG", 100_000), _r("STCG", 50_000)])
    assert s["net"]["ltcg"] == 70_000.0
    assert s["net"]["stcg"] == 50_000.0
    assert s["tax"]["stcg"] == 10_000.0
    assert s["tax"]["ltcg"] == 0.0


def test_golden_tax_cross_fy_carry_forward():
    # Year 1: LTCL 100k, no gains → carried forward
    y1 = tax_year_summary([_r("LTCL", 100_000)])
    assert y1["carry_forward_out"]["ltcl"] == [(100_000.0, 1)]
    # Year 2: LTCG 150k, brought-forward LTCL 100k (age 1) → LTCG 50k → exempt → 0 tax
    y2 = tax_year_summary([_r("LTCG", 150_000)],
                          carry_in={"ltcl": [(100_000, 1)], "stcl": []})
    assert y2["net"]["ltcg"] == 50_000.0
    assert y2["tax"]["total"] == 0.0


def test_golden_tax_cross_fy_lapse_at_8_years():
    # A loss aged 8 cannot be used and does not carry out
    s = tax_year_summary([_r("LTCG", 150_000)],
                         carry_in={"ltcl": [(100_000, 8)], "stcl": []})
    assert s["net"]["ltcg"] == 150_000.0          # loss lapsed, no offset
    assert s["carry_forward_out"]["ltcl"] == []   # and it does not carry forward


# ---------------- classification + FIFO matching ----------------

def test_classify_boundaries():
    assert classify_gain(100, 366) == "LTCG"
    assert classify_gain(100, 365) == "STCG"       # strict: >12 months
    assert classify_gain(-100, 366) == "LTCL"
    assert classify_gain(-100, 365) == "STCL"


def test_fifo_matching_oldest_first_with_ltcg_stcg_split():
    lots = [
        {"lot_id": 1, "qty": 100, "buy_price": Decimal(100), "trade_date": date(2024, 1, 1)},
        {"lot_id": 2, "qty": 100, "buy_price": Decimal(200), "trade_date": date(2025, 1, 1)},
    ]
    sells = [{"instrument": "X", "qty": 150, "sell_price": Decimal(250), "sell_date": date(2025, 6, 1)}]
    realized = match_sells_fifo(lots, sells)
    by_type = {r["type"]: r for r in realized}
    assert by_type["LTCG"]["qty"] == 100           # 516 days held
    assert by_type["LTCG"]["gain"] == Decimal(15000)
    assert by_type["STCG"]["qty"] == 50            # 151 days held
    assert by_type["STCG"]["gain"] == Decimal(2500)


# ---------------- unrealised split + sequencing ----------------

def test_unrealized_split():
    lots = [
        {"qty": 10, "buy_price": 100, "ltp": 150, "ltcg_eligible": True},
        {"qty": 10, "buy_price": 100, "ltp": 120, "ltcg_eligible": False},
        {"qty": 10, "buy_price": 100, "ltp": 90, "ltcg_eligible": False},
    ]
    s = unrealized_split(lots)
    assert s == {"ltcg": 500.0, "stcg": 200.0, "ltcl": 0.0, "stcl": 100.0}


def test_rank_candidates_ltcg_first():
    cands = [
        {"instrument": "A", "decision": "TRIM"},
        {"instrument": "B", "decision": "TRIM"},
    ]
    lots_by = {
        "A": [{"qty": 100, "buy_price": 100, "ltp": 200, "ltcg_eligible": False}],  # STCG 10k
        "B": [{"qty": 100, "buy_price": 100, "ltp": 200, "ltcg_eligible": True}],   # LTCG 10k
    }
    ranked = rank_candidates(cands, lots_by)
    assert [r["instrument"] for r in ranked] == ["B", "A"]   # LTCG (tax-free) first
    assert ranked[0]["ltcg_gain"] == 10000.0
    assert ranked[1]["stcg_gain"] == 10000.0
