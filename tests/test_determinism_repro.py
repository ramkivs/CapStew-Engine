"""Determinism and staleness regression tests (Freeze §8, audit R-03 / R-05).

The audit proved that byte-identical inputs produced three different
`content_hash` values purely because `data_as_of` was read from filesystem
mtime. These tests pin the fix:

  * the hash depends only on file CONTENT plus declared inputs;
  * mtime changes (clone, copy, download, `touch`) cannot move it;
  * a fresh copy of the same bytes in a different directory hashes identically;
  * staleness now fires from declared data dates instead of never firing.
"""
import os
import shutil
from datetime import date

import pytest

from app.pipeline import DataAsOfError, resolve_data_as_of, run_engine, run_foundation

FIXDIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures"
AS_OF = date(2026, 8, 22)


def _copy_fixtures(dest):
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("portfolio.csv", "screener.csv", "ledger.csv"):
        shutil.copyfile(FIXDIR / name, dest / name)
    return dest


def _hash(d):
    return run_engine(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                      as_of=AS_OF)["content_hash"]


# ---- 1. mtime invariance ----------------------------------------------------

def test_content_hash_is_invariant_under_mtime_changes(tmp_path):
    """The exact defect from the audit: touch must not change the hash."""
    d = _copy_fixtures(tmp_path / "fx")
    baseline = _hash(d)

    for stamp in ("2026-01-15 10:00:00", "2026-10-30 10:00:00", "2020-02-29 23:59:59"):
        for name in ("portfolio.csv", "screener.csv", "ledger.csv"):
            os.utime(d / name, (__import__("time").mktime(
                __import__("time").strptime(stamp, "%Y-%m-%d %H:%M:%S")),) * 2)
        assert _hash(d) == baseline, f"hash moved after touching fixtures to {stamp}"


def test_content_hash_identical_across_independent_copies(tmp_path):
    """Two separate copies of the same bytes (a fresh checkout) hash identically."""
    a = _copy_fixtures(tmp_path / "a")
    b = _copy_fixtures(tmp_path / "b")
    # give the copies deliberately different mtimes
    os.utime(b / "ledger.csv", (0, 0))
    assert _hash(a) == _hash(b)


def test_repeated_execution_is_stable(tmp_path):
    d = _copy_fixtures(tmp_path / "fx")
    hashes = {_hash(d) for _ in range(5)}
    assert len(hashes) == 1


def test_content_changes_do_change_the_hash(tmp_path):
    """Sanity: the hash must still be sensitive to real data changes."""
    d = _copy_fixtures(tmp_path / "fx")
    baseline = _hash(d)
    text = (d / "screener.csv").read_text()
    (d / "screener.csv").write_text(text.replace("SALASAR", "SALASARX", 1))
    assert _hash(d) != baseline


# ---- 2. data_as_of resolution ----------------------------------------------

def test_data_as_of_defaults_to_run_as_of():
    resolved = resolve_data_as_of(AS_OF)
    assert resolved == {"portfolio": "2026-08-22", "screener": "2026-08-22",
                        "ledger": "2026-08-22"}


def test_data_as_of_accepts_a_single_date_for_all_sources():
    resolved = resolve_data_as_of(AS_OF, "2026-08-01")
    assert set(resolved.values()) == {"2026-08-01"}


def test_data_as_of_accepts_per_source_dates():
    resolved = resolve_data_as_of(AS_OF, {"ledger": "2026-07-01"})
    assert resolved["ledger"] == "2026-07-01"
    assert resolved["portfolio"] == "2026-08-22"


def test_data_as_of_rejects_malformed_date():
    with pytest.raises(DataAsOfError) as exc:
        resolve_data_as_of(AS_OF, {"ledger": "15/01/2026"})
    assert "ISO date" in str(exc.value)


def test_data_as_of_rejects_wrong_type():
    with pytest.raises(DataAsOfError):
        resolve_data_as_of(AS_OF, 20260801)


def test_data_as_of_ignores_unknown_source_keys():
    resolved = resolve_data_as_of(AS_OF, {"nonsense": "2026-01-01"})
    assert set(resolved) == {"portfolio", "screener", "ledger"}


# ---- 3. staleness actually works now ---------------------------------------

def test_staleness_fires_when_declared_data_is_old(tmp_path):
    """Audit R-05: staleness could never fire because mtime reset on checkout."""
    d = _copy_fixtures(tmp_path / "fx")
    payload = run_foundation(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                             as_of=AS_OF, data_as_of="2026-07-01")
    codes = [w["code"] for w in payload["warnings"]]
    assert "STALENESS" in codes
    assert set(payload["data_as_of"]["stale_files"]) == {"portfolio", "screener", "ledger"}


def test_no_staleness_when_data_is_current(tmp_path):
    d = _copy_fixtures(tmp_path / "fx")
    payload = run_foundation(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                             as_of=AS_OF)
    assert "STALENESS" not in [w["code"] for w in payload["warnings"]]
    assert payload["data_as_of"]["stale_files"] == []


def test_staleness_respects_per_source_thresholds(tmp_path):
    """Ledger allows 7 days, valuation files 3 (config.STALENESS_DAYS_*)."""
    d = _copy_fixtures(tmp_path / "fx")
    payload = run_foundation(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                             as_of=AS_OF, data_as_of="2026-08-17")   # 5 days behind
    stale = set(payload["data_as_of"]["stale_files"])
    assert {"portfolio", "screener"} <= stale      # > 3 day valuation threshold
    assert "ledger" not in stale                   # within the 7 day ledger threshold


def test_staleness_feeds_the_confidence_penalty(tmp_path):
    """The p_staleness penalty must actually move when data is declared stale."""
    d = _copy_fixtures(tmp_path / "fx")
    fresh = run_engine(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                       as_of=AS_OF)
    old = run_engine(d / "portfolio.csv", d / "screener.csv", d / "ledger.csv",
                     as_of=AS_OF, data_as_of="2026-06-01")

    def _stale_penalty(payload):
        h = next(x for x in payload["holdings"] if x["confidence_breakdown"])
        return h["confidence_breakdown"]["staleness"]

    assert _stale_penalty(fresh) == 0
    assert _stale_penalty(old) > 0
