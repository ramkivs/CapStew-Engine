import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server serves the SPA and proxies /api to the FastAPI engine (same sandbox).
// The browser only ever talks to this origin via relative /api paths — it never
// computes a decision and never calls localhost directly.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
