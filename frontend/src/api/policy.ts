import { api } from './client';
import type { Policy } from '../types';

export const policy = {
  get: () => api.get<Policy>('/api/v1/policy'),
  put: (body: Record<string, unknown>) => api.put<Policy>('/api/v1/policy', body),
};
