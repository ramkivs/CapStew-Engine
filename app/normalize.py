"""Date disambiguation and symbol normalization.

The three exports mix YYYY-MM-DD (portfolio) and DD-MM-YYYY (ledger) — the
spec's appendix shows both. Format is detected by shape (4-digit year position),
which is unambiguous between the two. A 2-2-4 string is always read day-first
(the documented ledger convention); such dates are recorded for a
DATE_FORMAT_INFERRED notice rather than rejected.
"""
import re
from datetime import date, datetime

from .symbols import map_name_to_ticker

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DDMM_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


class DateAmbiguousError(ValueError):
    """Raised for date strings whose format cannot be determined."""


def parse_date(raw, *, inferred_notes=None) -> date:
    """Parse a date in ISO (YYYY-MM-DD) or DD-MM-YYYY form.

    `inferred_notes` (optional list) receives a description of every 2-2-4
    date whose day AND month are both <= 12 — i.e. dates whose day/month
    order is only resolvable by convention.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty date")
    if ISO_RE.match(raw):
        return datetime.strptime(raw, "%Y-%m-%d").date()
    if DDMM_RE.match(raw):
        d, m, y = (int(x) for x in raw.split("-"))
        if d <= 12 and m <= 12 and inferred_notes is not None:
            inferred_notes.append(
                f"{raw!r}: both day and month are <= 12 — interpreted as DD-MM-YYYY")
        try:
            return date(y, m, d)
        except ValueError as exc:
            raise ValueError(f"invalid date {raw!r}") from exc
    raise DateAmbiguousError(f"unrecognized date format {raw!r}")

