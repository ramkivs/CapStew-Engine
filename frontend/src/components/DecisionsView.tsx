import type { DecisionPayload, Holding } from '../types';
import { Badge, Bar, Stat, TagChip, pct, num } from './ui';

const CAT_COLORS: Record<string, string> = {
  position_sizing: '#34d399',
  valuation_stretch: '#fb923c',
  quality_drift: '#a78bfa',
  tax_efficiency: '#60a5fa',
  opportunity_cost: '#fbbf24',
  technical_regime: '#94a3b8',
};

export function DecisionsView({ payload, preview, onSelect, onClearPreview }: {
  payload: DecisionPayload;
  preview: DecisionPayload | null;
  onSelect: (h: Holding) => void;
  onClearPreview: () => void;
}) {
  const p = preview ?? payload;
  const dist = p.portfolio_summary.decision_distribution;
  const tax = p.portfolio_summary.tax as Record<string, unknown>;

  return (
    <div>
      {preview ? (
        <div style={{ marginBottom: 14 }}>
          <div className="banner warn" style={{ justifyContent: 'space-between' }}>
            <span><b>PREVIEW — not authoritative.</b> Weight changes recomputed server-side via /what-if.</span>
            <button className="btn" style={{ padding: '4px 12px' }} onClick={onClearPreview}>✕ clear</button>
          </div>
        </div>
      ) : null}

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        <Stat k="Portfolio value" v={'₹' + p.portfolio_summary.total_value.toLocaleString('en-IN')}
          s={`${p.portfolio_summary.holdings_count} holdings · run ${p.run_id.slice(0, 16)}…`} />
        <Stat k="Decisions" v={
          <span>
            <span style={{ color: '#34d399' }}>{dist.HOLD ?? 0}</span>{' '}
            <span style={{ color: '#fbbf24' }}>{dist.WATCH ?? 0}</span>{' '}
            <span style={{ color: '#fb923c' }}>{dist.TRIM ?? 0}</span>{' '}
            <span style={{ color: '#a78bfa' }}>{dist.HARVEST ?? 0}</span>{' '}
            <span style={{ color: '#f87171' }}>{dist.EXIT ?? 0}</span>
          </span>}
          s="HOLD · WATCH · TRIM · HARVEST · EXIT" />
        <Stat k="LTCG headroom" v={`₹${num(tax.ltcg_headroom as number)}`}
          s={tax.provisional ? 'provisional — no sold ledger' : 'realised from sold ledger'} />
        <Stat k="Stage 1 gates fired" v={<span style={{ color: 'var(--red)' }}>{p.portfolio_summary.stage1_gates_fired}</span>}
          s="governance · allocation · tax defer" />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>Holdings — scored & ranked <span className="tag">click row → detail</span></h3>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Instrument</th><th>Bucket</th>
                  <th className="num">Alloc</th><th className="num">Gain/Loss</th>
                  <th>Decision</th><th className="num">Score</th><th className="num">Conf</th>
                </tr>
              </thead>
              <tbody>
                {p.holdings.map((h) => {
                  const m = meta(h.decision);
                  const prev = h.previous_run;
                  const changed = prev && prev.decision !== h.decision;
                  return (
                    <tr key={h.instrument} className="row" onClick={() => onSelect(h)}>
                      <td className="tick">{h.ticker ?? h.instrument}
                        {h.data_completeness.position_sizing === false ? ' · partial' : ''}
                        {h.behavioral.blocks_adds ? ' ' : ''}
                      </td>
                      <td className="muted" style={{ fontFamily: 'system-ui' }}>{h.bucket ?? '—'}</td>
                      <td className="num">{pct(h.alloc_pct)}</td>
                      <td className={`num ${(h.gain_pct ?? 0) >= 0 ? 'up' : 'down'}`}>
                        {(h.gain_pct ?? 0) >= 0 ? '+' : ''}{pct(h.gain_pct)}
                      </td>
                      <td>
                        <Badge decision={h.decision} />
                        {changed ? <span className="note" style={{ marginLeft: 6, fontSize: 10 }}>↑ prev {prev!.decision}</span> : null}
                      </td>
                      <td className="num" style={{ color: m }}>{num(h.composite_score)}</td>
                      <td className="num">{h.confidence == null ? '—' : `${h.confidence}%`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid" style={{ gap: 14 }}>
          <div className="card">
            <h3>Action queue <span className="tag">EXIT → TRIM → HARVEST</span></h3>
            {p.portfolio_layer.action_queue.length === 0
              ? <div className="note">No candidates.</div>
              : p.portfolio_layer.action_queue.map((q) => {
                  const rc = q.reason;
                  const cc = rc === 'RISK' ? 'var(--red)' : rc === 'SIZING' ? 'var(--orange)' : 'var(--violet)';
                  return (
                    <div key={q.instrument + q.rank} className="cfg"
                      style={{ gridTemplateColumns: '20px 1fr auto auto' }}>
                      <div style={{ color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{q.rank}</div>
                      <div><b style={{ fontFamily: 'var(--mono)', color: 'var(--blue)' }}>{q.instrument}</b>{' '}
                        <span className="note">{q.decision}</span></div>
                      <TagChip color={cc}>{rc}</TagChip>
                      <div className="val">{num(q.score)}</div>
                    </div>
                  );
                })}
            <div className="note" style={{ marginTop: 8 }}>
              Not a plain composite sort — risk/sizing outrank valuation harvests.
            </div>
          </div>

          <div className="card">
            <h3>Theme concentration <span className="tag">rebalance check</span></h3>
            {p.portfolio_layer.theme_concentration.map((t) => (
              <div key={t.theme} className="cfg">
                <div className="lbl"><b>{t.theme}</b><small>sub-sector</small></div>
                <Bar value={Math.min(100, t.alloc_pct * 5)} color={t.status === 'breach' ? 'var(--yellow)' : 'var(--green)'} />
                <div className="val" style={{ color: t.status === 'breach' ? 'var(--yellow)' : undefined }}>
                  {t.alloc_pct.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>

          <div className="card">
            <h3>Tax-aware sequencing <span className="tag">render, don't calculate</span></h3>
            {p.portfolio_layer.tax_sequencing.slice(0, 5).map((t) => (
              <div key={t.instrument} className="cfg">
                <div className="lbl"><b style={{ fontFamily: 'var(--mono)', color: 'var(--blue)' }}>{t.instrument}</b>
                  <small>{t.decision}</small></div>
                <div></div>
                <div className="val" style={{ fontSize: 12 }}>
                  LTCG ₹{num(t.ltcg_gain)} · STCG ₹{num(t.stcg_gain)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function meta(d: string): string {
  const map: Record<string, string> = {
    HOLD: '#34d399', WATCH: '#fbbf24', TRIM: '#fb923c', HARVEST: '#a78bfa',
    EXIT: '#f87171', 'NO-DECISION': '#94a3b8',
  };
  return map[d] ?? '#34d399';
}

export { CAT_COLORS };
