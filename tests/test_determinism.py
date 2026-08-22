"""Capital Steward Determinism Guarantee (Freeze §8) — replay tests."""
from datetime import date
from pathlib import Path

FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_same_inputs_same_policy_same_hash(foundation):
    from app.pipeline import run_foundation
    replay = run_foundation(
        FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22), run_id="run_replay",
    )
    assert replay["content_hash"] == foundation["content_hash"]


def test_content_hash_excludes_run_id_and_self(foundation):
    from app.determinism import content_hash
    content = {k: v for k, v in foundation.items() if k not in ("run_id", "content_hash")}
    assert content_hash(content) == foundation["content_hash"]


def test_payload_is_stable_across_run_ids(foundation):
    from app.pipeline import run_foundation
    a = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                       as_of=date(2026, 8, 22), run_id="AAA")
    b = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv", FIXDIR / "ledger.csv",
                       as_of=date(2026, 8, 22), run_id="BBB")
    strip = lambda p: {k: v for k, v in p.items() if k not in ("run_id", "content_hash")}
    assert strip(a) == strip(b)
