"""Cost-basis reconciliation (G0 — data integrity).

Hard checks per instrument present in both the portfolio and the ledger:
  qty:        Σ(lot qty)                 == portfolio Qty Held
  invested:   Σ(lot qty × buy price)     == portfolio Invested  (± tolerance)
  avg price:  Σ(qty × buy) / Σ(qty)      == portfolio Avg Buy Price (± tolerance)
  value:      Σ(lot qty × ltp)           == portfolio Current Value (± tolerance)
Any failure is a BLOCKING issue (G0 → NO-DECISION) for that instrument.

CR-006: the Portfolio↔Ledger identity join uses the shared deterministic
link from symbols.build_portfolio_ledger_link (exact match first, then
canonical 1↔1, collisions fail closed with CANONICAL_NAME_COLLISION). The
numeric checks above and the ₹0.01 tolerance are unchanged.
"""
from decimal import Decimal

from .symbols import build_portfolio_ledger_link


def _close(a, b, tol):
    if a is None or b is None:
        return False
    return abs(Decimal(a) - Decimal(b)) <= Decimal(tol)


def _f(x, dp=2):
    if x is None:
        return None
    return float(Decimal(x).quantize(Decimal("1") / (10 ** dp)))


def _collision_message(name, key, detail):
    return (
        f"{name!r}: canonical-name collision — canonical key {key!r} is shared by "
        f"portfolio names {list(detail['portfolio'])} and ledger names "
        f"{list(detail['ledger'])}; identity is ambiguous, so no match was made "
        "(fail-closed, no arbitrary selection)"
    )


def reconcile(portfolio_rows, ledger_rows, tolerance=Decimal("0.01"), link=None):
    lots_by_name = {}
    for r in ledger_rows:
        lots_by_name.setdefault(r["instrument"], []).append(r)

    # CR-006: deterministic Portfolio↔Ledger identity link (lookup only).
    # When not supplied by the caller, build it here from the same raw names.
    if link is None:
        link = build_portfolio_ledger_link(
            [p.get("instrument") for p in portfolio_rows],
            [r.get("instrument") for r in ledger_rows],
        )
    p2l = link["portfolio_to_ledger"]
    l2p = link["ledger_to_portfolio"]
    p_collisions = link["collision_portfolio_names"]
    l_collisions = link["collision_ledger_names"]
    collision_of = {}
    for key, detail in link["collisions"].items():
        for n in detail["portfolio"] + detail["ledger"]:
            collision_of[n] = (key, detail)

    issues = []   # {"code", "severity", "instrument", "message"}
    checks = []   # {"instrument", "check", "status", "expected", "actual"}

    for p in portfolio_rows:
        name = p["instrument"]
        if name in p_collisions:
            key, detail = collision_of[name]
            issues.append({
                "code": "CANONICAL_NAME_COLLISION", "severity": "blocking",
                "instrument": name,
                "message": _collision_message(name, key, detail),
            })
            continue
        ledger_name = p2l.get(name)
        lots = lots_by_name.get(ledger_name, []) if ledger_name is not None else []
        if not lots:
            issues.append({
                "code": "NO_LOTS", "severity": "blocking", "instrument": name,
                "message": f"portfolio position {name!r} has no buy fills in the ledger",
            })
            continue

        sum_qty = sum(l["qty"] for l in lots)
        sum_invested = sum(l["qty"] * l["buy_price"] for l in lots)
        sum_value = sum(l["qty"] * l["ltp"] for l in lots)
        avg = sum_invested / sum_qty if sum_qty else Decimal("0")

        def check(key, expected, actual, label):
            ok = _close(expected, actual, tolerance)
            checks.append({
                "instrument": name, "check": key, "status": "pass" if ok else "fail",
                "expected": _f(expected), "actual": _f(actual),
            })
            if not ok:
                issues.append({
                    "code": "RECONCILE_MISMATCH", "severity": "blocking", "instrument": name,
                    "message": (f"{name}: {label} — portfolio {_f(expected)} vs ledger {_f(actual)}"),
                })

        check("qty", p["qty_held"], sum_qty, "quantity held")
        check("invested", p["invested"], sum_invested, "invested")
        check("avg_price", p["avg_buy_price"], avg, "avg buy price")
        check("value", p["current_value"], sum_value, "current value")

        # Ledger-internal integrity (soft): invested/curr_value columns vs recomputed.
        for l in lots:
            if not _close(l["invested"], l["qty"] * l["buy_price"], tolerance):
                checks.append({
                    "instrument": name, "check": "ledger_invested",
                    "status": "fail",
                    "expected": _f(l["qty"] * l["buy_price"]), "actual": _f(l["invested"]),
                })
            if not _close(l["curr_value"], l["qty"] * l["ltp"], tolerance):
                checks.append({
                    "instrument": name, "check": "ledger_curr_value",
                    "status": "fail",
                    "expected": _f(l["qty"] * l["ltp"]), "actual": _f(l["curr_value"]),
                })

    # Ledger rows without a portfolio position (warning only — may be a sold
    # position whose portfolio row was dropped, or a stray fill). CR-006:
    # counterpart determination uses the shared identity link; ledger names
    # involved in a canonical collision fail closed instead of linking or
    # warning.
    for name in lots_by_name:
        if name in l_collisions:
            key, detail = collision_of[name]
            issues.append({
                "code": "CANONICAL_NAME_COLLISION", "severity": "blocking",
                "instrument": name,
                "message": _collision_message(name, key, detail),
            })
        elif name not in l2p:
            issues.append({
                "code": "LEDGER_ONLY_LOTS", "severity": "warning", "instrument": name,
                "message": f"ledger has buy fills for {name!r} but no portfolio position",
            })

    blocking = sum(1 for i in issues if i["severity"] == "blocking")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    return {
        "ok": blocking == 0,
        "blocking": blocking,
        "warnings": warnings,
        "checks": checks,
        "issues": issues,
    }
