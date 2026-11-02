"""Policy loading + validation. Policy is data, not code (ADR-7 / Freeze §14).

policy/policy.yaml is the OPERATIONAL serialization of the signed D-01…D-15
policy in Methodology Freeze §14 — it must not introduce or silently alter
policy values.

Layering (personal local app):
  * `policy/policy.yaml`  — shipped signed defaults, tracked in git, NEVER
    written by the running application.
  * `data/policy.yaml`    — the user's committed overrides, written by
    `PUT /api/v1/policy`. Takes precedence when present.
Deleting `data/policy.yaml` (or `POST /api/v1/policy/reset`) restores the
shipped defaults. This keeps user tuning persistent across git operations while
protecting the signed file from unintended modification.
"""
from pathlib import Path

import yaml

from . import config

# Keys the application is allowed to read/write. Anything else is rejected, so a
# malformed or hostile PUT cannot inject arbitrary keys into the signed policy.
POLICY_KEYS = frozenset({
    "policy_version", "effective_from", "buckets", "target_bands",
    "max_single_stock_pct", "rebalance_trigger_multiple", "quality_floor",
    "quality_drop_pts", "pledge_threshold_pct", "pledge_qoq_pp",
    "ltcg_defer_window_days", "valuation_extreme_suppress", "bands", "weights",
    "rerating_strong_pct", "rerating_critical_pct", "min_position_alloc_pct",
    "min_position_value", "participation_adv_pct", "participation_position_pct",
    "txn_cost_liquid_pct", "txn_cost_microcap_pct", "hurdle_nifty_pct",
    "hurdle_liquid_pct", "review_cadence", "ltcg_period_days",
    "recon_tolerance_inr",
})

# D-09: category weights must sum to exactly 100.
WEIGHT_SUM = 100


def policy_path() -> Path:
    """The file the engine actually reads (user override if present).

    Resolved through the `config` module on every call so tests (and any other
    caller) can redirect it, exactly as `store.py` does for STORE_PATH.
    """
    user = config.USER_POLICY_PATH
    return user if user.exists() else config.POLICY_PATH


def load_policy(path: Path = None) -> dict:
    with open(path or policy_path(), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_defaults() -> dict:
    """The shipped signed defaults, ignoring any user override."""
    with open(config.POLICY_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def commit_policy(policy: dict) -> dict:
    """Write the user's policy to the app-managed data directory."""
    dest = config.USER_POLICY_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(policy, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return policy


def reset_policy() -> dict:
    """Discard the user override and return to the shipped signed defaults."""
    if config.USER_POLICY_PATH.exists():
        config.USER_POLICY_PATH.unlink()
    return load_defaults()


def get_ltcg_period_days(policy: dict) -> int:
    return int(policy.get("ltcg_period_days", 365))


def get_recon_tolerance(policy: dict) -> float:
    return float(policy.get("recon_tolerance_inr", 0.01))


def validate_policy(policy: dict) -> list:
    """Freeze §10 — return a list of violation strings (empty = consistent)."""
    errors = []
    unknown = sorted(set(policy) - POLICY_KEYS)
    if unknown:
        errors.append(f"unknown policy keys: {', '.join(unknown)}")
    w = policy.get("weights", {})
    total = sum(w.values())
    if total <= 0:
        errors.append("weights: sum must be > 0")
    elif total != WEIGHT_SUM:
        errors.append(f"weights: must sum to {WEIGHT_SUM} (D-09), got {total}")
    for k, v in w.items():
        if not (0 <= v <= 100):
            errors.append(f"weights: {k} out of range [0,100]")
    bands = policy.get("bands", {})
    h, wm, tm = bands.get("hold_max"), bands.get("watch_max"), bands.get("trim_max")
    if not (h is not None and wm is not None and tm is not None and h < wm < tm <= 100):
        errors.append("bands: must be contiguous non-overlapping (hold < watch < trim ≤ 100)")
    tb = policy.get("target_bands", {})
    for name, b in tb.items():
        if not (b[0] >= 0 and b[1] > b[0]):
            errors.append(f"target_bands: {name} invalid {b}")
    if policy.get("min_position_alloc_pct", 0) >= policy.get("max_single_stock_pct", 10):
        errors.append("min_position_alloc_pct must be < max_single_stock_pct")
    if policy.get("ltcg_defer_window_days", 30) < 0:
        errors.append("ltcg_defer_window_days must be >= 0")
    return errors
