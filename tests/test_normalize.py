from datetime import date

import pytest

from app.normalize import DateAmbiguousError, map_name_to_ticker, parse_date


def test_iso_format():
    assert parse_date("2026-05-26") == date(2026, 5, 26)


def test_dd_mm_yyyy_format():
    assert parse_date("27-05-2026") == date(2026, 5, 27)


def test_dd_mm_day_and_month_both_low():
    # documented convention: DD-MM-YYYY even when both <= 12
    assert parse_date("09-02-2026") == date(2026, 2, 9)


def test_inferred_note_recorded():
    notes = []
    parse_date("02-05-2026", inferred_notes=notes)
    assert any("interpreted as DD-MM-YYYY" in n for n in notes)


def test_unrecognized_format_raises():
    with pytest.raises(DateAmbiguousError):
        parse_date("05/26/2026")


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_date("")


def test_symbol_map_hit():
    assert map_name_to_ticker("Salasar Techno Engg") == ("SALASAR", True)


def test_symbol_map_miss():
    assert map_name_to_ticker("Arihant Capital Markets") == (None, False)
