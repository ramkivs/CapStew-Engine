"""Stage 2 sub-scores, eligibility tiers, and band mapping (Freeze §3).

Sub-scores are 0-100 where HIGHER = stronger pressure to reduce the position
(more over-sized, more stretched, more decayed, more tax-costly, less compelling,
weaker trend). The composite blends available categories, renormalised over the
available weights, AFTER eligibility classification (Freeze §3 sequence).
"""
WEIGHT_KEYS = [
    "position_sizing", "valuation_stretch", "quality_drift",
    "tax_efficiency", "opportunity_cost", "technical_regime",
]
PROXY_CATEGORIES = {"valuation_stretch", "quality_drift", "opportunity_cost", "technical_regime"}
BAND_EDGES = (31, 56, 76)  # enter thresholds used for the confidence boundary penalty
ASSUMED_SMALL_MICRO_BASIS = "assumed_small_micro"
CLASSIFIED_BUCKET_BASIS = "classified_bucket"
OPPORTUNITY_COST_SOURCE_PEG_PROXY = "peg_proxy"
OPPORTUNITY_COST_SOURCE_WATCHLIST = "watchlist"
OPPORTUNITY_COST_SOURCE_MISSING = "missing"

# Four-state data-quality model (audit item: proxy ≠ missing).
# position_sizing comes from the portfolio file, tax_efficiency from the ledger —
# both authoritative. The other four are v1 proxies (peer-relative/snapshot)
# until their authoritative sources land.
AUTHORITATIVE_CATEGORIES = {"position_sizing", "tax_efficiency"}
CATEGORY_FILE = {
    "position_sizing": "portfolio",
    "tax_efficiency": "ledger",
    "valuation_stretch": "screener",
    "quality_drift": "screener",
    "opportunity_cost": "screener",
    "technical_regime": "screener",
}


def categorize_quality(subs, stale_files, position_sizing_basis=None):
    """Map each category to AUTHORITATIVE | PROXY | MISSING | STALE.

    CR-009: when position sizing is available only through the approved
    small/micro fallback for an unclassified bucket, disclose it as proxy rather
    than authoritative. This does not change the sizing score or gate math.
    """
    stale = set(stale_files or [])
    q = {}
    for k in WEIGHT_KEYS:
        if subs.get(k) is None:
            q[k] = "missing"
        elif k == "position_sizing" and position_sizing_basis == ASSUMED_SMALL_MICRO_BASIS:
            q[k] = "proxy"
        elif k in AUTHORITATIVE_CATEGORIES:
            q[k] = "stale" if CATEGORY_FILE[k] in stale else "authoritative"
        else:
            q[k] = "stale" if CATEGORY_FILE[k] in stale else "proxy"
    return q


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def band_for(bucket, policy):
    tb = policy["target_bands"]
    if bucket == "large":
        return tuple(tb["large"])
    if bucket == "mid":
        return tuple(tb["mid"])
    return tuple(tb["small_micro"])


def band_basis_for(bucket):
    """Return the disclosed sizing-band basis without changing bucket classification."""
    return ASSUMED_SMALL_MICRO_BASIS if bucket is None else CLASSIFIED_BUCKET_BASIS


def sizing_band_evidence(bucket, policy, alloc_pct=None):
    """CR-009 disclosure for the band used by position sizing / G2 evidence."""
    band = band_for(bucket, policy)
    basis = band_basis_for(bucket)
    return {
        "bucket_basis": basis,
        "band_basis": basis,
        "bucket": bucket,
        "band": [float(band[0]), float(band[1])],
        "alloc_pct": alloc_pct,
        "cap_pct": float(band[1]),
    }


def _is_financial(sub_sector):
    s = (sub_sector or "").lower()
    return any(t in s for t in ("bank", "nbfc", "finance"))


# --- category sub-scores -----------------------------------------------------

def position_sizing(alloc_pct, bucket, policy):
    """0-100; over-allocation pushes toward booking."""
    if alloc_pct is None:
        return None
    band = band_for(bucket, policy)
    cap = policy["max_single_stock_pct"]
    rebal = band[1] * policy["rebalance_trigger_multiple"]
    if alloc_pct >= cap:
        return 100
    if alloc_pct > rebal:
        return 90
    if alloc_pct > band[1]:
        over = (alloc_pct - band[1]) / max(rebal - band[1], 1e-9)
        return round(_clamp(56 + over * 33))
    if alloc_pct < band[0]:
        under = (band[0] - alloc_pct) / max(band[0], 1e-9)
        return round(_clamp(30 - under * 20))
    return 35


def valuation_stretch(f):
    """0-100; peer premium + absolute PE level. Own-5yr-median is a gap (proxy)."""
    if not f:
        return None
    pe = f.get("pe_ratio")
    pe_prem = f.get("pe_premium_vs_subsector")
    pb_prem = f.get("pb_premium_vs_subsector")
    if pe is None or pe <= 0:
        if pb_prem is None:
            return None
        return round(_clamp(50 + (pb_prem - 1.0) * 50))
    base = 50 + ((pe_prem if pe_prem is not None else 1.0) - 1.0) * 50
    level = _clamp((pe - 15.0) * 2.0, 0, 40)
    return round(_clamp(base + level))


