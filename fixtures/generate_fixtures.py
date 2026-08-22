"""Generate internally-consistent fixture CSVs for Phase 1.

The three exports must reconcile exactly (G0), so portfolio numbers are
computed from the ledger here rather than hand-written. The golden trilogy
(SALASAR / ASHOKA / LT) is embedded as data facts:

  GOLDEN-G2-TRIM-S-SALASAR : screener pledge 4.0% (below G1 threshold)
  GOLDEN-G1-EXIT-ASHOKA    : screener pledge 12.4% (above G1 threshold); 16 declining, all-red lots
  GOLDEN-G3-HOLD-LT        : oldest lot 2025-09-13 → 22 days to LTCG as of 2026-08-22

AGI Greenpac is deliberately OMITTED from the screener to exercise the
SYMBOL_UNMATCHED / PARTIAL_DATA path.
"""
import csv
from datetime import date
from decimal import Decimal

AS_OF = date(2026, 8, 22)

# ledger: instrument -> list of (date_dd_mm_yyyy, qty, buy_price, ltp)
# Quantities are scaled so position values are realistic (> ₹5,000 dust floor).
LEDGER = {
    "Salasar Techno Engg": [
        ("23-04-2026", 160, "42.00", "76.50"),
        ("02-05-2026", 160, "48.50", "76.50"),
        ("11-06-2026", 160, "61.20", "76.50"),
    ],
    "Ashoka Buildcon": [
        ("22-05-2026", 100, "131.00", "113.90"),
        ("25-05-2026", 100, "130.20", "113.90"),
        ("28-05-2026", 100, "129.50", "113.90"),
        ("31-05-2026", 100, "128.80", "113.90"),
        ("03-06-2026", 100, "128.00", "113.90"),
        ("06-06-2026", 100, "127.20", "113.90"),
        ("09-06-2026", 100, "126.40", "113.90"),
        ("12-06-2026", 100, "125.60", "113.90"),
        ("15-06-2026", 100, "124.80", "113.90"),
        ("18-06-2026", 100, "124.00", "113.90"),
        ("21-06-2026", 100, "123.20", "113.90"),
        ("24-06-2026", 100, "122.40", "113.90"),
        ("27-06-2026", 100, "121.60", "113.90"),
        ("30-06-2026", 100, "120.80", "113.90"),
        ("03-07-2026", 100, "120.00", "113.90"),
        ("06-07-2026", 100, "119.20", "113.90"),
    ],
    "Larsen & Toubro": [
        ("13-09-2025", 120, "287.00", "340.00"),
        ("03-11-2025", 80, "301.00", "340.00"),
    ],
    "AGI Greenpac": [
        ("27-05-2026", 10, "588.30", "706.00"),
        ("27-05-2026", 10, "591.00", "706.00"),
    ],
    "Bajaj Finance": [
        ("19-05-2026", 120, "895.00", "1087.00"),
    ],
    "HDFC Bank": [
        ("19-05-2026", 200, "772.00", "727.00"),
    ],
    "Bank of Baroda": [
        ("09-02-2026", 100, "290.00", "251.00"),
        ("30-03-2026", 200, "250.00", "251.00"),
    ],
    "DAM Capital Advisors": [
        ("12-08-2026", 50, "145.98", "146.15"),
    ],
    "Bharat Coking Coal": [
        ("21-06-2026", 80, "215.00", "231.00"),
        ("05-07-2026", 120, "228.00", "231.00"),
    ],
}

