import { describe, it, expect } from 'vitest';
import { decisionsToCsv } from './exportDecisions';
import { noDecisionHolding, payload, scoredHolding } from '../test/fixture';

describe('decisionsToCsv — serialization of the authoritative payload only', () => {
  it('stamps provenance so an exported file can be traced to a run', () => {
    const csv = decisionsToCsv(payload([scoredHolding()]));
    const head = csv.split('\n').slice(0, 5);
    expect(head[0]).toBe('# run_id=run_20260822T000000_abc123');
    expect(head[1]).toBe('# as_of=2026-08-22');
    expect(head[4]).toBe('# content_hash=contenthash');
  });

  it('emits one header row and one row per holding', () => {
    const lines = decisionsToCsv(payload([scoredHolding(), scoredHolding({ instrument: 'X' })]))
      .split('\n').filter((l) => l && !l.startsWith('#'));
    expect(lines).toHaveLength(3);
    expect(lines[0].startsWith('instrument,ticker,bucket,decision')).toBe(true);
  });

  it('exports the backend value verbatim — the browser recomputes nothing', () => {
    const csv = decisionsToCsv(payload([scoredHolding({ composite_score: 65.2, decision: 'TRIM' })]));
    const row = csv.split('\n').find((l) => l.startsWith('Salasar Techno Engg'))!;
    expect(row).toContain('TRIM');
    expect(row).toContain('65.2');
  });

  it('renders a NO-DECISION row with empty scored fields rather than crashing', () => {
    const csv = decisionsToCsv(payload([noDecisionHolding()]));
    const row = csv.split('\n').find((l) => l.startsWith('Bajaj Finance'))!;
    expect(row).toContain('NO-DECISION');
    expect(row).toContain('G0');
    // alloc/gain/value/qty are blank — never fabricated
    expect(row.split(',')[4]).toBe('');
  });

  it('quotes values containing commas or quotes (RFC 4180)', () => {
    const csv = decisionsToCsv(payload([scoredHolding({ instrument: 'Ltd, "A" Co' })]));
    expect(csv).toContain('"Ltd, ""A"" Co"');
  });
});
