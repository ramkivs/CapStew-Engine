import { api } from './client';
import type { DecisionPayload, Holding } from '../types';

// Authoritative engine adapter — the browser NEVER computes a decision; it renders
// whatever these endpoints return.
export const engine = {
  health: () => api.get<{ status: string; engine_version: string; phase: string }>('/api/v1/health'),
  runSample: () => api.post<DecisionPayload>('/api/v1/run-sample'),
  run: (form: FormData) => api.postForm<DecisionPayload>('/api/v1/run', form),
  whatIf: (policyOverrides: Record<string, unknown>) =>
    api.post<DecisionPayload>('/api/v1/what-if', { policy_overrides: policyOverrides }),
  decisions: () => api.get<DecisionPayload>('/api/v1/decisions'),
  holding: (instrument: string) =>
    api.get<Holding>(`/api/v1/holdings/${encodeURIComponent(instrument)}`),
};
