"""Confidence model (Freeze §4) — exact equation + caps."""
from app.confidence import compute_penalties, confidence_from_penalties


def test_confidence_rounds_inside_clamp():
    # raw = 93.6 → round → 94 (NOT 93.6, NOT clamp-of-unrounded)
    assert confidence_from_penalties({"a": 6.4}) == 94


def test_confidence_clamps_floor():
    assert confidence_from_penalties({"a": 500}) == 20


def test_confidence_clamps_ceiling():
    assert confidence_from_penalties({"a": 0, "b": 0}) == 95


def test_confidence_is_integer():
    for s in (0, 0.1, 3.7, 12.5, 80, 100):
        assert isinstance(confidence_from_penalties({"x": s}), int)


def test_penalties_missing_data_scales_with_coverage():
    subs = {"position_sizing": 50}
    p_full = compute_penalties(subs, coverage=1.0, composite_score=50, stale_count=0, proxy_count=0)
    p_half = compute_penalties(subs, coverage=0.5, composite_score=50, stale_count=0, proxy_count=0)
    assert p_half["missing_data"] == 12.5
    assert p_full["missing_data"] == 0.0


def test_boundary_penalty_near_edge():
    p = compute_penalties({"a": 50}, coverage=1.0, composite_score=57.0, stale_count=0, proxy_count=0)
    assert p["boundary"] == 4.0  # 57 is 1 pt from the 56 TRIM edge → 5-1


def test_no_boundary_penalty_away_from_edges():
    p = compute_penalties({"a": 50}, coverage=1.0, composite_score=40.0, stale_count=0, proxy_count=0)
    assert p["boundary"] == 0.0


def test_proxy_penalty_capped_at_10():
    p = compute_penalties({"a": 50}, coverage=1.0, composite_score=40.0, stale_count=0, proxy_count=4)
    assert p["proxy"] == 10.0
