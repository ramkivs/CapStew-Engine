"""Engine-level constants and the name→ticker symbol map (Phase 1)."""
from pathlib import Path

# CR-022 / VP-1: payload-visible provenance changed (provenance.archive + dual
# source-date labels) => ENGINE_VERSION bump. CALCULATION_VERSION and
# NORMALIZATION_VERSION are unchanged: no scoring/decision math and no
# date/symbol normalization semantics changed.
ENGINE_VERSION = "0.4.0-phase3"
PHASE = ("Phase 3 — tax-year subsystem + run history/diff + provenance "
         "(UI contract fields) + CR-022 snapshot archive/provenance")

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "policy.yaml"
STORE_PATH = ROOT / "data" / "engine.db"   # append-only run store (ADR-4)

NORMALIZATION_VERSION = "1.0"   # date/symbol normalization lineage
CALCULATION_VERSION = "2.1"     # scoring/decision calculation lineage (+ tax calc v1)

# CR-022 snapshot archive (EMM-F2): content-addressed raw/normalized input
# blobs + append-only hash-chained manifest under the gitignored data/ boundary.
# Indefinite local retention (F2-D7); no compression/rotation in CR-022.
ARCHIVE_VERSION = 1             # archive schema/record lineage (F2-D10.9)
ARCHIVE_ROOT = ROOT / "data" / "archive"

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
