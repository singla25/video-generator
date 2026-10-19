import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const BACKEND = 'http://127.0.0.1:8000';
const PROXIED = ['/auth', '/templates', '/batches', '/stats', '/audit', '/health'];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin in dev: the browser only ever talks to the Vite server.
    proxy: Object.fromEntries(PROXIED.map((p) => [p, { target: BACKEND, changeOrigin: false }])),
  },
  test: {
    environment: 'jsdom',
    include: ['../tests/frontend/unit/**/*.test.{ts,tsx}'],
    setupFiles: ['../tests/frontend/setup.ts'],
    css: false,
    coverage: { provider: 'v8', include: ['src/**'], reporter: ['text', 'html'] },
  },
});