# screener rows: (name, ticker, sub-sector, mcap_cr, close, pe, pb, peg, roe, roce,
#                 eps_hist, eps_fwd, d2e, icr, pfcf, pledge_pct, sma200, pe_prem, pb_prem, dii3m, fii3m)
SCREENER = [
    ("Salasar Techno Engg", "SALASAR", "Engineering - Infrastructure", "480", "76.50",
     "55.0", "4.8", "2.9", "12.1", "9.8", "9.0", "11.0", "1.4", "3.2", "48.0",
     "4.0", "52.40", "1.85", "1.62", "-1.2", "-2.4"),
    ("Ashoka Buildcon", "ASHOKA", "Engineering - Infrastructure", "3100", "113.90",
     "-8.5", "0.9", "0.0", "-3.4", "2.1", "-15.0", "-8.0", "2.1", "1.1", "-12.0",
     "12.4", "128.60", "0.42", "0.38", "0.3", "-1.1"),
    ("Larsen & Toubro", "LT", "Engineering - Infrastructure", "480000", "340.00",
     "26.0", "4.9", "1.9", "14.2", "13.8", "15.0", "16.0", "0.8", "5.4", "22.0",
     "0.0", "318.00", "1.10", "1.05", "0.9", "1.4"),
    ("Bajaj Finance", "BAJFINANCE", "NBFC", "450000", "1087.00",
     "24.0", "3.6", "1.2", "22.5", "4.8", "20.0", "21.0", "3.6", "1.9", "15.0",
     "0.0", "1052.00", "0.85", "0.90", "0.7", "0.6"),
    ("HDFC Bank", "HDFCBANK", "Banks - Private", "700000", "727.00",
     "19.5", "2.6", "1.1", "15.8", "1.9", "16.0", "15.0", "6.8", "1.4", "11.0",
     "0.0", "742.00", "0.92", "0.88", "1.2", "0.5"),
    ("Bank of Baroda", "BANKBARODA", "Banks - PSU", "130000", "251.00",
     "9.5", "1.1", "0.7", "13.1", "1.2", "18.0", "12.0", "10.2", "1.6", "4.0",
     "0.0", "243.00", "0.70", "0.66", "0.4", "-0.3"),
    ("DAM Capital Advisors", "DAMCAP", "Capital Markets", "3500", "146.15",
     "22.0", "4.2", "1.5", "18.9", "21.0", "28.0", "25.0", "0.1", "6.5", "18.0",
     "0.0", "139.00", "1.15", "1.20", "0.8", "1.0"),
    ("Bharat Coking Coal", "BCC", "Mining", "14000", "231.00",
     "8.2", "1.4", "0.5", "17.5", "19.0", "12.0", "9.0", "0.0", "8.9", "6.0",
     "0.0", "226.00", "0.60", "0.62", "0.5", "0.2"),
]


def iso(dd_mm_yyyy: str) -> date:
    d, m, y = (int(x) for x in dd_mm_yyyy.split("-"))
    return date(y, m, d)


def write_ledger(path):
    header = ["Instrument", "Qty.", "Buy Price", "LTP", "P&L", "Invested", "Curr value", "Trade Date"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for name, lots in LEDGER.items():
            for (d, q, b, ltp) in lots:
                q, b, ltp = Decimal(q), Decimal(b), Decimal(ltp)
                pnl = (ltp - b) * q
                w.writerow([
                    name, f"{int(q)}", f"{b:.2f}", f"{ltp:.2f}",
                    f"{pnl:.2f}", f"{b * q:.2f}", f"{ltp * q:.2f}", d,
                ])


def write_portfolio(path):
    header = ["Instrument", "Transactions", "Qty Held", "Avg Buy Price", "Invested",
              "Current Value", "Allocation %", "Gain/Loss %", "Net Cashflow", "XIRR",
              "Holding Period (Days)", "First Date", "Last Date"]
    total_value = Decimal("0")
    rows = []
    for name, lots in LEDGER.items():
        qty = sum(Decimal(q) for (_, q, _, _) in lots)
        invested = sum(Decimal(q) * Decimal(b) for (_, q, b, _) in lots)
        value = sum(Decimal(q) * Decimal(ltp) for (_, q, _, ltp) in lots)
        total_value += value
        rows.append([name, len(lots), qty, invested, value, invested, value])

    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for (name, n_lots, qty, invested, value, _, _) in rows:
            avg = invested / qty
            gain_pct = (value - invested) / invested * 100
            alloc = value / total_value * 100
            first = iso(min(d for (d, _, _, _) in LEDGER[name]))
            last = iso(max(d for (d, _, _, _) in LEDGER[name]))
            holding_days = (AS_OF - first).days
            w.writerow([
                name, n_lots, f"{int(qty)}", f"{avg:.4f}", f"{invested:.2f}",
                f"{value:.2f}", f"{alloc:.4f}", f"{gain_pct:.4f}",
                f"{value - invested:.2f}", "", f"{holding_days}",
                first.isoformat(), last.isoformat(),
            ])


def write_screener(path):
    header = ["Name", "Ticker", "Sub-Sector", "Market Cap", "Close Price", "PE Ratio",
              "PB Ratio", "PEGRATIO", "ROE", "ROCE", "1Y Historical EPS Growth",
              "1Y Forward EPS Growth", "Debt to Equity", "Interest Coverage Ratio",
              "Price/FCF", "Pledged Promoter Holdings", "200D SMA",
              "PE Premium vs Sub-sector", "PB Premium vs Sub-sector",
              "DII Holding Change 3M", "FII Holding Change 3M"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in SCREENER:
            w.writerow(row)


def main(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    write_ledger(outdir / "ledger.csv")
    write_portfolio(outdir / "portfolio.csv")
    write_screener(outdir / "screener.csv")
    print(f"fixtures written to {outdir}")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    main(out)
