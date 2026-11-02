import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WeightsView } from './WeightsView';
import type { Policy } from '../types';

/** A policy whose weights total exactly 100, as D-09 requires. */
const POLICY: Policy = {
  policy_version: 3,
  weights: {
    position_sizing: 25, valuation_stretch: 25, quality_drift: 20,
    tax_efficiency: 15, opportunity_cost: 10, technical_regime: 5,
  },
  max_single_stock_pct: 10,
  rebalance_trigger_multiple: 1.5,
  pledge_threshold_pct: 10,
  quality_floor: 40,
  ltcg_defer_window_days: 30,
  valuation_extreme_suppress: 85,
  bands: { hold_max: 30, watch_max: 55, trim_max: 75 },
  participation_position_pct: 25,
  txn_cost_liquid_pct: 0.35,
  txn_cost_microcap_pct: 1.0,
};

function renderView(onCommit = vi.fn(async () => {}), onWhatIf = vi.fn()) {
  render(
    <WeightsView policy={POLICY} previewActive={false} onWhatIf={onWhatIf} onCommit={onCommit} />,
  );
  return { onCommit, onWhatIf };
}

// The range inputs carry no accessible name (the caption is a sibling <div>),
// so select them by the order WEIGHT_LABELS is rendered in. This keeps the test
// honest about the current markup instead of requiring an app change.
const ORDER = ['position_sizing', 'valuation_stretch', 'quality_drift',
               'tax_efficiency', 'opportunity_cost', 'technical_regime'];

function slider(key: string): HTMLInputElement {
  const all = document.querySelectorAll('input[type="range"]');
  expect(all).toHaveLength(ORDER.length);
  return all[ORDER.indexOf(key)] as HTMLInputElement;
}

afterEach(() => { vi.useRealTimers(); });

describe('WeightsView — D-09 weight validation', () => {
  it('starts at the policy total of 100', () => {
    renderView();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText(/must equal 100/)).toBeInTheDocument();
  });

  it('BLOCKS commit when the total is 99 and never calls the API', async () => {
    const user = userEvent.setup();
    const { onCommit } = renderView();

    // Drop one category by a point: 100 -> 99.
    fireEvent.change(slider('technical_regime'), { target: { value: '4' } });
    expect(screen.getByText('99%')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /commit policy/i }));

    expect(screen.getByText(/weights must total 100 \(currently 99\)/)).toBeInTheDocument();
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('ACCEPTS commit when the total is exactly 100', async () => {
    const user = userEvent.setup();
    const { onCommit } = renderView();

    await user.click(screen.getByRole('button', { name: /commit policy/i }));

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(POLICY.weights);
    expect(screen.getByText(/policy v4 committed/)).toBeInTheDocument();
  });

  it('accepts a re-balanced 100 (move a point between categories)', async () => {
    const user = userEvent.setup();
    const { onCommit } = renderView();

    fireEvent.change(slider('technical_regime'), { target: { value: '4' } });   // 99
    fireEvent.change(slider('position_sizing'), { target: { value: '26' } });   // back to 100
    expect(screen.getByText('100%')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /commit policy/i }));
    expect(onCommit).toHaveBeenCalledWith({ ...POLICY.weights, technical_regime: 4, position_sizing: 26 });
  });

  it('blocks a total above 100 as well as below', async () => {
    const user = userEvent.setup();
    const { onCommit } = renderView();

    fireEvent.change(slider('technical_regime'), { target: { value: '6' } });   // 101
    expect(screen.getByText('101%')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /commit policy/i }));
    expect(screen.getByText(/currently 101/)).toBeInTheDocument();
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('debounces the preview call — dragging alone never persists', () => {
    vi.useFakeTimers();
    const { onWhatIf, onCommit } = renderView();

    act(() => { fireEvent.change(slider('position_sizing'), { target: { value: '30' } }); });
    expect(onWhatIf).not.toHaveBeenCalled();      // not yet — still inside the debounce

    act(() => { vi.advanceTimersByTime(350); });
    expect(onWhatIf).toHaveBeenCalledTimes(1);    // server-side /what-if preview only
    expect(onCommit).not.toHaveBeenCalled();      // and never a commit
  });
});
