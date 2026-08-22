"""Golden precedence fixtures — the trilogy (Freeze §11).

Phase 1 asserts the DATA FACTS these fixtures encode; the gate decisions
(G2→TRIM-S, G1→EXIT, G3→HOLD) are asserted in Phase 2 gate tests.
"""


def _pos(foundation, name):
    return next(p for p in foundation["positions"] if p["instrument"] == name)


def _lots(foundation, name):
    return [l for l in foundation["lots"] if l["instrument"] == name]


def test_golden_g2_salasar_pledge_below_g1_threshold(foundation):
    # GOLDEN-G2-TRIM-S-SALASAR: pledge 4.0% (< 10%) so G1 does NOT fire.
    assert _pos(foundation, "Salasar Techno Engg")["pledge_pct"] == 4.0


def test_golden_g1_ashoka_pledge_above_g1_threshold(foundation):
    # GOLDEN-G1-EXIT-ASHOKA: pledge 12.4% (> 10%) so G1 fires.
    assert _pos(foundation, "Ashoka Buildcon")["pledge_pct"] == 12.4


def test_golden_g1_ashoka_16_declining_all_red_lots(foundation):
    lots = _lots(foundation, "Ashoka Buildcon")
    assert len(lots) == 16
    assert all(l["pnl"] < 0 for l in lots)
    prices = [l["buy_price"] for l in lots]
    assert prices == sorted(prices, reverse=True)  # non-increasing buy prices


def test_golden_g3_lt_oldest_lot_22_days_to_ltcg(foundation):
    # GOLDEN-G3-HOLD-LT: oldest lot 2025-09-13 → 22 days to LTCG as of 2026-08-22.
    lots = _lots(foundation, "Larsen & Toubro")
    assert lots[0]["days_to_ltcg"] == 22
    assert lots[0]["ltcg_eligible"] is False


def test_agi_greenpac_not_in_screener_universe(foundation):
    p = _pos(foundation, "AGI Greenpac")
    assert p["in_screener"] is False
    codes = {w["code"] for w in foundation["warnings"]}
    assert "PARTIAL_DATA" in codes


def test_bucket_classification(foundation):
    pos = {p["instrument"]: p for p in foundation["positions"]}
    assert pos["Larsen & Toubro"]["bucket"] == "large"
    assert pos["Bajaj Finance"]["bucket"] == "large"
    assert pos["Bank of Baroda"]["bucket"] == "large"
    assert pos["Bharat Coking Coal"]["bucket"] == "mid"
    assert pos["Ashoka Buildcon"]["bucket"] == "small"
    assert pos["DAM Capital Advisors"]["bucket"] == "small"
    assert pos["Salasar Techno Engg"]["bucket"] == "micro"
