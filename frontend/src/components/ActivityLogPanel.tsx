import { useEffect, useRef } from 'react';
import { clearActivityLog, useActivityLog } from '../activityLog';

const ICON: Record<string, string> = { info: 'ℹ️', ok: '✅', fail: '⛔' };
const COLOR: Record<string, string> = {
  info: 'var(--muted)',
  ok: 'var(--green)',
  fail: 'var(--red)',
};

export function ActivityLogPanel() {
  const entries = useActivityLog();
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [entries.length]);

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3>
        Activity log <span className="tag">file load → import → run · diagnostics only</span>
      </h3>
      {entries.length === 0 ? (
        <div className="note">
          No activity yet. This panel records file selections, run requests, backend responses
          and structured import errors (file · line · column · token) as they happen in this
          session. Nothing here changes decisions — it is a trace, not a calculation.
        </div>
      ) : (
        <>
          <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 6 }}>
            {entries.map((e, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  gap: 8,
                  padding: '3px 0',
                  fontFamily: 'var(--mono)',
                  fontSize: 12,
                  color: COLOR[e.level],
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                }}
              >
                <span style={{ color: 'var(--dim)', flexShrink: 0 }}>
                  {new Date(e.ts).toLocaleTimeString('en-GB')}
                </span>
                <span style={{ flexShrink: 0 }}>{ICON[e.level]}</span>
                <span style={{ wordBreak: 'break-word' }}>{e.text}</span>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <div style={{ marginTop: 8 }}>
            <button className="btn" style={{ padding: '4px 12px' }} onClick={clearActivityLog}>
              ✕ clear log
            </button>
          </div>
        </>
      )}
    </div>
  );
}
