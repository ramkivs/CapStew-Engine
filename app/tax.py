"""Tax-year subsystem (Phase 3A) — separate domain module from DecisionEngine.

Indian listed-equity capital gains, per-lot FIFO (spec §9):
  - LTCG: held > 12 months → 12.5% above ₹1.25L annual exemption (S.112A)
  - STCG: held ≤ 12 months → 20% (S.111A)
  - Set-off (S.74): STCL offsets STCG then LTCG; LTCL offsets LTCG only;
    unabsorbed losses carry forward 8 assessment years (age 8 lapses).
  - No wash-sale rule (spec §2.11): sell-and-rebuy to reset basis is legal (GAAR caveat).

This module owns realised-gain computation, classification, set-off, exemption,
headroom, carry-forward, and tax-aware sequencing. It never mutates the engine's
decision state — it answers "what are the tax consequences of these sells".
"""
from decimal import Decimal, ROUND_HALF_UP

from .normalize import parse_date

LTCG_RATE = Decimal("0.125")
STCG_RATE = Decimal("0.20")
LTCG_EXEMPTION = Decimal("125000")
CARRY_FORWARD_YEARS = 8
LTCG_PERIOD_DAYS = 365

D = Decimal


def _d2(x):
    return float(D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP))


# --- classification -----------------------------------------------------------

def classify_gain(gain, days_held, ltcg_period=LTCG_PERIOD_DAYS):
    """Return LTCG | STCG | LTCL | STCL. Strict: LTCG needs days_held > period."""
    long_term = days_held > ltcg_period
    gain = D(gain)
    if gain >= 0:
        return "LTCG" if long_term else "STCG"
    return "LTCL" if long_term else "STCL"


# --- FIFO sell matching ------------------------------------------------------

def match_sells_fifo(lots, sells, ltcg_period=LTCG_PERIOD_DAYS):
    """Match sell fills to buy lots FIFO (oldest first), Indian tax matching.

    lots:  list of {lot_id, qty, buy_price, trade_date (date)}
    sells: list of {instrument, qty, sell_price, sell_date (date)}
    Returns realized records: one row per (sell × lot) slice, each with its own
    holding period and LTCG/STCG classification.
    """
    pool = [dict(l) for l in lots]
    pool.sort(key=lambda l: (l["trade_date"], l.get("lot_id", 0)))
    realized = []
    idx = 0
    for s in sorted(sells, key=lambda x: x["sell_date"]):
        remaining = D(s["qty"])
        while remaining > 0 and idx < len(pool):
            lot = pool[idx]
            if lot["qty"] <= 0:
                idx += 1
                continue
            take = min(D(lot["qty"]), remaining)
            gain = (D(s["sell_price"]) - D(lot["buy_price"])) * take
            days = (s["sell_date"] - lot["trade_date"]).days
            realized.append({
                "instrument": s.get("instrument"),
                "lot_id": lot.get("lot_id"),
                "sell_date": s["sell_date"],
                "qty": take,
                "buy_price": D(lot["buy_price"]),
                "sell_price": D(s["sell_price"]),
                "gain": gain,
                "holding_days": days,
                "type": classify_gain(gain, days, ltcg_period),
            })
            lot["qty"] = D(lot["qty"]) - take
            remaining -= take
            if lot["qty"] <= 0:
                idx += 1
    return realized


# --- tax-year summary with S.74 set-off --------------------------------------

def _usable(entries):
    return sorted([(D(a), int(age)) for (a, age) in entries if int(age) < CARRY_FORWARD_YEARS],
                  key=lambda x: x[1])


