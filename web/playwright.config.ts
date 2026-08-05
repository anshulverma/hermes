import { defineConfig, devices } from '@playwright/test';

/**
 * Real-browser UI tests.
 *
 * These exist for the things jsdom structurally cannot answer: scrolling,
 * overscroll, stacking and spacing all need a layout engine. jsdom has none, so
 * a passing vitest suite says nothing about them.
 *
 * The target is the DEPLOYED control plane, not a dev server -- that way the
 * tests exercise the same bundle the browser actually serves. Run `make deploy`
 * first. Point elsewhere with HERMES_URL.
 */
const URL = process.env.HERMES_URL || 'http://127.0.0.1:44102';

export default defineConfig({
  testDir: './tests-ui',
  // Layout assertions are measurements, not races: a retry that "fixes" one is
  // hiding a real flake.
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: URL,
    viewport: { width: 1440, height: 900 },
    // Deterministic pixels across runs: no animation mid-screenshot.
    launchOptions: { args: ['--force-color-profile=srgb'] },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
