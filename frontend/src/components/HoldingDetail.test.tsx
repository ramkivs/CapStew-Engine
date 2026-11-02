import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HoldingDetail } from './HoldingDetail';
import { noDecisionHolding, scoredHolding } from '../test/fixture';

const noop = () => {};

describe('HoldingDetail', () => {
  it('renders nothing when no holding is selected', () => {
    const { container } = render(<HoldingDetail holding={null} onClose={noop} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a scored holding: subscores, lots, tax status', () => {
    render(<HoldingDetail holding={scoredHolding()} onClose={noop} />);
    expect(screen.getByText('SALASAR')).toBeInTheDocument();
    // the six Stage-2 categories come from the backend payload, not the browser
    expect(screen.getByText('Position sizing')).toBeInTheDocument();
    expect(screen.getByText('Opportunity cost (PEG proxy)')).toBeInTheDocument();
    // FIFO lot table renders the backend lot rows
    expect(screen.getAllByText('#1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-04-23').length).toBeGreaterThan(0);
  });

  it('renders a NO-DECISION holding without crashing (regression)', () => {
    // This is the exact shape the backend returns for a G0-blocked instrument:
    // subscores, behavioral, data_completeness, data_quality and lots are all
    // absent. Reading any of them unguarded threw and blanked the panel.
    render(<HoldingDetail holding={noDecisionHolding()} onClose={noop} />);
    expect(screen.getByText('BAJFINANCE')).toBeInTheDocument();
  });

  it('shows why a NO-DECISION holding has no decision', () => {
    render(<HoldingDetail holding={noDecisionHolding()} onClose={noop} />);
    const hits = screen.getAllByText(/G0 → NO-DECISION \(reconciliation blocked\)/);
    expect(hits.length).toBeGreaterThan(0);
  });

  it('does not fabricate scores for a blocked holding', () => {
    render(<HoldingDetail holding={noDecisionHolding()} onClose={noop} />);
    // no composite value is invented for a holding that was never scored
    expect(screen.queryByText('65.2')).not.toBeInTheDocument();
  });

  it('calls onClose when dismissed', () => {
    const onClose = vi.fn();
    render(<HoldingDetail holding={scoredHolding()} onClose={onClose} />);
    screen.getByRole('button', { name: '✕' }).click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