def tax_year_summary(realized, exemption=LTCG_EXEMPTION, carry_in=None, fy=None):
    """Aggregate realised records into a full FY summary with S.74 set-off.

    carry_in: {"ltcl": [(amount, age_years), ...], "stcl": [(amount, age_years), ...]}
    Losses older than CARRY_FORWARD_YEARS lapse (cannot be used).
    Set-off order (current-year before brought-forward):
      1. current LTCL → current LTCG
      2. current STCL → current STCG, leftover → LTCG
      3. carried LTCL → remaining LTCG (oldest first)
      4. carried STCL → remaining STCG, then LTCG
      5. ₹1.25L exemption on final LTCG
    """
    ltcg = stcg = ltcl = stcl = D(0)
    for r in realized:
        g = D(r["gain"])
        t = r["type"]
        if t == "LTCG":
            ltcg += g
        elif t == "STCG":
            stcg += g
        elif t == "LTCL":
            ltcl += -g
        elif t == "STCL":
            stcl += -g

    carry_in = carry_in or {"ltcl": [], "stcl": []}
    c_ltcl = _usable(carry_in.get("ltcl", []))
    c_stcl = _usable(carry_in.get("stcl", []))

    # 1 — current LTCL vs current LTCG
    ltcg_net = ltcg - ltcl
    ltcl_cf = D(0)
    if ltcg_net < 0:
        ltcl_cf = -ltcg_net
        ltcg_net = D(0)

    # 2 — current STCL vs current STCG
    stcg_net = stcg - stcl
    stcl_left = D(0)
    if stcg_net < 0:
        stcl_left = -stcg_net
        stcg_net = D(0)

    # 3 — leftover current STCL vs remaining LTCG
    stcl_cf = D(0)
    if stcl_left > 0:
        ltcg_net -= stcl_left
        if ltcg_net < 0:
            stcl_cf = -ltcg_net
            ltcg_net = D(0)

    # 4 — carried LTCL vs remaining LTCG
    ltcl_cf_remaining = []
    for amt, age in c_ltcl:
        if ltcg_net <= 0:
            ltcl_cf_remaining.append((amt, age))
            continue
        used = min(amt, ltcg_net)
        ltcg_net -= used
        if amt - used > 0:
            ltcl_cf_remaining.append((amt - used, age))

    # 5 — carried STCL vs remaining STCG then LTCG
    stcl_cf_remaining = []
    for amt, age in c_stcl:
        if stcg_net > 0:
            used = min(amt, stcg_net)
            stcg_net -= used
            amt -= used
        if amt > 0 and ltcg_net > 0:
            used = min(amt, ltcg_net)
            ltcg_net -= used
            amt -= used
        if amt > 0:
            stcl_cf_remaining.append((amt, age))

    exemption_used = min(exemption, ltcg_net)
    ltcg_taxable = ltcg_net - exemption_used
    tax = LTCG_RATE * ltcg_taxable + STCG_RATE * stcg_net

    def age_out(entries):
        out = []
        for amt, age in entries:
            amt, age = D(amt), int(age)
            if amt > 0 and age + 1 < CARRY_FORWARD_YEARS:
                out.append((amt, age + 1))
        return out

    carry_out = {
        "ltcl": age_out([(ltcl_cf, 0)] + ltcl_cf_remaining),
        "stcl": age_out([(stcl_cf, 0)] + stcl_cf_remaining),
    }

    return {
        "fy": fy,
        "gross": {"ltcg": _d2(ltcg), "stcg": _d2(stcg), "ltcl": _d2(ltcl), "stcl": _d2(stcl)},
        "set_off": {
            "ltcl_used": _d2(ltcl - ltcl_cf),
            "stcl_used_against_stcg": _d2(stcl - stcl_left),
            "stcl_used_against_ltcg": _d2(stcl_left - stcl_cf),
        },
        "net": {"ltcg": _d2(ltcg_net), "stcg": _d2(stcg_net)},
        "exemption": {"used": _d2(exemption_used), "headroom": _d2(exemption - exemption_used)},
        "taxable": {"ltcg": _d2(ltcg_taxable), "stcg": _d2(stcg_net)},
        "tax": {"ltcg": _d2(LTCG_RATE * ltcg_taxable), "stcg": _d2(STCG_RATE * stcg_net),
                "total": _d2(tax)},
        "carry_forward_out": {
            "ltcl": [(float(a), age) for a, age in carry_out["ltcl"]],
            "stcl": [(float(a), age) for a, age in carry_out["stcl"]],
        },
    }


# --- unrealised split (open positions) ---------------------------------------

def unrealized_split(lots):
    """Split the open position's unrealized P&L into LTCG/STCG/LTCL/STCL buckets."""
    ltcg = stcg = ltcl = stcl = D(0)
    for lot in lots:
        gain = (D(lot["ltp"]) - D(lot["buy_price"])) * D(lot["qty"])
        if gain >= 0:
            if lot["ltcg_eligible"]:
                ltcg += gain
            else:
                stcg += gain
        else:
            if lot["ltcg_eligible"]:
                ltcl += -gain
            else:
                stcl += -gain
    return {"ltcg": _d2(ltcg), "stcg": _d2(stcg), "ltcl": _d2(ltcl), "stcl": _d2(stcl)}


# --- tax-aware sequencing -----------------------------------------------------

def rank_candidates(candidates, lots_by, exemption=LTCG_EXEMPTION):
    """Rank TRIM/HARVEST candidates tax-efficiently.

    Order: (1) LTCG-eligible unrealized gains (tax-free up to headroom),
           (2) STCG gains ascending (20% drag).
    Returns a list ordered best-to-book-first.
    """
    rows = []
    for h in candidates:
        lots = lots_by.get(h["instrument"], [])
        split = unrealized_split(lots)
        ltcg_gain = D(str(split["ltcg"]))
        stcg_gain = D(str(split["stcg"]))
        # estimate tax if fully realised this year
        est = D(0)
        if ltcg_gain > 0:
            est += LTCG_RATE * max(D(0), ltcg_gain - exemption)
        est += STCG_RATE * stcg_gain
        rows.append({
            "instrument": h["instrument"],
            "decision": h["decision"],
            "ltcg_gain": float(ltcg_gain),
            "stcg_gain": float(stcg_gain),
            "est_tax_if_realised": float(est.quantize(D("0.01"), rounding=ROUND_HALF_UP)),
        })
    rows.sort(key=lambda r: (-r["ltcg_gain"], r["stcg_gain"], r["est_tax_if_realised"]))
    return rows
