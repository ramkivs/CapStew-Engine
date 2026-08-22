from decimal import Decimal

from app.reconcile import reconcile


def test_clean_fixture_reconciles(foundation):
    r = foundation["reconciliation"]
    assert r["ok"] is True
    assert r["blocking"] == 0


def test_agi_greenpac_exact_reconciliation(foundation):
    checks = {(c["instrument"], c["check"]): c for c in foundation["reconciliation"]["checks"]}
    qty = checks[("AGI Greenpac", "qty")]
    assert qty["status"] == "pass" and qty["expected"] == 20
    inv = checks[("AGI Greenpac", "invested")]
    assert inv["status"] == "pass" and abs(inv["expected"] - 11793.0) < 0.01
    avg = checks[("AGI Greenpac", "avg_price")]
    assert avg["status"] == "pass" and abs(avg["expected"] - 589.65) < 0.001


def test_reconcile_mismatch_is_blocking():
    portfolio = [{
        "instrument": "X", "qty_held": 2, "avg_buy_price": Decimal("10"),
        "invested": Decimal("30"), "current_value": Decimal("40"),
    }]
    ledger = [{
        "instrument": "X", "qty": 2, "buy_price": Decimal("10"), "ltp": Decimal("20"),
        "invested": Decimal("20"), "curr_value": Decimal("40"),
    }]
    r = reconcile(portfolio, ledger, Decimal("0.01"))
    assert r["ok"] is False
    codes = {i["code"] for i in r["issues"]}
    assert "RECONCILE_MISMATCH" in codes
    assert any(i["severity"] == "blocking" for i in r["issues"])


def test_no_lots_is_blocking():
    portfolio = [{
        "instrument": "Y", "qty_held": 1, "avg_buy_price": Decimal("10"),
        "invested": Decimal("10"), "current_value": Decimal("10"),
    }]
    r = reconcile(portfolio, [], Decimal("0.01"))
    assert r["ok"] is False
    assert any(i["code"] == "NO_LOTS" for i in r["issues"])


def test_ledger_only_lots_warns_not_blocks():
    ledger = [{
        "instrument": "Z", "qty": 1, "buy_price": Decimal("10"), "ltp": Decimal("10"),
        "invested": Decimal("10"), "curr_value": Decimal("10"),
    }]
    r = reconcile([], ledger, Decimal("0.01"))
    assert r["ok"] is True
    assert any(i["code"] == "LEDGER_ONLY_LOTS" and i["severity"] == "warning" for i in r["issues"])
