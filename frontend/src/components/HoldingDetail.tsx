import type { Holding } from '../types';
import { Badge, Bar, Ring, TagChip, inr, num, pct } from './ui';
import { CAT_COLORS } from './DecisionsView';

const CAT_LABELS: Record<string, string> = {
  position_sizing: 'Position sizing',
  valuation_stretch: 'Valuation stretch',
  quality_drift: 'Quality drift',
  tax_efficiency: 'Tax efficiency',
  opportunity_cost: 'Opportunity cost (PEG proxy)',
  technical_regime: 'Technical / regime',
};

export function HoldingDetail({ holding, onClose }: { holding: Holding | null; onClose: () => void }) {
  if (!holding) return null;
  const h = holding;
  const m = meta(h.decision);
  const weights = h.subscores;
  const gate = gateMeta(h);
  const confidenceBreakdown = Object.entries(h.confidence_breakdown ?? {});
  const incompleteInputs = Object.entries(h.data_completeness)
    .filter(([, ok]) => ok === false)
    .map(([k]) => k.replace(/_/g, ' '));

  return (
    <>
      <div className={`scrim ${holding ? 'open' : ''}`} onClick={onClose} />
      <div className={`slideover ${holding ? 'open' : ''}`} role="dialog" aria-modal="true">
        <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {h.ticker ?? h.instrument}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>
              {h.instrument} <span className="note" style={{ fontWeight: 400 }}>· {h.bucket ?? 'unknown bucket'}</span>
            </div>
          </div>
          <Badge decision={h.decision} />
          <TagChip color={gate.color}>{gate.label}</TagChip>
          <span className="chip warn">Human review required</span>
          <button className="btn" style={{ padding: '6px 12px' }} onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: '16px 20px' }}>
          <div className="grid cols-3" style={{ marginBottom: 14 }}>
            <div className="stat">
              <div className="k">Final backend decision</div>
              <div className="v" style={{ fontSize: 18 }}><Badge decision={h.decision} /></div>
              <div className="s">Action badge; not recalculated in browser.</div>
            </div>
            <div className="stat">
              <div className="k">Composite score</div>
              <div className="v" style={{ color: m }}>{num(h.composite_score)}</div>
              <div className="s">Supporting Stage 2 signal, not the action itself.</div>
            </div>
            <div className="stat">
              <div className="k">Gate / override state</div>
              <div className="v" style={{ fontSize: 16 }}><TagChip color={gate.color}>{gate.label}</TagChip></div>
              <div className="s">From backend Stage 1 fields.</div>
            </div>
          </div>

          <div className="grid cols-2">
            <div className="card">
              <h3>Confidence / trust <span className="tag">20–95 scale · not expected return</span></h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <Ring value={h.confidence ?? 0} color={m} />
                <div className="subs">
                  <div className="note">
                    Confidence is the backend evidence-quality/trust indicator. It does <b>not</b> mean expected upside, probability of profit, or certainty of outcome.
                  </div>
                  <Row label="Evidence tier" value={h.evidence?.tier ?? '—'} />
                  <Row label="Evidence coverage" value={h.evidence ? `${(h.evidence.coverage * 100).toFixed(0)}%` : '—'} />
                  <Row label="Critical missing" value={h.evidence?.critical_categories_missing.length ? h.evidence.critical_categories_missing.join(', ') : 'none reported'} />
                </div>
              </div>

              <div style={{ marginTop: 12 }}>
                <div className="note" style={{ marginBottom: 6 }}>
                  Backend-reported confidence breakdown / penalties:
                </div>
                {confidenceBreakdown.length > 0 ? confidenceBreakdown.map(([label, value]) => (
                  <div key={label} className="cfg" style={{ gridTemplateColumns: '1fr auto', padding: '6px 0' }}>
                    <div className="lbl"><b>{label.replace(/_/g, ' ')}</b></div>
                    <div className="val">{num(value, 1)}</div>
                  </div>
                )) : <div className="note">No confidence breakdown supplied.</div>}
              </div>
            </div>

            <div className="grid" style={{ gap: 14, alignContent: 'start' }}>
              <div className="card">
                <h3>Position snapshot</h3>
                <Row label="Allocation" value={pct(h.alloc_pct)} />
                <Row label="Gain / Loss" value={(h.gain_pct ?? 0) >= 0 ? `+${pct(h.gain_pct)}` : pct(h.gain_pct)}
                  color={(h.gain_pct ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
                <Row label="Pledged promoter" value={`${num(h.pledge_pct)}%`}
                  color={(h.pledge_pct ?? 0) > 10 ? 'var(--red)' : 'var(--green)'} />
                <Row label="Next review" value={h.next_review_date ?? '—'} color={h.next_review_date ? 'var(--yellow)' : undefined} />
                <div className="note" style={{ marginTop: 6 }}>
                  Review date is backend-provided. This view does not create a new schedule.
                </div>
              </div>
              <div className="card">
                <h3>Decision path <span className="tag">gate state separated from score</span></h3>
                <Row label="Stage 1 fired" value={h.stage1.fired ? 'yes' : 'no'} color={h.stage1.fired ? 'var(--red)' : 'var(--green)'} />
                <Row label="Winning gate" value={h.stage1.winning_gate ?? '—'} color={h.stage1.fired ? 'var(--red)' : undefined} />
                <Row label="Gates fired" value={h.stage1.gates_fired.length ? h.stage1.gates_fired.join(', ') : 'none'} />
                <Row label="Tax defer suppressed" value={h.stage1.tax_defer_suppressed ? 'yes' : 'no'} color={h.stage1.tax_defer_suppressed ? 'var(--yellow)' : undefined} />
                <div className="note" style={{ marginTop: 8, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                  {h.reason_tree.decision_path}
                </div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Composite score contributors <span className="tag">backend subscore display</span></h3>
            {Object.entries(CAT_LABELS).map(([k, label]) => (
              <div key={k} className="subrow" style={{ marginTop: 9 }}>
                <span>{label}</span>
                <Bar value={weights[k as keyof typeof weights] ?? 0} color={CAT_COLORS[k]} />
                <span className="num" style={{ fontFamily: 'var(--mono)' }}>{num(weights[k as keyof typeof weights])}</span>
              </div>
            ))}
            <div className="note" style={{ marginTop: 10 }}>
              These are authoritative backend subscores. The frontend only renders the supplied values.
              Opportunity Cost is currently the backend PEG proxy where fundamentals exist;
              D-14 / hurdle_d14 and watchlist scoring are not live unless separately authorized.
            </div>
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Why now / actionability context</h3>
            <div className="note" style={{ marginBottom: 8 }}>
              Primary trigger: <b style={{ color: 'var(--text)' }}>{h.why_now?.primary_trigger ?? '—'}</b>
            </div>
            {h.why_now?.contributors?.length ? (
              <div className="grid cols-3">
                {h.why_now.contributors.map((c) => (
                  <div key={c.label} className="stat">
                    <div className="k">{c.label}</div>
                    <div className="v" style={{ fontSize: 16 }}>{num(c.value, 1)}</div>
                    <div className="s">weight {num(c.weight, 2)}</div>
                  </div>
                ))}
              </div>
            ) : <div className="note">No contributor list supplied.</div>}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Evidence and data-quality caveats <span className="tag">trust boundary</span></h3>
            <div className="note">
              Evidence: {h.evidence?.tier ?? '—'} · coverage {h.evidence ? `${(h.evidence.coverage * 100).toFixed(0)}%` : '—'}
              {h.evidence?.critical_categories_missing.length
                ? ` · missing critical: ${h.evidence.critical_categories_missing.join(', ')}` : ' · no critical missing categories reported'}
            </div>
            <div className="note" style={{ marginTop: 6 }}>
              data quality: {Object.entries(h.data_quality).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ') || '—'}
            </div>
            <div className="note" style={{ marginTop: 6 }}>
              completeness: {incompleteInputs.length ? `partial ${incompleteInputs.join(', ')}` : 'all reported categories complete'}
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
              <h3>Suggested trim <span className="tag">authoritative FIFO lot-aware payload · mode {h.trim.mode}</span></h3>
              <div className="note" style={{ marginBottom: 10 }}>
                Quantity, value, mode, lots, taxes, and costs are backend-provided. The browser does not calculate trim, sizing, or tax effects.
              </div>
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
              Indian CGT is per-lot FIFO — a trim sells the <b>oldest unsold lots first</b>. This section renders backend lot data only.
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

function gateMeta(h: Holding): { label: string; color: string } {
  if (h.stage1.fired) {
    return { label: h.stage1.winning_gate ?? h.stage1.gates_fired[0] ?? 'Stage 1 gate', color: 'var(--red)' };
  }
  if (h.stage1.tax_defer_suppressed) {
    return { label: 'Tax defer suppressed', color: 'var(--yellow)' };
  }
  return { label: 'No Stage 1 gate', color: 'var(--green)' };
}
