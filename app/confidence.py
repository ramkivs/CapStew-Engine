"""Confidence model (Freeze §4).

confidence == round(clamp(100 − Σ penalties, 20, 95)).
The breakdown lists the PENALTIES, not confidence parts — do not code it as a sum
of parts. ADVISORY tier caps confidence at 55 (applied by the caller).
"""
import statistics


def confidence_from_penalties(penalties):
    raw = 100 - sum(penalties.values())
    return int(round(max(20, min(95, raw))))


def compute_penalties(subs, coverage, composite_score, stale_count, proxy_count):
    p_missing = round(25 * (1 - coverage), 2)
    avail = [v for v in subs.values() if v is not None]
    sd = statistics.stdev(avail) if len(avail) >= 2 else 0.0
    p_divergence = round(min(15.0, 0.6 * sd + 5.0), 2)  # single engine in Phase 2 → E = 5
    d = min((abs(composite_score - e) for e in (31, 56, 76)), default=999.0)
    p_boundary = round(max(0.0, 5.0 - d), 2) if d <= 5 else 0.0
    p_proxy = round(min(10, 5 * proxy_count), 2)
    p_staleness = round(min(6, 3 * stale_count), 2)
    return {
        "missing_data": p_missing,
        "divergence": p_divergence,
        "boundary": p_boundary,
        "proxy": p_proxy,
        "staleness": p_staleness,
    }
