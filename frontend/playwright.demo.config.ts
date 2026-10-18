import { randomBytes } from 'node:crypto';
import path from 'node:path';

import { defineConfig, devices } from '@playwright/test';

/**
 * The integrated demonstration: the real FastAPI + PostgreSQL stack with the scripted
 * assistant, search and speech providers, plus the curated reference pack published as
 * verified-source data (OSRIP_E2E_REFERENCE_PACK=1), in a throwaway database. Each step
 * asserts what it shows and saves a screenshot to docs/evidence/integrated/.
 *   $env:OSRIP_TEST_ADMIN_URL = (..\backend\.venv\Scripts\python.exe ..\backend\scripts\devdb.py url)
 *   $env:PW_CHANNEL = "msedge"; npx playwright test -c playwright.demo.config.ts
 */

const channel = process.env.PW_CHANNEL;
const backend = path.resolve(import.meta.dirname, '../backend');
const python =
  process.env.OSRIP_PYTHON ??
  path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

process.env.OSRIP_E2E_PASSWORD ??= `e2e-${randomBytes(18).toString('hex')}`;

const API_PORT = 8766;
const WEB_PORT = 5176;

export default defineConfig({
  testDir: './e2e-demo',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    channel,
    viewport: { width: 1440, height: 900 },
    // The fake speech provider's audio plays without a click.
    launchOptions: { args: ['--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] },
    storageState: {
      cookies: [],
      origins: [{ origin: `http://localhost:${WEB_PORT}`, localStorage: [{ name: 'osrip.intro.autoplay', value: 'off' }] }],
    },
  },
  webServer: [
    {
      command: `"${python}" scripts/serve_e2e.py`,
      cwd: backend,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        OSRIP_TEST_ADMIN_URL: process.env.OSRIP_TEST_ADMIN_URL ?? '',
        OSRIP_E2E_PASSWORD: process.env.OSRIP_E2E_PASSWORD,
        OSRIP_E2E_PORT: String(API_PORT),
        OSRIP_E2E_WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
        OSRIP_E2E_REFERENCE_PACK: '1',
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
        VITE_MAP_STYLE_URL: `http://localhost:${WEB_PORT}/__no_map_style__.json`,
      },
    },
  ],
  projects: [
    { name: 'desktop', grepInvert: /@phone/, use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, channel } },
    { name: 'phone', grep: /@phone/, use: { ...devices['Pixel 7'], channel } },
  ],
});
