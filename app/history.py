"""CR-024 (EMM-F2) — date-indexed historical fundamentals store/query,
G-04 own-history PE/PB median, G1 historical legs (evidence surfaces only).

READ-ONLY over the CR-022 snapshot archive (``data/archive``). This module
writes nothing: it reads the append-only manifest and the archived normalized
foundation corpora and derives historical evidence. It never fabricates
observations — an observation exists only where a screener snapshot was
actually archived (event-driven capture retained, F2-D2-A). Pre-CR-022
history is permanently unavailable (F2-D6-A).

Frozen methodology (authority-frozen, do not reinterpret):

* G04-MEDIAN-METHODOLOGY-v1 — separate PE and PB 5-year medians; trading-day
  observation dates; rolling five-calendar-year window ending at as-of;
  >= 24 valid observations per metric; BOTH PE and PB minimums required for
  eligibility; missing observations omitted; mathematically
  invalid/non-finite observations excluded; NO winsorization; full
  observation- and median-level provenance. IMPLEMENTED BUT NOT ACTIVATED:
  the production peer-relative PE/PB proxy remains the scoring input
  (G04-D9-A / F2-I5-A).

* G1-HISTORY-LEGS-METHODOLOGY-v1 — quality_drop: current quality observation
  vs prior eligible comparable observation (year-over-year); fires when
  deterioration >= 20 (equality fires); missing history => unavailable /
  non-firing; no interpolation. pledge_qoq: promoter pledge percentage,
  latest calendar quarter vs immediately preceding quarter; fires when the
  increase >= 5 percentage points (equality fires); missing either quarter
  => unavailable / non-firing; no interpolation. Full provenance.
  IMPLEMENTED AS EVIDENCE ONLY: current G1 gate semantics are untouched
  (F2-I6-A / G1-D11-A / G1-D12-A).

Implementation-defined conventions (F2-I2 / F2-I3 authorized; deterministic,
documented, tested, surfaced for authority review before closure):

C-1  Even-count median convention (G04): arithmetic mean of the two central
     order statistics of the valid sorted observations.
C-2  Observation-date derivation (G04/G1): the archived foundation corpus
     ``provenance.sources.screener.as_of`` — the engine-resolved F2-D3 dual-
     timestamp date (explicit > filename > labelled mtime fallback). When
     several archived snapshots carry the same observation date, the one from
     the ingest event with the GREATEST manifest ``seq`` (the most recently
     archived) is authoritative. Dates outside archived snapshots do not
     exist.
C-3  Calendar endpoint inclusion (G04): trailing window
     ``[as_of - 5 calendar years, as_of]`` with BOTH endpoints inclusive.
     Year subtraction uses a leap clamp (Feb 29 -> Feb 28 when the target
     year has no Feb 29).
C-4  Quality-observation composition (G1): the engine's existing
     ``scoring.quality_drift`` sub-score (0-100, higher = more decay;
     CALCULATION_VERSION 2.1 math, sector-aware) recomputed from each
     archived snapshot's fundamentals. Deterioration = INCREASE of the drift
     score; the frozen "20% deterioration" threshold is 20.0 points on the
     0-100 badness scale (``>=`` fires). Rationale: recomputing the frozen
     engine measure keeps production and historical legs on identical math;
     a relative-percent change of raw fundamentals is ill-defined across
     sign changes and was therefore not chosen.
C-5  Pledge quarter-boundary convention (G1): CALENDAR quarters
     (Q1 = Jan-Mar ... Q4 = Oct-Dec). The per-quarter value is the
     observation with the LATEST observation date inside that quarter (ties
     broken by greatest manifest seq). "Latest quarter" = the calendar
     quarter containing the most recent observation <= as_of; "preceding
     quarter" = the immediately previous calendar quarter.

Determinism (Freeze §8): every function is a pure function of the archive
content plus its explicit arguments. No wall-clock, run-date or locale input
enters any computation; ``as_of`` is always an explicit parameter.
"""
import json
import math
from datetime import date
from pathlib import Path

from . import archive, config
from .scoring import quality_drift

METHODOLOGY_VERSION_G04 = "G04-MEDIAN-METHODOLOGY-v1"
METHODOLOGY_VERSION_G1 = "G1-HISTORY-LEGS-METHODOLOGY-v1"

G04_LOOKBACK_YEARS = 5
G04_MIN_OBSERVATIONS = 24
G1_QUALITY_DROP_THRESHOLD_POINTS = 20.0   # >= fires (G1-D2, equality confirmed)
G1_PLEDGE_QOQ_THRESHOLD_PP = 5.0          # >= fires (G1-D6, equality confirmed)
QUALITY_OBSERVATION_METRIC = "quality_drift"

