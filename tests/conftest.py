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
    """Isolate the run store AND the user policy file per test.

    Without the policy redirect, any test hitting PUT /api/v1/policy would write
    into the repository's data/ directory.
    """
    import app.config as cfg
    monkeypatch.setattr(cfg, "STORE_PATH", tmp_path / "engine.db")
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "policy.yaml")
    monkeypatch.setattr(cfg, "BACKUP_DIR", tmp_path / "backups")
    yield
