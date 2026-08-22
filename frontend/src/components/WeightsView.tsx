import { useEffect, useRef, useState } from 'react';
import type { Policy } from '../types';
import { Banner } from './ui';

const WEIGHT_LABELS: Record<string, string> = {
  position_sizing: 'Position sizing / concentration',
  valuation_stretch: 'Valuation stretch',
  quality_drift: 'Fundamental / quality drift',
  tax_efficiency: 'Tax efficiency',
  opportunity_cost: 'Opportunity cost',
  technical_regime: 'Technical / regime overlay',
};

export function WeightsView({ policy, previewActive, onWhatIf, onCommit }: {
  policy: Policy | null;
  previewActive: boolean;
  onWhatIf: (weights: Record<string, number>) => void;
  onCommit: (weights: Record<string, number>) => Promise<void>;
}) {
  const [weights, setWeights] = useState<Record<string, number>>(policy?.weights ?? {});
  const [committed, setCommitted] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (policy) setWeights(policy.weights);
  }, [policy]);

  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  function change(key: string, v: number) {
    const next = { ...weights, [key]: v };
    setWeights(next);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => onWhatIf(next), 350); // debounced /what-if
  }

  async function commit() {
    await onCommit(weights);
    setCommitted(`policy v${(policy?.policy_version ?? 0) + 1} committed`);
  }

  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Category weights <span className="tag">Stage 2 composite</span></h3>
        {previewActive ? (
          <Banner kind="warn"><b>Preview — not authoritative.</b> The browser never computes decisions;
            each change re-runs the engine server-side via /what-if.</Banner>
        ) : null}
        {Object.entries(WEIGHT_LABELS).map(([k, label]) => (
          <div key={k} className="cfg">
            <div className="lbl" style={{ minWidth: 220 }}><b>{label}</b></div>
            <input type="range" min={0} max={50} step={1} value={weights[k] ?? 0}
              onChange={(e) => change(k, Number(e.target.value))} aria-valuenow={weights[k] ?? 0} />
            <div className="val" id={`w-${k}`}>{weights[k] ?? 0}%</div>
          </div>
        ))}
        <div className="cfg" style={{ borderBottom: 'none', marginTop: 6 }}>
          <div className="lbl"><b>Total</b><small>must sum &gt; 0</small></div>
          <div className="bar"><i style={{ width: `${Math.min(total, 100)}%`, background: total > 0 ? 'var(--green)' : 'var(--red)' }} /></div>
          <div className="val" style={{ color: total > 0 ? 'var(--green)' : 'var(--red)' }}>{total}%</div>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
          <button className="btn primary" onClick={commit}>Commit policy</button>
          {committed ? <span className="note" style={{ color: 'var(--green)' }}>{committed}</span> : null}
        </div>
        <div className="note" style={{ marginTop: 10 }}>
          Dragging alone never persists — only <b>Commit policy</b> writes a new version.
        </div>
      </div>

      <div className="card">
        <h3>Thresholds & gates <span className="tag">D-01…D-15</span></h3>
        {policy ? (
          <>
            <T label="Composite bands" value={`0-${policy.bands.hold_max} / ${policy.bands.hold_max + 1}-${policy.bands.watch_max} / ${policy.bands.watch_max + 1}-${policy.bands.trim_max} / ${policy.bands.trim_max + 1}+`} />
            <T label="Max single-stock cap (G2)" value={`${policy.max_single_stock_pct}%`} />
            <T label="Rebalance trigger" value={`${policy.rebalance_trigger_multiple}× band mid`} />
            <T label="Quality floor (G1)" value={`${policy.quality_floor}/100`} />
            <T label="Pledge spike (G1)" value={`${policy.pledge_threshold_pct}%`} />
            <T label="LTCG defer window (G3)" value={`${policy.ltcg_defer_window_days}d`} />
            <T label="Valuation-extreme suppress" value={`${policy.valuation_extreme_suppress}`} />
            <T label="Participation cap (ADV unknown)" value={`${policy.participation_position_pct}%`} />
            <T label="Txn cost (liquid / micro)" value={`${policy.txn_cost_liquid_pct}% / ${policy.txn_cost_microcap_pct}%`} />
          </>
        ) : <div className="note">Policy not loaded.</div>}
        <div className="note" style={{ marginTop: 10 }}>
          Versioned in <span className="kbd">policy.yaml</span> — operational serialization of Freeze §14.
        </div>
      </div>
    </div>
  );
}

function T({ label, value }: { label: string; value: string }) {
  return (
    <div className="cfg">
      <div className="lbl"><b>{label}</b></div>
      <div></div>
      <div className="val">{value}</div>
    </div>
  );
}
