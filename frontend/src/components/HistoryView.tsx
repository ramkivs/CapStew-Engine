import { useState } from 'react';
import type { RunDiff, RunListItem } from '../types';
import { Badge, Banner } from './ui';

export function HistoryView({ runs, onDiff, diff, onRefresh }: {
  runs: RunListItem[];
  onDiff: (runId: string) => Promise<void>;
  diff: RunDiff | null;
  onRefresh: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  async function pick(runId: string) {
    setSelected(runId);
    await onDiff(runId);
  }

  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Run history <span className="tag">append-only</span></h3>
        <button className="btn" style={{ marginBottom: 10 }} onClick={onRefresh}>↻ refresh</button>
        <table>
          <thead>
            <tr><th>Run</th><th>As-of</th><th>Policy</th><th>Content hash</th></tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id} className="row" onClick={() => pick(r.run_id)}
                style={{ background: selected === r.run_id ? '#141c2e' : undefined }}>
                <td className="tick">{r.run_id.slice(0, 24)}…</td>
                <td>{r.as_of}</td>
                <td>v{r.policy_version}</td>
                <td style={{ fontSize: 11 }}>{r.content_hash.slice(0, 12)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Run diff <span className="tag">run N vs N-1</span></h3>
        {diff == null ? (
          <div className="note">Select a run to diff it against its predecessor.</div>
        ) : diff.previous_run_id == null ? (
          <Banner kind="ok">First run — no predecessor to diff against.</Banner>
        ) : (
          <>
            <div className="note" style={{ marginBottom: 10 }}>
              {diff.run_id.slice(0, 24)}… vs {diff.previous_run_id.slice(0, 24)}…
            </div>
            {diff.changed.length === 0 && diff.removed_holdings.length === 0
              ? <Banner kind="ok">No decision changes between runs.</Banner>
              : null}
            {diff.changed.map((c) => {
              const toDecision = typeof c.decision === 'string' ? c.decision : c.decision?.to ?? 'HOLD';
              return (
                <div key={c.instrument} className="cfg">
                  <div className="lbl">
                    <b style={{ fontFamily: 'var(--mono)', color: 'var(--blue)' }}>{c.instrument}</b>
                    <small>{c.status === 'added' ? 'added' : `${(c.decision as { from: string; to: string })?.from} → ${(c.decision as { from: string; to: string })?.to}`}</small>
                  </div>
                  <div><Badge decision={toDecision} /></div>
                  <div className="val" style={{ fontSize: 11 }}>
                    {c.score ? `${num(c.score.from)} → ${num(c.score.to)}` : ''}
                  </div>
                </div>
              );
            })}
            {diff.removed_holdings.length > 0 ? (
              <div className="note" style={{ marginTop: 8 }}>
                removed: {diff.removed_holdings.join(', ')}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function num(n: number | null | undefined): string {
  return n == null ? '—' : String(n);
}
