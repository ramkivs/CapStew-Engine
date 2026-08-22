from datetime import date, timedelta
from decimal import Decimal

from app.lot_engine import build_lots

ASOF = date(2026, 8, 22)


def _lots(rows, ltcg_days=365):
    return build_lots(rows, ASOF, ltcg_days)


def _lot(days_ago, buy="100.00", ltp="110.00", qty=10, name="X"):
    return {
        "instrument": name,
        "qty": qty,
        "buy_price": Decimal(buy),
        "ltp": Decimal(ltp),
        "trade_date": (ASOF - timedelta(days=days_ago)).isoformat(),
    }


def test_ltcg_boundary_exactly_365_days_is_stcg():
    lots = _lots([_lot(365)])
    assert lots[0]["days_held"] == 365
    assert lots[0]["days_to_ltcg"] == 0
    assert lots[0]["ltcg_eligible"] is False


def test_ltcg_boundary_364_days():
    lots = _lots([_lot(364)])
    assert lots[0]["days_held"] == 364
    assert lots[0]["days_to_ltcg"] == 1
    assert lots[0]["ltcg_eligible"] is False


def test_ltcg_boundary_366_days_is_ltcg():
    lots = _lots([_lot(366)])
    assert lots[0]["days_held"] == 366
    assert lots[0]["days_to_ltcg"] == 0
    assert lots[0]["ltcg_eligible"] is True


def test_pnl_and_pnl_pct():
    lots = _lots([_lot(100, buy="100.00", ltp="110.00", qty=10)])
    assert lots[0]["pnl"] == Decimal("100.00")
    assert lots[0]["pnl_pct"] == 10.0


def test_loss_pnl_pct_negative():
    import pytest
    lots = _lots([_lot(100, buy="110.00", ltp="100.00", qty=10)])
    assert lots[0]["pnl"] == Decimal("-100.00")
    assert lots[0]["pnl_pct"] == pytest.approx(-9.09, abs=0.01)


def test_canonical_order_by_date_then_price():
    rows = [
        _lot(20, buy="101.00", name="A"),
        _lot(10, buy="103.00", name="A"),
        _lot(10, buy="101.00", name="A"),
    ]
    lots = _lots(rows)
    # older (20 days ago) first; within the same date (10 days ago), lower buy price first
    assert [l["buy_price"] for l in lots] == [Decimal("101.00"), Decimal("101.00"), Decimal("103.00")]
    assert [l["days_held"] for l in lots] == [20, 10, 10]
