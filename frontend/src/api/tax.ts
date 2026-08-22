import { api } from './client';
import type { TaxYear } from '../types';

// Render-only: the browser displays tax numbers, never calculates them.
export const tax = {
  tracker: () => api.get<TaxYear>('/api/v1/tax-tracker'),
};