CONVENTIONS = {
    "C-1": "even-count median = mean of the two central order statistics",
    "C-2": ("observation_date = archived corpus provenance.sources.screener.as_of; "
            "duplicate dates resolved by greatest manifest seq (latest ingestion wins)"),
    "C-3": ("trailing [as_of - 5 calendar years, as_of], both endpoints inclusive; "
            "leap clamp Feb 29 -> Feb 28"),
    "C-4": ("quality observation = scoring.quality_drift recomputed from the archived "
            "snapshot fundamentals; deterioration = point increase; 20% = 20.0 points"),
    "C-5": ("calendar quarters; per-quarter value = latest-in-quarter observation; "
            "latest quarter = quarter of newest observation <= as_of"),
}


# ---- helpers -------------------------------------------------------------------


def _root(root=None) -> Path:
    return Path(root or config.ARCHIVE_ROOT)


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _minus_years(d: date, years: int) -> date:
    """Calendar-year subtraction with leap clamp (C-3)."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29 -> Feb 28
        return d.replace(year=d.year - years, day=28)


def _quarter(d: date):
    """Calendar quarter key (C-5): (year, 1..4)."""
    return (d.year, (d.month - 1) // 3 + 1)


def _prev_quarter(q):
    year, qn = q
    return (year - 1, 4) if qn == 1 else (year, qn - 1)


def _valid_multiple(value) -> bool:
    """Mathematically valid PE/PB observation (G04-D5-A): finite and > 0.

    Zero/negative multiples (loss-making earnings / negative book value) are
    mathematically invalid valuation multiples and are excluded; valid values
    are never winsorized.
    """
    return (value is not None and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def _median(sorted_values):
    """C-1 convention: middle order statistic; even counts average the two
    central order statistics."""
    n = len(sorted_values)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_values[mid])
    return float((sorted_values[mid - 1] + sorted_values[mid]) / 2.0)


# ---- observation extraction (date-indexed store) --------------------------------


def _ingest_entries(root=None):
    return [e for e in archive.read_manifest(root=_root(root))
            if e.get("kind") == "ingest"]


def _observations_from_entry(entry, root_path) -> list[dict]:
    """One archived foundation corpus -> one observation per position.

    Observation date = corpus provenance.sources.screener.as_of (C-2). No
    observation is created for a date outside an actually archived snapshot.
    """
    files = {rec.get("slot"): rec for rec in entry.get("files", [])}
    screener_rec = files.get("screener", {})
    fsha = entry.get("foundation_sha256")
    try:
        corpus = json.loads(archive.read_blob(fsha, root=root_path).decode("utf-8"))
    except (OSError, ValueError, TypeError):
        return []  # unreadable/removed corpus => no observations (never fabricated)
    sources = (corpus.get("provenance") or {}).get("sources") or {}
    scr = sources.get("screener") or {}
    obs_date = scr.get("as_of") or entry.get("run_as_of")
    if obs_date is None:
        return []
    seq = entry.get("seq")
    observations = []
    for pos in corpus.get("positions", []):
        instrument = pos.get("instrument")
        if not instrument:
            continue
        fundamentals = pos.get("fundamentals") or {}
        metrics = {k: v for k, v in fundamentals.items()
                   if v is not None and isinstance(v, (int, float))}
        if pos.get("pledge_pct") is not None:
            metrics["pledge_pct"] = pos["pledge_pct"]
        if not metrics:
            continue  # position without screener data -> no observation
        observations.append({
            "instrument": instrument,
            "observation_date": obs_date,
            "run_id": entry.get("run_id"),
            "seq": seq,
            "metrics": metrics,
            "sub_sector": fundamentals.get("sub_sector"),
            "provenance": {
                "source": "CR-022 snapshot archive",
                "owner": "authority (local archive)",
                "source_as_of": screener_rec.get("declared_source_as_of"),
                "as_of_source": scr.get("as_of_source"),
                "source_version": {
                    "engine_version": entry.get("engine_version"),
                    "normalization_version": entry.get("normalization_version"),
                },
                "snapshot": {
                    "run_id": entry.get("run_id"),
                    "seq": seq,
                    "foundation_sha256": fsha,
                    "foundation_blob": entry.get("foundation_blob"),
                    "screener_sha256": screener_rec.get("sha256"),
                    "screener_blob": screener_rec.get("blob"),
                },
            },
        })
    return observations


def all_observations(root=None) -> list[dict]:
    """Every observation extractable from the archive (deterministic order).

    Sorted by (observation_date, seq, instrument); duplicate (instrument, date)
    pairs are collapsed keeping the greatest manifest seq (C-2).
    """
    root_path = _root(root)
    raw = []
    for entry in _ingest_entries(root_path):
        raw.extend(_observations_from_entry(entry, root_path))
    raw.sort(key=lambda o: (o["observation_date"], o["seq"], o["instrument"]))
    latest = {}
    for obs in raw:
        latest[(obs["instrument"], obs["observation_date"])] = obs
    return sorted(latest.values(),
                  key=lambda o: (o["observation_date"], o["instrument"]))


def query_fundamentals(instrument: str, metric: str | None = None,
                       start=None, end=None, as_of=None, root=None) -> dict:
    """Date-indexed lookup WITHOUT run_id (F2-D1-A).

    Filters: exact instrument; optional metric key; inclusive [start, end]
    observation window; ``as_of`` caps observation dates (<= as_of). Unknown
    metric keys or absent dates simply match nothing — nothing is fabricated.
    """
    start_d = _parse_date(start) if start else None
    end_d = _parse_date(end) if end else None
    as_of_d = _parse_date(as_of) if as_of else None
    out = []
    for obs in all_observations(root):
        if obs["instrument"] != instrument:
            continue
        d = _parse_date(obs["observation_date"])
        if as_of_d and d > as_of_d:
            continue
        if start_d and d < start_d:
            continue
        if end_d and d > end_d:
            continue
        if metric is not None and metric not in obs["metrics"]:
            continue
        rec = dict(obs)
        rec["value"] = obs["metrics"].get(metric) if metric is not None else None
        out.append(rec)
    return {"instrument": instrument, "metric": metric,
            "start": start, "end": end, "as_of": as_of,
            "observation_count": len(out), "observations": out}


def latest_archived_as_of(root=None):
    """Deterministic default as_of: the newest ingest run_as_of in the archive
    (explicit; never wall-clock)."""
    dates = [e.get("run_as_of") for e in _ingest_entries(root) if e.get("run_as_of")]
    return max(dates) if dates else None


# ---- G-04 own-history PE/PB median (implemented, NOT activated) -------------------


def pe_pb_medians(instrument: str, as_of, root=None) -> dict:
    """G04-MEDIAN-METHODOLOGY-v1 evaluation for one instrument at one as_of.

    EVIDENCE SURFACE ONLY — nothing here feeds scoring (F2-I5-A).
    """
    as_of_d = _parse_date(as_of)
    window_start = _minus_years(as_of_d, G04_LOOKBACK_YEARS)
    window_end = as_of_d
    obs = []
    for o in all_observations(root):
        if o["instrument"] != instrument:
            continue
        d = _parse_date(o["observation_date"])
        if window_start <= d <= window_end:          # C-3 inclusive endpoints
            obs.append(o)
    obs.sort(key=lambda o: o["observation_date"])

    per_metric = {}
    for metric, label in (("pe_ratio", "pe"), ("pb_ratio", "pb")):
        values, valid_obs, excluded_invalid = [], [], 0
        for o in obs:
            v = o["metrics"].get(metric)
            if v is None:
                continue                              # G04-D4: missing omitted
            if not _valid_multiple(v):
                excluded_invalid += 1                 # G04-D5: invalid excluded
                continue
            values.append(float(v))
            valid_obs.append(o)                       # no winsorization (G04-D5-A)
        values.sort()
        per_metric[label] = {
            "metric": metric,
            "valid_observation_count": len(values),
            "excluded_invalid_count": excluded_invalid,
            "minimum_required": G04_MIN_OBSERVATIONS,
            "eligible": len(values) >= G04_MIN_OBSERVATIONS,
            "median": _median(values),
            "observations": valid_obs,
        }
    eligible = per_metric["pe"]["eligible"] and per_metric["pb"]["eligible"]  # G04-D7-A
    return {
        "instrument": instrument,
        "as_of": as_of_d.isoformat(),
        "methodology_version": METHODOLOGY_VERSION_G04,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat(),
                   "lookback_years": G04_LOOKBACK_YEARS,
                   "endpoint_semantics": "inclusive both endpoints (C-3)"},
        "eligible": eligible,
        "activation_state": "NOT ACTIVATED — peer-relative proxy remains the "
                            "production scoring input (G04-D9-A / F2-I5-A)",
        "pe": per_metric["pe"],
        "pb": per_metric["pb"],
        "conventions": CONVENTIONS,
        "provenance": {"source": "CR-022 snapshot archive",
                       "archive_root": str(_root(root)),
                       "observation_derivation": CONVENTIONS["C-2"]},
    }


# ---- G1 history legs (implemented as evidence; current gate semantics unchanged) -


def _quality_value(obs):
    """C-4: quality_drift sub-score recomputed from the snapshot fundamentals."""
    metrics = obs["metrics"]
    if not metrics:
        return None
    f = dict(metrics)
    if obs.get("sub_sector") is not None:
        f["sub_sector"] = obs["sub_sector"]
    return quality_drift(f)


def quality_drop(instrument: str, as_of, root=None) -> dict:
    """G1-METHODOLOGY-v1 quality_drop leg (YoY, >= 20 points fires)."""
    as_of_d = _parse_date(as_of)
    obs = [o for o in all_observations(root)
           if o["instrument"] == instrument
           and _parse_date(o["observation_date"]) <= as_of_d
           and _quality_value(o) is not None]
    obs.sort(key=lambda o: o["observation_date"])
    base = {
        "instrument": instrument,
        "as_of": as_of_d.isoformat(),
        "leg": "quality_drop",
        "methodology_version": METHODOLOGY_VERSION_G1,
        "quality_observation_metric": QUALITY_OBSERVATION_METRIC,
        "threshold_points": G1_QUALITY_DROP_THRESHOLD_POINTS,
        "operator": ">=",
        "comparison_period": "year_over_year",
        "conventions": CONVENTIONS,
        "activation_state": "EVIDENCE ONLY — current G1 gate semantics unchanged "
                            "(F2-I6-A / G1-D11-A)",
    }
    current = obs[-1] if obs else None
    prior_target = _minus_years(as_of_d, 1)
    priors = [o for o in obs if _parse_date(o["observation_date"]) <= prior_target]
    prior = priors[-1] if priors else None
    if current is None or prior is None:
        missing = "current" if current is None else ("prior" if prior is None else None)
        return {**base, "available": False, "fired": False,
                "reason": f"missing required {missing} history — leg unavailable, "
                          "non-firing (G1-D4-A); no interpolation",
                "prior_target_date": prior_target.isoformat()}
    cur_q = _quality_value(current)
    pri_q = _quality_value(prior)
    deterioration = round(cur_q - pri_q, 4)
    return {**base, "available": True,
            "fired": deterioration >= G1_QUALITY_DROP_THRESHOLD_POINTS,
            "deterioration_points": deterioration,
            "prior_target_date": prior_target.isoformat(),
            "current": {"observation_date": current["observation_date"],
                        "quality_observation": cur_q, "provenance": current["provenance"]},
            "prior": {"observation_date": prior["observation_date"],
                      "quality_observation": pri_q, "provenance": prior["provenance"]}}


def pledge_qoq(instrument: str, as_of, root=None) -> dict:
    """G1-METHODOLOGY-v1 pledge_qoq leg (QoQ, >= 5 pp fires)."""
    as_of_d = _parse_date(as_of)
    obs = [o for o in all_observations(root)
           if o["instrument"] == instrument
           and "pledge_pct" in o["metrics"]
           and _parse_date(o["observation_date"]) <= as_of_d]
    obs.sort(key=lambda o: (o["observation_date"], o["seq"]))
    base = {
        "instrument": instrument,
        "as_of": as_of_d.isoformat(),
        "leg": "pledge_qoq",
        "methodology_version": METHODOLOGY_VERSION_G1,
        "metric": "promoter pledge percentage",
        "threshold_pp": G1_PLEDGE_QOQ_THRESHOLD_PP,
        "operator": ">=",
        "comparison_period": "quarter_over_quarter",
        "conventions": CONVENTIONS,
        "activation_state": "EVIDENCE ONLY — current G1 gate semantics unchanged "
                            "(F2-I6-A / G1-D11-A)",
    }
    if not obs:
        return {**base, "available": False, "fired": False,
                "reason": "no pledge history — leg unavailable, non-firing (G1-D8-A)"}
    latest = obs[-1]
    latest_date = _parse_date(latest["observation_date"])
    latest_q = _quarter(latest_date)
    preceding_q = _prev_quarter(latest_q)
    preceding = [o for o in obs if _quarter(_parse_date(o["observation_date"])) == preceding_q]
    if not preceding:
        return {**base, "available": False, "fired": False,
                "reason": f"preceding quarter {preceding_q} has no archived observation "
                          "— leg unavailable, non-firing (G1-D8-A)",
                "latest_quarter": {"year": latest_q[0], "quarter": latest_q[1]}}
    prev = preceding[-1]
    increase = round(latest["metrics"]["pledge_pct"] - prev["metrics"]["pledge_pct"], 4)
    return {**base, "available": True,
            "fired": increase >= G1_PLEDGE_QOQ_THRESHOLD_PP,
            "increase_pp": increase,
            "latest_quarter": {"year": latest_q[0], "quarter": latest_q[1],
                               "observation_date": latest["observation_date"],
                               "pledge_pct": latest["metrics"]["pledge_pct"],
                               "provenance": latest["provenance"]},
            "preceding_quarter": {"year": preceding_q[0], "quarter": preceding_q[1],
                                  "observation_date": prev["observation_date"],
                                  "pledge_pct": prev["metrics"]["pledge_pct"],
                                  "provenance": prev["provenance"]}}


def g1_legs(instrument: str, as_of, root=None) -> dict:
    return {"instrument": instrument,
            "quality_drop": quality_drop(instrument, as_of, root=root),
            "pledge_qoq": pledge_qoq(instrument, as_of, root=root)}
