import { Chip } from './ui';

export type ViewId = 'inputs' | 'decisions' | 'weights' | 'tax' | 'history';

const TABS: { id: ViewId; n: string; label: string }[] = [
  { id: 'inputs', n: '01', label: 'Inputs & Policy' },
  { id: 'decisions', n: '02', label: 'Decisions' },
  { id: 'weights', n: '03', label: 'Weights & Thresholds' },
  { id: 'tax', n: '04', label: 'Tax-Year Tracker' },
  { id: 'history', n: '05', label: 'Run History' },
];

export function Header({ view, onView, engine, asOf, running }: {
  view: ViewId;
  onView: (v: ViewId) => void;
  engine: string | null;
  asOf: string | null;
  running: boolean;
}) {
  return (
    <>
      <header className="appbar">
        <div className="logo">
          <div className="mark">CS</div>
          <div>
            <b>Capital Steward Engine</b>
            <br />
            <small>Portfolio discipline · valuation · tax · risk</small>
          </div>
        </div>
        <div className="spacer" />
        {asOf ? <Chip>as-of <b style={{ color: 'var(--text)' }}>{asOf}</b></Chip> : null}
        <Chip className="warn">⚠ ADVISORY MODE — Stage 2 never auto-executes</Chip>
        <Chip className="ok">{engine ? `● Engine ${engine}` : running ? '● running…' : '○ idle'}</Chip>
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <div key={t.id} className={`tab ${view === t.id ? 'active' : ''}`}
            onClick={() => onView(t.id)} role="tab">
            <span className="n">{t.n}</span>{t.label}
          </div>
        ))}
      </nav>
    </>
  );
}
