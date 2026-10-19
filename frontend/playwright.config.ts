import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173';

export default defineConfig({
  testDir: '../tests/frontend/e2e',
  use: { baseURL },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    {
      name: 'reduced-motion',
      use: { ...devices['Desktop Chrome'], reducedMotion: 'reduce' },
    },
    {
      name: 'tablet',
      use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } },
    },
  ],
  // Started only when E2E_START_SERVER is set; otherwise assume a running server.
  webServer: process.env.E2E_START_SERVER
    ? { command: 'npm run dev -- --host 127.0.0.1', url: baseURL, reuseExistingServer: true }
    : undefined,
});
