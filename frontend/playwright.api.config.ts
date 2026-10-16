import { randomBytes } from 'node:crypto';
import path from 'node:path';

import { defineConfig, devices } from '@playwright/test';

/**
 * Full-stack tests: real FastAPI + PostgreSQL behind the Vite proxy, frontend in
 * http-adapter mode. Requires OSRIP_TEST_ADMIN_URL (a PostgreSQL superuser URL,
 * e.g. from `python scripts/devdb.py url` in backend/).
 *   PW_CHANNEL=msedge npx playwright test -c playwright.api.config.ts
 */

const channel = process.env.PW_CHANNEL;
const backend = path.resolve(import.meta.dirname, '../backend');
const python =
  process.env.OSRIP_PYTHON ??
  path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

// One random password per run for the throwaway test accounts; never stored.
process.env.OSRIP_E2E_PASSWORD ??= `e2e-${randomBytes(18).toString('hex')}`;

const API_PORT = 8765;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: './e2e-api',
  fullyParallel: false, // the tests share one seeded database
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    channel,
    // The first-visit entrance counts as seen (it is tested in the mock suite).
    storageState: {
      cookies: [],
      origins: [{ origin: `http://localhost:${WEB_PORT}`, localStorage: [{ name: 'osrip.entrance', value: 'seen-1' }] }],
    },
  },
  webServer: [
    {
      command: `"${python}" scripts/serve_e2e.py`,
      cwd: backend,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        OSRIP_TEST_ADMIN_URL: process.env.OSRIP_TEST_ADMIN_URL ?? '',
        OSRIP_E2E_PASSWORD: process.env.OSRIP_E2E_PASSWORD,
        OSRIP_E2E_PORT: String(API_PORT),
        OSRIP_E2E_WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
      },
    },
    {
      command: 'npm run dev',
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      env: {
        VITE_DATA_ADAPTER: 'http',
        VITE_API_BASE_URL: '/api/v1',
        OSRIP_API_ORIGIN: `http://127.0.0.1:${API_PORT}`,
        OSRIP_WEB_PORT: String(WEB_PORT),
        // Not a map style: no external tile requests, and the "map unavailable" path is exercised.
        VITE_MAP_STYLE_URL: `http://localhost:${WEB_PORT}/__no_map_style__.json`,
      },
    },
  ],
  projects: [
    // Phone-sized checks (layout, Arabic labels, keyboard, errors) on the same stack.
    // Listed first so they run before the zz* specs, which add monthly synthetic data
    // that makes some sections mixed-frequency.
    { name: 'mobile', testMatch: /(quality|assistant|phone|workspace-phone|research-brief)\.spec\.ts/, use: { ...devices['Pixel 7'], channel } },
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel } },
  ],
});
