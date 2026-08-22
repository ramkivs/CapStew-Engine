"""Hysteresis (Freeze §6) — asymmetric transitions + N=2 persistence."""
from datetime import date

from app.hysteresis import Hysteresis

A1, A2 = date(2026, 8, 20), date(2026, 8, 21)


def test_transition_enter_and_revert_asymmetry():
    t = Hysteresis.transition
    assert t("WATCH", 56) == "TRIM"     # enter TRIM at 56
    assert t("TRIM", 52) == "TRIM"      # still TRIM at 52 (revert is <52)
    assert t("TRIM", 51) == "WATCH"     # revert below 52
    assert t("HOLD", 31) == "WATCH"     # enter WATCH at 31
    assert t("WATCH", 28) == "WATCH"    # still WATCH at 28 (revert is <28)
    assert t("WATCH", 27) == "HOLD"
    assert t("TRIM", 76) == "HARVEST"
    assert t("HARVEST", 72) == "HARVEST"  # revert is <72
    assert t("HARVEST", 71) == "TRIM"


def test_n2_persistence_requires_two_distinct_runs():
    h = Hysteresis()
    assert h.apply("X", "HOLD", 40.0, A1) == "HOLD"      # first run: adopt HOLD
    # from HOLD, score 45 → target WATCH (steps through adjacent bands)
    assert h.apply("X", "WATCH", 45.0, A2) == "HOLD"     # pending count 1
    assert h.apply("X", "WATCH", 45.0, date(2026, 8, 22)) == "WATCH"  # commit on 2nd distinct run
    assert h.apply("X", "WATCH", 45.0, date(2026, 8, 23)) == "WATCH"


def test_same_asof_does_not_double_count():
    h = Hysteresis()
    h.apply("X", "HOLD", 40.0, A1)
    assert h.apply("X", "WATCH", 45.0, A1) == "HOLD"     # same as_of → pending count 1
    assert h.apply("X", "WATCH", 45.0, A1) == "HOLD"     # still 1 (reset, no increment)
    assert h.apply("X", "WATCH", 45.0, A2) == "WATCH"    # distinct as_of → count 2 → commit


def test_bypass_overrides_immediately():
    h = Hysteresis()
    h.apply("X", "HOLD", 40.0, A1)
    assert h.bypass("X", "EXIT", 0.0, A2) == "EXIT"
    assert h.get_prev("X")["decision"] == "EXIT"
