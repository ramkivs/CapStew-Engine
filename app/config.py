"""Engine-level constants and the name→ticker symbol map (Phase 1)."""
from pathlib import Path

# Release lineage: v1.0.0 (methodology freeze, Phases 1-3) and v1.1.0 (CR-001..
# CR-012B) are tagged in Git. This build adds the reliability corrections
# (security, determinism, hysteresis persistence, config consistency), so it is
# the next release in that series. It participates in content_hash (Freeze §8:
# same inputs + same policy + same engine version => identical hash).
ENGINE_VERSION = "1.2.0"
PHASE = ("Phase 3 engine + v1.2 reliability corrections (security, determinism, "
         "hysteresis persistence, config consistency)")

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "policy.yaml"      # shipped, signed D-01…D-15 defaults
DATA_DIR = ROOT / "data"                            # the ONLY directory the app writes to
USER_POLICY_PATH = DATA_DIR / "policy.yaml"         # user's committed policy overrides
STORE_PATH = DATA_DIR / "engine.db"                 # append-only run store (ADR-4)
BACKUP_DIR = DATA_DIR / "backups"                   # local backup destination

NORMALIZATION_VERSION = "1.0"   # date/symbol normalization lineage
CALCULATION_VERSION = "2.1"     # scoring/decision calculation lineage (+ tax calc v1)

# Full company names appear in the portfolio & ledger exports; the screener is
# keyed by ticker. Names not present here get SYMBOL_UNMATCHED (partial-data path).
SYMBOL_MAP = {
    "Salasar Techno Engg": "SALASAR",
    "Ashoka Buildcon": "ASHOKA",
    "Larsen & Toubro": "LT",
    "AGI Greenpac": "AGIGREENPAC",
    "Bajaj Finance": "BAJFINANCE",
    "HDFC Bank": "HDFCBANK",
    "Bank of Baroda": "BANKBARODA",
    "DAM Capital Advisors": "DAMCAP",
    "Bharat Coking Coal": "BCC",
}

# Files older than this many days (vs as_of) raise a STALENESS warning.
STALENESS_DAYS_VALUATION = 3
STALENESS_DAYS_LEDGER = 7
