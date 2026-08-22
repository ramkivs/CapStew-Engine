"""Engine-level constants and the name→ticker symbol map (Phase 1)."""
from pathlib import Path

ENGINE_VERSION = "0.3.1-phase3"
PHASE = "Phase 3 — tax-year subsystem + run history/diff + provenance (UI contract fields)"

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "policy.yaml"
STORE_PATH = ROOT / "data" / "engine.db"   # append-only run store (ADR-4)

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
