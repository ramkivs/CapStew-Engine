export type Decision = 'HOLD' | 'WATCH' | 'TRIM' | 'HARVEST' | 'EXIT' | 'NO-DECISION';

export interface SubScores {
  position_sizing: number | null;
  valuation_stretch: number | null;
  quality_drift: number | null;
  tax_efficiency: number | null;
  opportunity_cost: number | null;
  technical_regime: number | null;
}

export interface Stage1 {
  fired: boolean;
  gates_fired: string[];
  winning_gate: string | null;
  tax_defer_suppressed: boolean;
}

export interface Evidence {
  coverage: number;
  tier: string;
  missing_weight: number;
  critical_categories_missing: string[];
}

export interface Lot {
  lot_id: number;
  instrument: string;
  ticker: string | null;
  trade_date: string;
  qty: number;
  buy_price: number;
  ltp: number;
  invested: number | null;
  value: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  days_held: number;
  days_to_ltcg: number;
  ltcg_eligible: boolean;
}

export interface Trim {
  mode: 'S' | 'V';
  suggested_qty: number | null;
  suggested_value: number | null;
  fifo_lots_to_sell: { lot_id: number; qty: number }[];
  tax_breakdown: {
    stcg_gain: number; ltcg_gain: number; stcg_tax: number; ltcg_tax: number; realized_loss: number;
  };
  est_transaction_cost: number;
  alloc_after_pct?: number;
  target_alloc_pct?: number;
  participation_capped?: boolean;
  rho?: number;
}

export interface Holding {
  instrument: string;
  ticker: string | null;
  bucket: string | null;
  alloc_pct: number | null;
  gain_pct: number | null;
  current_value: number | null;
  qty_held: number | null;
  pledge_pct: number | null;
  decision: Decision;
  composite_score: number | null;
  confidence: number | null;
  confidence_breakdown: Record<string, number> | null;
  subscores: SubScores;
  stage1: Stage1;
  evidence: Evidence | null;
  primary_drivers: string[];
  watch_flags: string[];
  behavioral_flags: string[];
  behavioral: { flag: string; requires_reunderwrite: boolean; blocks_adds: boolean };
  trim: Trim | null;
  tax_status: {
    mixed_ltcg: boolean;
    oldest_lot_days_to_ltcg: number | null;
    ltcg_eligible_lots: number;
  } | null;
  data_completeness: Record<string, boolean>;
  data_quality: Record<string, string>;
  lots: Lot[];
  reason_tree: { decision_path: string; stage1: Record<string, unknown>; stage2: Record<string, unknown> };
  why_now: { primary_trigger: string; contributors: { label: string; value: number; weight: number }[] };
  previous_run: { decision: string; composite_score: number | null; as_of: string } | null;
  next_review_date: string | null;
}

export interface ActionQueueItem {
  rank: number; instrument: string; decision: string; reason: string; score: number | null;
}

export interface TaxYear {
  realized: { instrument: string; lot_id: number; sell_date: string; qty: number;
    buy_price: number; sell_price: number; gain: number; holding_days: number; type: string }[];
  summary: {
    fy: string | null;
    gross: Record<string, number>;
    set_off: Record<string, number>;
    net: Record<string, number>;
    exemption: { used: number; headroom: number };
    taxable: Record<string, number>;
    tax: Record<string, number>;
    carry_forward_out: { ltcl: [number, number][]; stcl: [number, number][] };
  };
  open_positions: Record<string, Record<string, number>>;
}

export interface DecisionPayload {
  run_id: string;
  as_of: string;
  engine_version: string;
  policy_version: number;
  input_hash: string;
  content_hash: string;
  provenance: {
    engine_version: string; normalization_version: string; calculation_version: string;
    policy_version: number; sources: Record<string, { as_of: string; days_behind: number }>;
  };
  portfolio_summary: {
    total_value: number; holdings_count: number;
    decision_distribution: Record<string, number>; stage1_gates_fired: number;
    tax: Record<string, unknown>;
  };
  holdings: Holding[];
  portfolio_layer: {
    action_queue: ActionQueueItem[];
    theme_concentration: { theme: string; alloc_pct: number; status: string }[];
    tax_sequencing: { instrument: string; decision: string; ltcg_gain: number; stcg_gain: number; est_tax_if_realised: number }[];
  };
  tax_year?: TaxYear;
  warnings: { code: string; instrument: string | null; message: string }[];
}

export interface RunListItem {
  run_id: string; as_of: string; engine_version: string; policy_version: number;
  input_hash: string; content_hash: string; created_at: string;
}

export interface RunDiff {
  run_id: string;
  previous_run_id: string | null;
  note?: string;
  as_of?: { from: string; to: string };
  changed: {
    instrument: string; status: 'changed' | 'added';
    decision?: { from: string; to: string }; score?: { from: number | null; to: number | null };
    gate?: { from: string | null; to: string | null };
  }[];
  removed_holdings: string[];
  distribution?: { from: Record<string, number>; to: Record<string, number> };
}

export interface Policy {
  policy_version: number;
  weights: Record<string, number>;
  max_single_stock_pct: number;
  rebalance_trigger_multiple: number;
  pledge_threshold_pct: number;
  quality_floor: number;
  ltcg_defer_window_days: number;
  valuation_extreme_suppress: number;
  bands: { hold_max: number; watch_max: number; trim_max: number };
  participation_position_pct: number;
  txn_cost_liquid_pct: number;
  txn_cost_microcap_pct: number;
  [k: string]: unknown;
}
