"""Engine-level constants and the name→ticker symbol map (Phase 1)."""
from pathlib import Path

# CR-023 / VP-1: payload-visible provenance again (per-position theme +
# theme_source, themes_sha256 in provenance.archive, theme concentration
# grouping switch) => ENGINE_VERSION bump. Calculation/normalization lineage
# unchanged on purpose: the manual tag changes ONLY the concentration grouping
# surface, never scoring/decision math (H2-D2-A).
ENGINE_VERSION = "0.5.0-phase3"
PHASE = ("Phase 3 — tax-year subsystem + run history/diff + provenance "
         "(UI contract fields) + CR-022 snapshot archive + CR-023 manual "
         "theme-tag layer (EMM-H2)")

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "policy.yaml"
THEMES_PATH = ROOT / "themes" / "themes.yaml"   # CR-023 authority mapping (NOT policy)
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
