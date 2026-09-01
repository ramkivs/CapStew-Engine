import { useEffect, useMemo, useState } from 'react';
import type { DecisionPayload, Holding } from '../types';
import { Badge, Banner, Bar, Stat, TagChip, inr, pct, num } from './ui';
import { comparatorFor, cycleSort } from '../utils/sort';
import { exportDecisionsJson, exportDecisionsCsv } from '../utils/exportDecisions';
import type { SortDir, SortState } from '../utils/sort';

const CAT_COLORS: Record<string, string> = {
  position_sizing: '#34d399',
  valuation_stretch: '#fb923c',
  quality_drift: '#a78bfa',
  tax_efficiency: '#60a5fa',
  opportunity_cost: '#fbbf24',
  technical_regime: '#94a3b8',
};

type PayloadWarning = DecisionPayload['warnings'][number];

type SortKey =
  | 'instrument'
  | 'bucket'
  | 'alloc'
  | 'gain'
  | 'decision'
  | 'gate'
  | 'composite'
  | 'confidence'
  | 'review';

const SORT_COLUMNS: Record<
  SortKey,
  { label: string; numeric: boolean; get: (h: Holding) => string | number | null }
> = {
  instrument: { label: 'Instrument', numeric: false, get: (h) => h.ticker ?? h.instrument },
  bucket: { label: 'Bucket', numeric: false, get: (h) => h.bucket },
  // G0 holdings intentionally omit scored-only fields under CR-022.
  alloc: { label: 'Alloc', numeric: true, get: (h) => h.decision === 'NO-DECISION' ? null : h.alloc_pct },
  gain: { label: 'Gain/Loss', numeric: true, get: (h) => h.decision === 'NO-DECISION' ? null : h.gain_pct },
  decision: { label: 'Final decision', numeric: false, get: (h) => h.decision },
  gate: { label: 'Gate state', numeric: false, get: (h) => gateMeta(h).label },
  composite: { label: 'Composite', numeric: true, get: (h) => h.composite_score },
  confidence: { label: 'Conf', numeric: true, get: (h) => h.confidence },
  review: { label: 'Review', numeric: false, get: (h) => h.next_review_date },
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
  const holdingsByInstrument = new Map(p.holdings.map((h) => [h.instrument, h]));
  const warningsByInstrument = groupWarningsByInstrument(p.warnings);

  // CR-026 (R-SORT-001): view-local presentation state. The default null state
  // leaves the authoritative backend holding order untouched and resets whenever
  // the payload object changes, including preview swaps and clears.
  const [sort, setSort] = useState<SortState<SortKey> | null>(null);
  useEffect(() => {
    setSort(null);
  }, [p]);
  const holdings = useMemo(() => {
    if (sort === null) return p.holdings;
    const col = SORT_COLUMNS[sort.key];
    // Sort a copy only: payload arrays and all backend-derived exports remain
    // unchanged (ADR-1a; CR-026 presentation-only behavior).
    return [...p.holdings].sort(
      comparatorFor(
        (h: Holding) => col.get(h),
        sort.dir,
        (h: Holding) => h.ticker ?? h.instrument,
      ),
    );
  }, [p, sort]);

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

      {p.warnings.length > 0 ? (
        <Banner kind="warn">
          <div>
            <b>Trust warnings from backend payload.</b> Review before acting; stale-data and reconciliation warnings are shown here when emitted.
            <ul style={{ marginTop: 6, paddingLeft: 18 }}>
              {p.warnings.slice(0, 5).map((w, i) => (
                <li key={`${w.code}-${w.instrument ?? 'portfolio'}-${i}`}>
                  <span className="kbd">{w.code}</span>{' '}
                  {w.instrument ? <b>{w.instrument}: </b> : <b>Portfolio: </b>}
                  {w.message}
                </li>
              ))}
            </ul>
            {p.warnings.length > 5 ? <div className="note">+{p.warnings.length - 5} more warning(s) in the authoritative payload.</div> : null}
          </div>
        </Banner>
      ) : (
        <Banner kind="ok">
          <b>No backend warnings reported for this run.</b> Decisions still remain advisory and require human review.
        </Banner>
      )}

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Decision clarity <span className="tag">backend-authoritative · presentation only</span></h3>
        <div className="grid cols-3">
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Final decision</b><br />
            The badge is the backend decision to review. The browser does not recompute or override it.
          </div>
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Composite score</b><br />
            Score is a supporting signal from Stage 2, not a standalone action instruction.
          </div>
          <div className="note">
            <b style={{ color: 'var(--text)' }}>Gate state</b><br />
            Gate chips use backend <span className="kbd">stage1</span> fields to show whether a hard gate drove the decision path.
          </div>
        </div>
      </div>

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
        <Stat k="Gate-driven holdings" v={<span style={{ color: 'var(--red)' }}>{p.portfolio_summary.stage1_gates_fired}</span>}
          s="shown from authoritative Stage 1 gate state" />
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 14, justifyContent: 'flex-end' }}>
        <button className="btn" type="button" onClick={() => exportDecisionsJson(payload)}>Decisions JSON</button>
        <button className="btn" type="button" onClick={() => exportDecisionsCsv(payload)}>Decisions CSV</button>
      </div>
      <div className="grid cols-2">
        <div className="card">
          <h3>Holdings — scored & ranked <span className="tag">click header → sort · click row → detail</span></h3>
          <div className="note" style={{ marginBottom: 8 }}>
            Decision, score, confidence, gate state, and review date are displayed separately to avoid treating a composite score as the action.
            Header sorting is presentation-only (nulls shown as — always sort last): it never changes decisions, ranks, sizing, gate state, or exports.
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {(Object.entries(SORT_COLUMNS) as [SortKey, (typeof SORT_COLUMNS)[SortKey]][]).map(([key, col]) => {
                    const active = sort?.key === key;
                    const direction: SortDir | undefined = active ? sort?.dir : undefined;
                    return (
                      <th key={key} className={col.numeric ? 'num' : undefined}
                        aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                        <button
                          type="button"
                          className={`th-sort${active ? ' active' : ''}`}
                          title={`Sort by ${col.label}`}
                          aria-label={`Sort by ${col.label}${active ? ` (currently ${direction === 'asc' ? 'ascending' : 'descending'})` : ''}`}
                          onClick={() => setSort((current) => cycleSort(current, key))}
                        >
                          {col.label}
                          <span className="sort-ind" aria-hidden="true">
                            {active ? (direction === 'asc' ? '▲' : '▼') : '⇅'}
                          </span>
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => {
                  const m = meta(h.decision);
                  const prev = h.previous_run;
                  const changed = prev && prev.decision !== h.decision;
                  const gate = gateMeta(h);
                  return (
                    <tr key={h.instrument} className="row" onClick={() => onSelect(h)}>
                      <td className="tick">{h.ticker ?? h.instrument}
                        {h.decision !== 'NO-DECISION' && h.data_completeness.position_sizing === false ? ' · partial' : ''}
                        {h.decision !== 'NO-DECISION' && h.behavioral.blocks_adds ? ' ' : ''}
                      </td>
                      <td className="muted" style={{ fontFamily: 'system-ui' }}>{h.bucket ?? '—'}</td>
                      <td className="num">{h.decision === 'NO-DECISION' ? '—' : pct(h.alloc_pct)}</td>
                      <td className={`num ${h.decision === 'NO-DECISION' ? '' : (h.gain_pct ?? 0) >= 0 ? 'up' : 'down'}`}>
                        {h.decision === 'NO-DECISION' ? '—' : `${(h.gain_pct ?? 0) >= 0 ? '+' : ''}${pct(h.gain_pct)}`}
                      </td>
                      <td>
                        <Badge decision={h.decision} />
                        {changed ? <span className="note" style={{ marginLeft: 6, fontSize: 10 }}>↑ prev {prev!.decision}</span> : null}
                      </td>
                      <td><TagChip color={gate.color}>{gate.label}</TagChip></td>
                      <td className="num" style={{ color: m }}>{num(h.composite_score)}</td>
                      <td className="num">{h.confidence == null ? '—' : `${h.confidence}%`}</td>
                      <td className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{h.next_review_date ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid" style={{ gap: 14 }}>
          <div className="card">
            <h3>Action queue <span className="tag">authoritative rows · enriched by holding payload</span></h3>
            {p.portfolio_layer.action_queue.length === 0
              ? <div className="note">No candidates.</div>
              : p.portfolio_layer.action_queue.map((q) => {
                  const h = holdingsByInstrument.get(q.instrument);
                  const rc = q.reason;
                  const cc = rc === 'RISK' ? 'var(--red)' : rc === 'SIZING' ? 'var(--orange)' : 'var(--violet)';
                  const trim = h?.trim;
                  const rowWarnings = warningsByInstrument.get(q.instrument) ?? [];
                  return (
                    <div key={q.instrument + q.rank} className="card" style={{ background: '#0e1526', marginTop: 10, padding: 12 }}>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                        <div>
                          <span style={{ color: 'var(--dim)', fontFamily: 'var(--mono)', marginRight: 8 }}>#{q.rank}</span>
                          <b style={{ fontFamily: 'var(--mono)', color: 'var(--blue)' }}>{q.instrument}</b>{' '}
                          <Badge decision={q.decision} />
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                          <TagChip color={cc}>{rc}</TagChip>
                          <span className="val">score {num(q.score)}</span>
                        </div>
                      </div>

                      <div className="note" style={{ marginTop: 8 }}>
                        {h?.reason_tree.decision_path ?? 'Holding-level decision path unavailable in payload.'}
                        {h?.why_now?.primary_trigger ? ` · why now: ${h.why_now.primary_trigger}` : ''}
                      </div>

                      {trim ? (
                        <div className="grid cols-3" style={{ marginTop: 10 }}>
                          <div className="stat"><div className="k">Trim mode</div><div className="v" style={{ fontSize: 16 }}>{trim.mode}</div></div>
                          <div className="stat"><div className="k">Suggested qty</div><div className="v" style={{ fontSize: 16 }}>{num(trim.suggested_qty)}</div></div>
                          <div className="stat"><div className="k">Suggested value</div><div className="v" style={{ fontSize: 16 }}>{inr(trim.suggested_value)}</div></div>
                        </div>
                      ) : (
                        <div className="note" style={{ marginTop: 8 }}>
                          No trim quantity/value displayed because no authoritative trim object is present for this queue item.
                        </div>
                      )}

                      <div className="note" style={{ marginTop: 8 }}>
                        Trust caveat: {qualityCaveat(h)}
                        {h?.next_review_date ? ` · next review ${h.next_review_date}` : ''}
                      </div>
                      {rowWarnings.length > 0 ? (
                        <div className="note" style={{ marginTop: 6, color: 'var(--yellow)' }}>
                          Warning(s): {rowWarnings.map(formatWarning).join(' · ')}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
            <div className="note" style={{ marginTop: 8 }}>
              Queue order, reasons, scores, and trim fields are rendered from backend payload data. The browser does not calculate decisions, sizing, taxes, or trims.
            </div>
          </div>

          <div className="card">
            <h3>Confidence guide <span className="tag">trust ≠ expected return</span></h3>
            <div className="note">
              Confidence is a backend evidence-quality indicator on a 20–95 scale. It describes trust in available inputs, not expected upside or certainty of outcome.
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

function gateMeta(h: Holding): { label: string; color: string } {
  if (h.stage1.fired) {
    return { label: h.stage1.winning_gate ?? h.stage1.gates_fired[0] ?? 'Stage 1 gate', color: 'var(--red)' };
  }
  if (h.stage1.tax_defer_suppressed) {
    return { label: 'Tax defer suppressed', color: 'var(--yellow)' };
  }
  return { label: 'No Stage 1 gate', color: 'var(--green)' };
}

function groupWarningsByInstrument(warnings: PayloadWarning[]): Map<string, PayloadWarning[]> {
  const grouped = new Map<string, PayloadWarning[]>();
  for (const warning of warnings) {
    if (!warning.instrument) continue;
    const existing = grouped.get(warning.instrument) ?? [];
    existing.push(warning);
    grouped.set(warning.instrument, existing);
  }
  return grouped;
}

function formatWarning(w: PayloadWarning): string {
  return `${w.code}: ${w.message}`;
}

function qualityCaveat(h: Holding | undefined): string {
  if (!h) return 'holding details unavailable in payload';
  if (h.decision === 'NO-DECISION') {
    return `no decision issued: ${h.reason_tree.decision_path}`;
  }

  const parts: string[] = [];
  if (h.evidence) {
    parts.push(`evidence ${h.evidence.tier}, coverage ${(h.evidence.coverage * 100).toFixed(0)}%`);
    if (h.evidence.critical_categories_missing.length > 0) {
      parts.push(`missing critical ${h.evidence.critical_categories_missing.join(', ')}`);
    }
  } else {
    parts.push('evidence unavailable');
  }

  const dataQualityCaveats = Object.entries(h.data_quality)
    .filter(([, v]) => !['actual', 'complete', 'ok', 'available'].includes(String(v).toLowerCase()))
    .map(([k, v]) => `${k.replace(/_/g, ' ')}=${v}`);
  if (dataQualityCaveats.length > 0) {
    parts.push(`data quality ${dataQualityCaveats.slice(0, 3).join(', ')}`);
  }

  const incomplete = Object.entries(h.data_completeness)
    .filter(([, ok]) => ok === false)
    .map(([k]) => k.replace(/_/g, ' '));
  if (incomplete.length > 0) {
    parts.push(`partial ${incomplete.slice(0, 3).join(', ')}`);
  }

  if (h.confidence != null) {
    parts.push(`confidence ${h.confidence}%`);
  }

  return parts.join(' · ');
}

export { CAT_COLORS };
