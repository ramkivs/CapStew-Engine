import type { ReactNode } from 'react';
import type { Decision } from '../types';

export const DECISION_META: Record<string, { color: string; label: string }> = {
  HOLD: { color: '#34d399', label: 'HOLD' },
  WATCH: { color: '#fbbf24', label: 'WATCH' },
  TRIM: { color: '#fb923c', label: 'TRIM' },
  HARVEST: { color: '#a78bfa', label: 'HARVEST' },
  EXIT: { color: '#f87171', label: 'EXIT · THESIS BREAK' },
  'NO-DECISION': { color: '#94a3b8', label: 'NO-DECISION' },
};

export function Badge({ decision }: { decision: string }) {
  const m = DECISION_META[decision] ?? DECISION_META.HOLD;
  return (
    <span className="badge" style={{ color: m.color, background: `${m.color}18`, border: `1px solid ${m.color}44` }}>
      <span className="dot" style={{ background: m.color }} />
      {m.label}
    </span>
  );
}

export function Stat({ k, v, s }: { k: string; v: ReactNode; s?: ReactNode }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {s ? <div className="s">{s}</div> : null}
    </div>
  );
}

export function Bar({ value, color, width = '100%' }: { value: number; color: string; width?: string | number }) {
  return (
    <div className="bar" style={{ width }}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </div>
  );
}

export function Ring({ value, color }: { value: number; color: string }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <svg width="70" height="70" viewBox="0 0 70 70">
      <circle cx="35" cy="35" r={r} fill="none" stroke="#1a2337" strokeWidth="7" />
      <circle cx="35" cy="35" r={r} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
        strokeDasharray={`${(c * value) / 100} ${c}`} transform="rotate(-90 35 35)" />
      <text x="35" y="40" textAnchor="middle" fontSize="19" fontWeight="700" fill="#e6ecf7"
        fontFamily="ui-monospace, monospace">{value}</text>
    </svg>
  );
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={`chip ${className ?? ''}`}>{children}</span>;
}

export function TagChip({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="tagchip" style={{ color, background: `${color}1a`, border: `1px solid ${color}44` }}>
      {children}
    </span>
  );
}

export function Banner({ kind, children }: { kind: 'warn' | 'ok' | 'err'; children: ReactNode }) {
  return <div className={`banner ${kind}`}>{children}</div>;
}

export const inr = (n: number | null | undefined) =>
  '₹' + (n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
export const pct = (n: number | null | undefined) => (n == null ? '—' : `${n.toFixed(1)}%`);
export const num = (n: number | null | undefined, dp = 0) =>
  n == null ? '—' : n.toFixed(dp);
