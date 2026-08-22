import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXDIR = ROOT / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _generate():
    from fixtures.generate_fixtures import main
    main(FIXDIR)


@pytest.fixture(scope="session")
def foundation(_generate):
    from app.pipeline import run_foundation
    return run_foundation(
        FIXDIR / "portfolio.csv",
        FIXDIR / "screener.csv",
        FIXDIR / "ledger.csv",
        as_of=date(2026, 8, 22),
    )


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    """Isolate the run store per test so persistence tests never share state."""
    import app.config as cfg
    monkeypatch.setattr(cfg, "STORE_PATH", tmp_path / "engine.db")
    yield
