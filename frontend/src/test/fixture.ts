import type { DecisionPayload, Holding } from '../types';

/** A scored holding, matching what `app/decision.py` emits for a normal run. */
export function scoredHolding(over: Partial<Holding> = {}): Holding {
  return {
    instrument: 'Salasar Techno Engg',
    ticker: 'SALASAR',
    bucket: 'micro',
    alloc_pct: 9.8,
    gain_pct: 51.3,
    current_value: 36720,
    qty_held: 480,
    pledge_pct: 4.0,
    decision: 'TRIM',
    composite_score: 65.2,
    confidence: 75,
    confidence_breakdown: { missing_data: 0, divergence: 5, boundary: 0, proxy: 20, staleness: 0, confidence: 75 },
    subscores: {
      position_sizing: 90, valuation_stretch: 40, quality_drift: 20,
      tax_efficiency: 60, opportunity_cost: 30, technical_regime: 25,
    },
    stage1: { fired: true, gates_fired: ['G2_allocation'], winning_gate: 'G2', tax_defer_suppressed: false },
    evidence: { coverage: 1, tier: 'NORMAL', missing_weight: 0, critical_categories_missing: [] },
    primary_drivers: ['HARD GATE G2'],
    watch_flags: [],
    behavioral_flags: ['none'],
    behavioral: { flag: 'none', requires_reunderwrite: false, blocks_adds: false },
    trim: {
      mode: 'S', suggested_qty: 100, suggested_value: 7650,
      fifo_lots_to_sell: [{ lot_id: 1, qty: 100 }],
      tax_breakdown: { stcg_gain: 3450, ltcg_gain: 0, stcg_tax: 517, ltcg_tax: 0, realized_loss: 0 },
      est_transaction_cost: 27, alloc_after_pct: 8.0, target_alloc_pct: 8.0,
      participation_capped: false, rho: 1.0,
    },
    tax_status: { mixed_ltcg: false, oldest_lot_days_to_ltcg: 112, ltcg_eligible_lots: 0 },
    data_completeness: { position_sizing: true, valuation_stretch: true, quality_drift: true, tax_efficiency: true, opportunity_cost: true, technical_regime: true },
    data_quality: { position_sizing: 'authoritative', valuation_stretch: 'proxy' },
    lots: [{ lot_id: 1, instrument: 'Salasar Techno Engg', ticker: 'SALASAR', trade_date: '2026-04-23', qty: 160, buy_price: 42, ltp: 76.5, invested: 6720, value: 12240, pnl: 5520, pnl_pct: 82.1, days_held: 121, days_to_ltcg: 244, ltcg_eligible: false }],
    reason_tree: { decision_path: 'G2 → TRIM (mode S)', stage1: {}, stage2: {} },
    why_now: { primary_trigger: 'G2 — G2_allocation', contributors: [] },
    previous_run: null,
    next_review_date: '2026-08-29',
    ...over,
  };
}

/**
 * A G0-blocked holding. The backend emits a much smaller object for these —
 * no alloc/gain/lots/behavioral/data_completeness — which used to crash the
 * Decisions table because the UI read those fields unconditionally.
 */
export function noDecisionHolding(instrument = 'Bajaj Finance', ticker = 'BAJFINANCE'): Holding {
  return {
    instrument,
    ticker,
    bucket: 'large',
    decision: 'NO-DECISION',
    composite_score: null,
    confidence: null,
    confidence_breakdown: null,
    subscores: null,
    stage1: { fired: false, gates_fired: [], winning_gate: 'G0', tax_defer_suppressed: false },
    evidence: null,
    primary_drivers: ['G0: cost-basis reconciliation failed'],
    watch_flags: [],
    behavioral_flags: ['none'],
    trim: null,
    tax_status: null,
    reason_tree: { decision_path: 'G0 → NO-DECISION (reconciliation blocked)', stage1: {}, stage2: {} },
    why_now: { primary_trigger: 'data integrity', contributors: [] },
    previous_run: null,
    next_review_date: '2026-08-22',
  };
}

export function payload(holdings: Holding[]): DecisionPayload {
  return {
    run_id: 'run_20260822T000000_abc123',
    as_of: '2026-08-22',
    engine_version: '0.3.1-phase3',
    policy_version: 1,
    input_hash: 'inputhash',
    content_hash: 'contenthash',
    provenance: {
      engine_version: '0.3.1-phase3', normalization_version: '1.0',
      calculation_version: '2.1', policy_version: 1,
      sources: { portfolio: { as_of: '2026-08-22', days_behind: 0 } },
    },
    portfolio_summary: {
      total_value: 700000, holdings_count: holdings.length,
      decision_distribution: {}, stage1_gates_fired: 1, tax: {},
    },
    holdings,
    portfolio_layer: { action_queue: [], theme_concentration: [], tax_sequencing: [] },
    warnings: [],
  };
}
