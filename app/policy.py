"""Policy loading + validation. Policy is data, not code (ADR-7 / Freeze §14).

policy.yaml is the OPERATIONAL serialization of the signed D-01…D-15 policy in
Methodology Freeze §14 — it must not introduce or silently alter policy values.
"""
from pathlib import Path

import yaml

from .config import POLICY_PATH


def load_policy(path: Path = None) -> dict:
    with open(path or POLICY_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_ltcg_period_days(policy: dict) -> int:
    return int(policy.get("ltcg_period_days", 365))


def get_recon_tolerance(policy: dict) -> float:
    return float(policy.get("recon_tolerance_inr", 0.01))


def validate_policy(policy: dict) -> list:
    """Freeze §10 — return a list of violation strings (empty = consistent)."""
    errors = []
    w = policy.get("weights", {})
    total = sum(w.values())
    if total <= 0:
        errors.append("weights: sum must be > 0")
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
