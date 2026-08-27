import { api } from './client';
import type { ThemeDocument } from '../types';

// CR-023: read-only readout of the authority theme mapping document.
// There is deliberately no mutation surface (H2-D5-A / no theme editor).
export const themes = {
  current: () => api.get<ThemeDocument>('/api/v1/themes'),
};
