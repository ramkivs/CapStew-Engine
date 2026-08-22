"""Print the decision content_hash for the bundled fixtures (cross-process determinism probe).

Usage: python scripts/hash_engine.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import run_engine  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"

if __name__ == "__main__":
    payload = run_engine(FIX / "portfolio.csv", FIX / "screener.csv", FIX / "ledger.csv",
                         as_of=date(2026, 8, 22))
    print(payload["content_hash"])
