import type { Holding } from '../types';
import { Badge, Bar, Ring, inr, num, pct } from './ui';
import { CAT_COLORS } from './DecisionsView';

const CAT_LABELS: Record<string, string> = {
  position_sizing: 'Position sizing',
  valuation_stretch: 'Valuation stretch',
  quality_drift: 'Quality drift',
  tax_efficiency: 'Tax efficiency',
  opportunity_cost: 'Opportunity cost',
  technical_regime: 'Technical / regime',
};

export function HoldingDetail({ holding, onClose }: { holding: Holding | null; onClose: () => void }) {
  if (!holding) return null;
  const h = holding;
  const m = meta(h.decision);
  const d = h.decision;
  const weights = h.subscores;

  return (
    <>
      <div className={`scrim ${holding ? 'open' : ''}`} onClick={onClose} />
      <div className={`slideover ${holding ? 'open' : ''}`} role="dialog" aria-modal="true">
        <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {h.ticker ?? h.instrument}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>
              {h.instrument} <span className="note" style={{ fontWeight: 400 }}>· {h.bucket ?? 'unknown bucket'}</span>
            </div>
          </div>
          <Badge decision={h.decision} />
          <span className="chip warn">Human review required</span>
          <button className="btn" style={{ padding: '6px 12px' }} onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: '16px 20px' }}>
          <div className="grid cols-2">
            <div className="card">
              <h3>Composite & confidence</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <Ring value={h.confidence ?? 0} color={m} />
                <div className="subs">
                  <div className="subrow">
                    <span className="muted">Composite score</span><span></span>
                    <span className="num" style={{ color: m, fontSize: 15 }}>{num(h.composite_score)}</span>
                  </div>
                  <div className="note">
                    Confidence = round(clamp(100 − Σ penalties, 20, 95)) — breakdown lists the penalties.
                  </div>
                </div>
              </div>
              {Object.entries(CAT_LABELS).map(([k, label]) => (
                <div key={k} className="subrow" style={{ marginTop: 9 }}>
                  <span>{label} <span className="w">{h.reason_tree.stage2.subscores ? '' : ''}</span></span>
                  <Bar value={weights[k as keyof typeof weights] ?? 0} color={CAT_COLORS[k]} />
                  <span className="num" style={{ fontFamily: 'var(--mono)' }}>{num(weights[k as keyof typeof weights])}</span>
                </div>
              ))}
            </div>

            <div className="grid" style={{ gap: 14, alignContent: 'start' }}>
              <div className="card">
                <h3>Position snapshot</h3>
                <Row label="Allocation" value={pct(h.alloc_pct)} />
                <Row label="Gain / Loss" value={(h.gain_pct ?? 0) >= 0 ? `+${pct(h.gain_pct)}` : pct(h.gain_pct)}
                  color={(h.gain_pct ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
                <Row label="Pledged promoter" value={`${num(h.pledge_pct)}%`}
                  color={(h.pledge_pct ?? 0) > 10 ? 'var(--red)' : 'var(--green)'} />
                <Row label="Next review" value={h.next_review_date ?? '—'} />
              </div>
              <div className="card">
                <h3>Decision path</h3>
                <div className="note" style={{ fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                  {h.reason_tree.decision_path}
                </div>
                <div className="note" style={{ marginTop: 6 }}>
                  Evidence: {h.evidence?.tier ?? '—'} · coverage {h.evidence ? `${(h.evidence.coverage * 100).toFixed(0)}%` : '—'}
                  {h.evidence?.critical_categories_missing.length
                    ? ` · missing critical: ${h.evidence.critical_categories_missing.join(', ')}` : ''}
                </div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Primary drivers</h3>
            <ul className="drivers">
              {h.primary_drivers.map((d, i) => {
                const isGate = /GATE/i.test(d) || /G1|G2|G3/i.test(d);
                return <li key={i} className={isGate ? 'gate' : 'warn'} dangerouslySetInnerHTML={{ __html: d }} />;
              })}
            </ul>
          </div>

          {h.watch_flags.length > 0 ? (
            <div className="card" style={{ marginTop: 14 }}>
              <h3>Watch flags</h3>
              <ul className="drivers">
                {h.watch_flags.map((w, i) => <li key={i} className="danger">⚠ {w}</li>)}
              </ul>
            </div>
          ) : null}

          {h.behavioral.blocks_adds ? (
            <div className="card" style={{ marginTop: 14 }}>
              <h3>Behavioral guardrail</h3>
              <ul className="drivers">
                <li className="danger"><b>Averaging-into-losses.</b> Further adds require a written
                  re-underwrite. Caution only — this is not an exit gate.</li>
              </ul>
            </div>
          ) : null}

          {h.trim ? (
            <div className="card" style={{ marginTop: 14 }}>
              <h3>Suggested trim <span className="tag">FIFO lot-aware · mode {h.trim.mode}</span></h3>
              <div className="grid cols-3">
                <div className="stat"><div className="k">Qty</div><div className="v" style={{ fontSize: 17 }}>
                  {h.trim.suggested_qty == null ? '—' : `${num(h.trim.suggested_qty)} / ${h.qty_held ?? '—'}`}</div></div>
                <div className="stat"><div className="k">Value</div><div className="v" style={{ fontSize: 17 }}>
                  {inr(h.trim.suggested_value)}</div></div>
                <div className="stat"><div className="k">Lots</div><div className="v" style={{ fontSize: 15 }}>
                  {h.trim.fifo_lots_to_sell.map((l) => `#${l.lot_id}`).join(', ') || '—'}</div></div>
              </div>
              <div className="note" style={{ marginTop: 10 }}>
                Tax: STCG ₹{num(h.trim.tax_breakdown.stcg_gain)} (+₹{num(h.trim.tax_breakdown.stcg_tax)}) ·
                LTCG ₹{num(h.trim.tax_breakdown.ltcg_gain)} (+₹{num(h.trim.tax_breakdown.ltcg_tax)}) ·
                est. cost ₹{num(h.trim.est_transaction_cost)}
                {h.trim.participation_capped ? ' · participation-capped' : ''}
              </div>
            </div>
          ) : null}

          <div className="card" style={{ marginTop: 14 }}>
            <h3>FIFO tax lots <span className="tag">per-lot · oldest-first</span></h3>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Lot</th><th>Trade date</th><th className="num">Qty</th><th className="num">Buy</th>
                    <th className="num">LTP</th><th className="num">P&amp;L</th><th className="num">%</th>
                    <th className="num">Held</th><th className="num">To LTCG</th>
                  </tr>
                </thead>
                <tbody>
                  {h.lots.map((l) => (
                    <tr key={l.lot_id}>
                      <td className="tick">#{l.lot_id}</td>
                      <td>{l.trade_date}</td>
                      <td className="num">{l.qty}</td>
                      <td className="num">{l.buy_price.toFixed(2)}</td>
                      <td className="num">{l.ltp.toFixed(2)}</td>
                      <td className={`num ${(l.pnl ?? 0) >= 0 ? 'up' : 'down'}`}>
                        {(l.pnl ?? 0) >= 0 ? '+' : ''}{num(l.pnl)}</td>
                      <td className={`num ${(l.pnl_pct ?? 0) >= 0 ? 'up' : 'down'}`}>
                        {(l.pnl_pct ?? 0) >= 0 ? '+' : ''}{num(l.pnl_pct, 1)}%</td>
                      <td className="num">{l.days_held}d</td>
                      <td className={`num ${l.days_to_ltcg === 0 ? 'up' : ''}`}>
                        {l.days_to_ltcg === 0 ? 'LTCG ✓' : `${l.days_to_ltcg}d`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="note" style={{ marginTop: 8 }}>
              Indian CGT is per-lot FIFO — a trim sells the <b>oldest unsold lots first</b>.
            </div>
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Provenance</h3>
            <div className="note" style={{ fontFamily: 'var(--mono)' }}>
              {JSON.stringify(h.reason_tree.stage1)} · {h.reason_tree.decision_path}
            </div>
            <div className="note" style={{ marginTop: 4 }}>
              data quality: {Object.entries(h.data_quality).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ')}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="cfg" style={{ borderBottom: 'none', padding: '5px 0' }}>
      <div className="lbl"><b style={{ color: 'var(--muted)' }}>{label}</b></div>
      <div></div>
      <div className="val" style={{ color: color ?? 'var(--text)' }}>{value}</div>
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
