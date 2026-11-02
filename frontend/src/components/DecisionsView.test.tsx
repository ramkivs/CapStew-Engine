import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DecisionsView } from './DecisionsView';
import { noDecisionHolding, payload, scoredHolding } from '../test/fixture';

const noop = () => {};

function renderView(holdings: ReturnType<typeof scoredHolding>[]) {
  return render(
    <DecisionsView payload={payload(holdings)} preview={null} onSelect={noop} onClearPreview={noop} />,
  );
}

describe('DecisionsView — holdings table', () => {
  it('renders every holding from the authoritative payload', () => {
    renderView([
      scoredHolding({ instrument: 'Salasar Techno Engg', ticker: 'SALASAR' }),
      scoredHolding({ instrument: 'Ashoka Buildcon', ticker: 'ASHOKA', decision: 'EXIT', composite_score: 21.4 }),
    ]);
    expect(screen.getByText('SALASAR')).toBeInTheDocument();
    expect(screen.getByText('ASHOKA')).toBeInTheDocument();
  });

  it('renders a NO-DECISION holding without crashing (regression: UI used to throw)', () => {
    // This is the exact shape the backend returns for a G0-blocked instrument:
    // no alloc_pct / gain_pct / lots / behavioral / data_completeness.
    renderView([scoredHolding(), noDecisionHolding()]);
    expect(screen.getByText('BAJFINANCE')).toBeInTheDocument();
    // blocked rows show an em dash rather than a fabricated number
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('sorts by composite ascending, then descending, then back to payload order', async () => {
    const user = userEvent.setup();
    renderView([
      scoredHolding({ instrument: 'A', ticker: 'AAA', composite_score: 80 }),
      scoredHolding({ instrument: 'B', ticker: 'BBB', composite_score: 20 }),
      scoredHolding({ instrument: 'C', ticker: 'CCC', composite_score: 50 }),
    ]);

    const tickers = () =>
      screen.getAllByRole('row').slice(1).map((r) => r.querySelector('td')?.textContent?.replace(/[^\w]/g, '') ?? '');

    expect(tickers()).toEqual(['AAA', 'BBB', 'CCC']); // backend order preserved by default

    const header = screen.getByRole('button', { name: /sort by composite/i });
    await user.click(header);
    expect(tickers()).toEqual(['BBB', 'CCC', 'AAA']); // asc

    await user.click(header);
    expect(tickers()).toEqual(['AAA', 'CCC', 'BBB']); // desc

    await user.click(header);
    expect(tickers()).toEqual(['AAA', 'BBB', 'CCC']); // none → payload order
  });

  it('keeps NO-DECISION rows last when sorting numerically', async () => {
    const user = userEvent.setup();
    renderView([noDecisionHolding(), scoredHolding({ instrument: 'A', ticker: 'AAA', composite_score: 80 })]);

    await user.click(screen.getByRole('button', { name: /sort by composite/i }));
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows[rows.length - 1].textContent).toContain('BAJFINANCE');
  });

  it('offers the payload export controls', () => {
    renderView([scoredHolding()]);
    expect(screen.getByRole('button', { name: 'Decisions JSON' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Decisions CSV' })).toBeInTheDocument();
  });
});