def quality_drift(f):
    """0-100 badness (higher = more decay). Sector-aware: banks/NBFCs are
    structurally leveraged with low accounting ROCE, so debt/ROCE penalties are
    skipped for them."""
    if not f:
        return None
    s = 0.0
    fin = _is_financial(f.get("sub_sector"))
    roe, roce = f.get("roe"), f.get("roce")
    if roe is not None:
        if roe < 0:
            s += 40
        elif roe < 10:
            s += 20
    if roce is not None and not fin:
        if roce < 0:
            s += 40
        elif roce < 8:
            s += 20
    de = f.get("debt_equity")
    if de is not None and not fin:
        if de > 4:
            s += 40
        elif de > 2:
            s += 25
    ic = f.get("interest_coverage")
    if ic is not None and ic < 1.5 and not fin:
        s += 20
    eh, ef = f.get("eps_growth_1y_hist"), f.get("eps_growth_1y_fwd")
    if eh is not None and eh < 0:
        s += 25
    if ef is not None and ef < 0:
        s += 15
    pe = f.get("pe_ratio")
    if pe is not None and pe <= 0:
        s += 30
    return round(_clamp(s))


def tax_efficiency(oldest_days_to_ltcg, any_ltcg_eligible):
    """0-100 cost of selling now (higher = more tax drag = dampens booking)."""
    if any_ltcg_eligible:
        return 25
    if oldest_days_to_ltcg is None:
        return 50
    return round(_clamp(30 + 45 * min(oldest_days_to_ltcg / 365.0, 1.0)))


def opportunity_cost(f):
    """0-100 live Opportunity Cost proxy via PEG.

    D-14/default-hurdle and watchlist scoring are not operational scorer inputs
    unless separately authorized; preserve the existing PEG proxy behavior.
    """
    if not f:
        return None
    peg = f.get("peg_ratio")
    if peg is None or peg <= 0:
        return 50
    return round(_clamp(50 + (peg - 1.5) * 40))


def opportunity_cost_source(f):
    """CR-007 source provenance for the Opportunity Cost category.

    Watchlist and D-14 hurdles are not operational in this CR. When fundamentals
    exist, the scorer remains the authorized PEG proxy, including the existing
    neutral proxy score for missing/invalid PEG. With no fundamentals, the
    category remains missing.
    """
    if not f:
        return OPPORTUNITY_COST_SOURCE_MISSING
    return OPPORTUNITY_COST_SOURCE_PEG_PROXY


def opportunity_cost_evidence(f):
    """Return non-decision provenance for Opportunity Cost scoring."""
    return {"source": opportunity_cost_source(f), "score": opportunity_cost(f)}


def technical_regime(f):
    """0-100; price vs 200D SMA (no 50D/RS in v1 → proxy)."""
    if not f:
        return None
    close, sma = f.get("close_price"), f.get("sma_200")
    if close is None or sma is None or sma <= 0:
        return None
    return round(_clamp(50 - (close / sma - 1.0) * 500))


# --- composite, eligibility, bands -------------------------------------------

def composite(subs, weights):
    num, den = 0.0, 0.0
    for k in WEIGHT_KEYS:
        v = subs.get(k)
        if v is not None:
            num += v * weights.get(k, 0)
            den += weights.get(k, 0)
    return round(num / den, 1) if den > 0 else None


def eligibility(subs, weights):
    den = sum(weights.get(k, 0) for k in WEIGHT_KEYS) or 1.0
    avail = [k for k in WEIGHT_KEYS if subs.get(k) is not None]
    coverage = sum(weights.get(k, 0) for k in avail) / den
    if coverage >= 0.8:
        tier = "NORMAL"
    elif coverage >= 0.6:
        tier = "ADVISORY"
    else:
        tier = "INSUFFICIENT"
    critical = [k for k in ("valuation_stretch", "quality_drift") if k not in avail]
    return {
        "coverage": round(coverage, 4),
        "tier": tier,
        "missing_weight": round(1.0 - coverage, 4),
        "critical_categories_missing": critical,
    }


def band_of(score):
    if score <= 30:
        return "HOLD"
    if score <= 55:
        return "WATCH"
    if score <= 75:
        return "TRIM"
    return "HARVEST"


def apply_eligibility_caps(decision, tier, critical):
    """Freeze §3: eligibility can cap a G4 decision downward (never upward)."""
    if tier == "INSUFFICIENT":
        return "WATCH", "INSUFFICIENT evidence — forced WATCH"
    if decision == "HARVEST" and "valuation_stretch" in critical:
        return "WATCH", "HARVEST requires valuation evidence"
    if decision == "TRIM" and "valuation_stretch" in critical and "quality_drift" in critical:
        return "WATCH", "TRIM requires valuation or quality evidence"
    return decision, None
