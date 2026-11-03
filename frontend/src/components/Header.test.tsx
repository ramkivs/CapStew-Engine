import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Header } from './Header';

// Branding regression guard: the application is CapitalCompass. The old product
// identity (CapStew / Capital Steward / "CS" mark) must not reappear in the app
// bar. Technical identifiers (repo name, API paths) are intentionally untouched
// elsewhere and are not asserted here.
function renderHeader() {
  return render(
    <Header view="inputs" onView={() => {}} engine="1.2.0" asOf="2026-08-22" running={false} />,
  );
}

describe('Header — CapitalCompass branding', () => {
  it('shows the CapitalCompass wordmark', () => {
    renderHeader();
    expect(screen.getByText('CapitalCompass')).toBeInTheDocument();
  });

  it('uses the CC logo mark, not the old CS mark', () => {
    const { container } = renderHeader();
    const mark = container.querySelector('.logo .mark');
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toBe('CC');
  });

  it('does not render any old product branding', () => {
    const { container } = renderHeader();
    const text = container.textContent ?? '';
    expect(text).not.toMatch(/CapStew/i);
    expect(text).not.toMatch(/Capital Steward/i);
  });

  it('keeps the navigation labels and advisory chip unchanged', () => {
    renderHeader();
    expect(screen.getByText('Inputs & Policy')).toBeInTheDocument();
    expect(screen.getByText('Decisions')).toBeInTheDocument();
    expect(screen.getByText('Weights & Thresholds')).toBeInTheDocument();
    expect(screen.getByText('Tax-Year Tracker')).toBeInTheDocument();
    expect(screen.getByText('Run History')).toBeInTheDocument();
    expect(screen.getByText(/ADVISORY MODE/)).toBeInTheDocument();
  });
});
