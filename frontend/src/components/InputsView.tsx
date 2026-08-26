import { useRef, useState } from 'react';
import { Banner } from './ui';
import { log } from '../activityLog';

const STEPS = [
  'Parse 3 files & normalise dates (DD-MM vs ISO)',
  'Reconcile cost basis: Σ(lot qty × buy) == Invested',
  'Build per-lot FIFO tax engine (days-to-LTCG, lot P&L)',
  'Run Stage 1 hard gates (governance · allocation · tax-defer)',
  'Score Stage 2 composite per bucket profile',
  'Rank candidates · theme rebalance · tax-year budget',
  'Write decisions (append-only log)',
];

export function InputsView({ running, onRunSample, onRunFiles }: {
  running: boolean;
  onRunSample: () => void;
  onRunFiles: (portfolio: File, screener: File, ledger: File, sold: File | null) => void;
}) {
  const [portfolio, setPortfolio] = useState<File | null>(null);
  const [screener, setScreener] = useState<File | null>(null);
  const [ledger, setLedger] = useState<File | null>(null);
  const [sold, setSold] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [step, setStep] = useState(-1);

  const stepTimer = useRef<number | null>(null);

  const pick = (slot: string, set: (f: File) => void) => (f: File) => {
    set(f);
    log('info', `file selected — ${slot}: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`);
  };

  function runFiles() {
    if (!portfolio || !screener || !ledger) {
      setErr('All three files are required (portfolio, screener, ledger).');
      return;
    }
    setErr(null);
    onRunFiles(portfolio, screener, ledger, sold);
  }

  function runSample() {
    setErr(null);
    setStep(0);
    const t = setInterval(() => {
      setStep((s) => {
        if (s >= STEPS.length) { clearInterval(t); return s; }
        return s + 1;
      });
    }, 180);
    stepTimer.current = t as unknown as number;
    setTimeout(() => {
      clearInterval(t);
      setStep(-1);
      onRunSample();
    }, STEPS.length * 180 + 400);
  }

  return (
    <div>
      <div className="grid cols-3" style={{ marginBottom: 14 }}>
        <FileDrop label="1 · Portfolio holdings" sub="Instrument, Qty, Avg Buy, Invested, Value, Alloc %, XIRR, Days, Dates"
          file={portfolio} onFile={pick('1 · portfolio holdings', setPortfolio)} />
        <FileDrop label="2 · Fundamentals / valuation screener" sub="PE/PB + premiums, PEG, ROE/ROCE, growth, D/E, pledge, DII/FII, 200D SMA"
          file={screener} onFile={pick('2 · valuation screener', setScreener)} />
        <FileDrop label="3 · Raw trade ledger (per fill)" sub="Instrument, Qty, Buy Price, LTP, P&L, Invested, Trade Date"
          file={ledger} onFile={pick('3 · trade ledger', setLedger)} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>Run controls</h3>
          <div className="note" style={{ marginBottom: 14 }}>
            Files are parsed server-side → cost-basis reconciliation → per-lot tax engine →
            Stage 1 gates → Stage 2 composite. Outputs are <b>advisory</b>. The browser never
            computes a decision (ADR-1a).
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn primary" disabled={running} onClick={runSample}>
              ▶ Run demo (bundled fixtures)
            </button>
            <button className="btn" disabled={running} onClick={runFiles}>
              ▶ Run my files
            </button>
          </div>
          <div className="note" style={{ marginTop: 12 }}>
            Reconciliation: <span className="kbd">Σ(lot qty × buy) == Invested</span> ·{' '}
            <span className="kbd">Σ(lot qty) == Qty Held</span> — mismatch = hard data error (G0).
          </div>
        </div>

        <div className="card">
          <h3>Sold transactions (optional) <span className="tag">closes the realised-gains gap</span></h3>
          <FileDrop label="Sold ledger" sub="Instrument, Qty, Sell Price, Sell Date — enables the real tax-year summary"
            file={sold} onFile={pick('sold ledger (optional)', setSold)} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Reconciliation / validation trust gate <span className="tag">G0 semantics unchanged</span></h3>
        <div className="grid cols-3">
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Pass</b><br />
            A decisions payload is shown only after the backend accepts required files and completes reconciliation checks.
          </div>
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Warning</b><br />
            Non-blocking backend warnings are surfaced in the Decisions trust banner with their payload codes and messages.
          </div>
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Blocking failure</b><br />
            Hard G0 mismatches remain backend errors; the UI displays the returned error instead of inventing a decision.
          </div>
        </div>
        <div className="note" style={{ marginTop: 10 }}>
          This screen explains the validation path only. It does not perform reconciliation, scoring, gating, trim, sizing, or tax calculations in the browser.
        </div>
      </div>

      {err ? <div style={{ marginTop: 14 }}><Banner kind="err">⚠ {err}</Banner></div> : null}

      {step >= 0 ? (
        <div className="overlay open">
          <div className="prog">
            <h3 style={{ marginBottom: 8 }}>Running engine…</h3>
            <div className="note" style={{ marginBottom: 10 }}>
              Authoritative pipeline — server-side only
            </div>
            {STEPS.map((s, i) => (
              <div key={s} className={`step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
                <span className="spinner" style={{ opacity: i === step ? 1 : 0 }} />
                {s}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FileDrop({ label, sub, file, onFile }: {
  label: string; sub: string; file: File | null; onFile: (f: File) => void;
}) {
  return (
    <label className={`drop-zone ${file ? 'file' : ''}`}
      style={{
        border: '1.5px dashed var(--line2)', borderRadius: 12, padding: 22, textAlign: 'center',
        color: file ? 'var(--green)' : 'var(--muted)', cursor: 'pointer', display: 'block',
        borderColor: file ? '#1f5b49' : undefined,
      }}>
      <input type="file" accept=".csv" style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
      <div style={{ fontSize: 22 }}>{file ? '✅' : '📄'}</div>
      <b>{file ? file.name : label}</b>
      <div className="note" style={{ marginTop: 6 }}>{sub}</div>
    </label>
  );
}
