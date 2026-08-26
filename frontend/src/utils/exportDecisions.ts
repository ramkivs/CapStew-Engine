import type { DecisionPayload, Holding } from '../types';

// Client-side export of the AUTHORITATIVE payload only — pure serialization of
// what the backend already returned. The browser recomputes nothing (ADR-1a),
// nothing is persisted server-side, and nothing leaves the local session.

const HEADERS = [
  'instrument', 'ticker', 'bucket', 'decision', 'composite_score', 'confidence',
  'alloc_pct', 'gain_pct', 'current_value', 'qty_held',
  'winning_gate', 'gates_fired', 'primary_trigger',
  'trim_mode', 'trim_suggested_qty', 'trim_suggested_value',
  'ltcg_eligible_lots', 'oldest_lot_days_to_ltcg', 'next_review_date',
] as const;

function row(h: Holding): (string | number | null)[] {
  return [
    h.instrument, h.ticker, h.bucket, h.decision, h.composite_score, h.confidence,
    h.alloc_pct, h.gain_pct, h.current_value, h.qty_held,
    h.stage1?.winning_gate ?? null, (h.stage1?.gates_fired ?? []).join('|') || null,
    h.why_now?.primary_trigger ?? null,
    h.trim?.mode ?? null, h.trim?.suggested_qty ?? null, h.trim?.suggested_value ?? null,
    h.tax_status?.ltcg_eligible_lots ?? null, h.tax_status?.oldest_lot_days_to_ltcg ?? null,
    h.next_review_date,
  ];
}

function esc(v: string | number | null): string {
  if (v === null || v === undefined) return '';
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function decisionsToCsv(payload: DecisionPayload): string {
  const meta = [
    `# run_id=${payload.run_id}`,
    `# as_of=${payload.as_of}`,
    `# engine_version=${payload.engine_version}`,
    `# policy_version=${payload.policy_version}`,
    `# content_hash=${payload.content_hash}`,
  ];
  const lines = [
    (HEADERS as readonly string[]).join(','),
    ...payload.holdings.map((h) => row(h).map(esc).join(',')),
  ];
  return meta.join('\n') + '\n' + lines.join('\n') + '\n';
}

function save(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function exportDecisionsJson(payload: DecisionPayload): string {
  const name = `decisions_${payload.run_id}.json`;
  save(name, JSON.stringify(payload, null, 2) + '\n', 'application/json');
  return name;
}

export function exportDecisionsCsv(payload: DecisionPayload): string {
  const name = `decisions_${payload.run_id}.csv`;
  save(name, decisionsToCsv(payload), 'text/csv');
  return name;
}
