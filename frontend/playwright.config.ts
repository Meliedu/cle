import { defineConfig, devices } from '@playwright/test';

// Base URL is env-driven so the suite can target an already-running dev server
// on a non-default port (e.g. when :3000 is occupied). Defaults to :3000.
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:3000';
// When PW_NO_WEBSERVER=1 the caller manages the dev server (and backend/DB)
// themselves — Playwright just drives the browser against BASE_URL.
const MANAGE_WEBSERVER = process.env.PW_NO_WEBSERVER !== '1';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // The live-stack suite (MELI_LIVE_STACK=1) drives a single `next dev` server
  // that compiles each route on first hit; running its authenticated flows in
  // parallel thrashes that server and produces spurious navigation timeouts.
  // Serialize when live so the documented invocation is reliable; otherwise use
  // the default (parallel) for the lightweight infra-free suites.
  workers:
    process.env.CI || process.env.MELI_LIVE_STACK === '1' ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  ...(MANAGE_WEBSERVER
    ? {
        webServer: {
          command: 'npm run dev',
          url: BASE_URL,
          reuseExistingServer: !process.env.CI,
        },
      }
    : {}),
});
