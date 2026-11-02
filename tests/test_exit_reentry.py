"""CR-024 — gate-only EXIT / hysteresis re-entry semantics."""

from datetime import date

from app.hysteresis import Hysteresis


def test_prior_exit_is_not_retained_by_hysteresis():
    h = Hysteresis()
    as_of = date(2026, 9, 2)

    h.seed("ASHOKA", "EXIT", 31.2, as_of.isoformat())

    result = h.apply("ASHOKA", "WATCH", 31.2, as_of)

    assert result == "WATCH"
    assert h.state["ASHOKA"]["decision"] == "WATCH"
    assert h.state["ASHOKA"]["pending"] is None


def test_prior_exit_reevaluates_g4_and_adopts_current_band():
    h = Hysteresis()
    previous_as_of = date(2026, 9, 1)
    current_as_of = date(2026, 9, 2)

    h.seed("ASHOKA", "EXIT", 69.0, previous_as_of.isoformat())
    previous = h.get_prev("ASHOKA")

    result = h.apply("ASHOKA", "WATCH", 31.2, current_as_of)

    assert result == "WATCH"
    assert h.state["ASHOKA"]["decision"] == "WATCH"
    assert h.state["ASHOKA"]["pending"] is None
    assert previous["decision"] == "EXIT"


def test_normal_n2_hysteresis_resumes_after_exit_adoption():
    h = Hysteresis()
    day1 = date(2026, 9, 1)
    day2 = date(2026, 9, 2)
    day3 = date(2026, 9, 3)

    h.seed("ASHOKA", "EXIT", 69.0, day1.isoformat())

    assert h.apply("ASHOKA", "WATCH", 31.2, day2) == "WATCH"

    # WATCH -> TRIM requires two distinct as_of dates.
    assert h.apply("ASHOKA", "TRIM", 56.0, day3) == "WATCH"
    assert h.state["ASHOKA"]["pending"] == {"band": "TRIM", "count": 1}


def test_gate_fired_exit_still_bypasses_immediately():
    h = Hysteresis()
    as_of = date(2026, 9, 2)

    h.seed("ASHOKA", "WATCH", 31.2, (date(2026, 9, 1)).isoformat())

    result = h.bypass("ASHOKA", "EXIT", 31.2, as_of)

    assert result == "EXIT"
    assert h.state["ASHOKA"]["decision"] == "EXIT"
    assert h.state["ASHOKA"]["pending"] is None
