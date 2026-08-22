import { api } from './client';
import type { RunListItem, RunDiff } from '../types';

export const history = {
  runs: () => api.get<RunListItem[]>('/api/v1/runs'),
  diff: (runId: string) => api.get<RunDiff>(`/api/v1/runs/${encodeURIComponent(runId)}/diff`),
};
