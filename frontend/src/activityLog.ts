import { useSyncExternalStore } from 'react';

// Session-only activity log (diagnostics). Records event text only — file names,
// sizes and backend error detail — never CSV contents, never decisions derived
// in the browser. Not persisted anywhere.

export type LogLevel = 'info' | 'ok' | 'fail';

export interface LogEntry {
  ts: number;
  level: LogLevel;
  text: string;
}

const MAX_ENTRIES = 300;
let entries: LogEntry[] = [];
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function log(level: LogLevel, text: string): void {
  entries = [...entries, { ts: Date.now(), level, text }].slice(-MAX_ENTRIES);
  emit();
}

export function clearActivityLog(): void {
  entries = [];
  emit();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot(): LogEntry[] {
  return entries;
}

export function useActivityLog(): LogEntry[] {
  return useSyncExternalStore(subscribe, getSnapshot);
}
