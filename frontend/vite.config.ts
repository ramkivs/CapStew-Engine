/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server serves the SPA and proxies /api to the FastAPI engine (same machine).
// The browser only ever talks to this origin via relative /api paths — it never
// computes a decision and never calls a hardcoded host directly.
export default defineConfig({
  plugins: [react()],
  server: {
    // Single-user local app: bind loopback so the UI (and the /api proxy behind
    // it) is not reachable from other machines on the same network. Pass
    // `npx vite --host 0.0.0.0` explicitly if you really want to expose it.
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
