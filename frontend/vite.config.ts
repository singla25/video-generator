import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

import { API_PREFIX } from './src/config';

const BACKEND = 'http://127.0.0.1:8000';
const PROXIED = [API_PREFIX];

const FRONTEND_DIR = path.dirname(fileURLToPath(import.meta.url));
const TESTS_DIR = path.resolve(FRONTEND_DIR, '../tests/frontend');

/**
 * Bare imports from tests/frontend (outside this package) are resolved as if
 * they came from frontend/, so tests share frontend/node_modules without a symlink.
 */
function resolveTestDepsFromFrontend(): Plugin {
  return {
    name: 'resolve-tests-deps-from-frontend',
    enforce: 'pre',
    async resolveId(source, importer, options) {
      const isBare = !/^([./]|[a-zA-Z]:|\0|virtual:)/.test(source);
      if (!isBare || !importer || !path.resolve(importer).startsWith(TESTS_DIR + path.sep)) {
        return null;
      }
      return this.resolve(source, path.join(FRONTEND_DIR, 'package.json'), {
        ...options,
        skipSelf: true,
      });
    },
  };
}

export default defineConfig({
  plugins: [resolveTestDepsFromFrontend(), react(), tailwindcss()],
  server: {
    // Same-origin in dev: the browser only ever talks to the Vite server.
    proxy: Object.fromEntries(PROXIED.map((p) => [p, { target: BACKEND, changeOrigin: false }])),
    // Narrow allow-list instead of fs.strict: false.
    fs: { allow: [FRONTEND_DIR, TESTS_DIR] },
  },
  test: {
    environment: 'jsdom',
    include: ['../tests/frontend/unit/**/*.test.{ts,tsx}'],
    setupFiles: ['../tests/frontend/setup.ts', './test-support/xhr-formdata.ts'],
    css: false,
    coverage: { provider: 'v8', include: ['src/**'], reporter: ['text', 'html'] },
  },
});
