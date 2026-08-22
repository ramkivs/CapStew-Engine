"""Behavioral guardrail: averaging-into-losses detector (spec §9.2 / Freeze §3.G).

Caution flag, never a hard gate: distinguishes disciplined accumulation from
habitual "chasing the average down". Returns None, "averaging_warn", or
"averaging_block_adds".
"""
from datetime import date


def averaging_flag(lots):
    """lots: FIFO-ordered dicts with trade_date (date), buy_price, pnl."""
    if len(lots) < 3:
        return None
    declining, gaps = 0, []
    prev = lots[0]
    for lot in lots[1:]:
        if lot["buy_price"] <= prev["buy_price"]:
            declining += 1
            gaps.append(max(0, (lot["trade_date"] - prev["trade_date"]).days))
        else:
            declining = 0
        prev = lot
    net_pnl = sum(l["pnl"] for l in lots)
    if declining >= 3 and net_pnl < 0:
        avg_gap = (sum(gaps) / len(gaps)) if gaps else 999
        if declining >= 8 or avg_gap < 30:
            return "averaging_block_adds"
        return "averaging_warn"
    return None


def parse_lots_for_behavior(lots):
    return [
        {
            "trade_date": date.fromisoformat(l["trade_date"]),
            "buy_price": l["buy_price"],
            "pnl": l["pnl"],
        }
        for l in lots
    ]
