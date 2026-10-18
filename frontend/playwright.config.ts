import { defineConfig, devices } from '@playwright/test';

// Mock-mode interface tests (no backend). They always start their own Vite server
// on a dedicated port in mock mode, so a developer's dev server (which defaults
// to the real API) is never reused by mistake.
// PW_CHANNEL=msedge (or chrome) runs against an installed browser instead of the
// downloaded Playwright Chromium, e.g. on machines without `playwright install`.
const channel = process.env.PW_CHANNEL;
const PORT = 5175;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    // The introduction is switched off (the Settings choice); e2e/entrance.spec.ts starts from a clean browser.
    storageState: {
      cookies: [],
      origins: [{ origin: `http://localhost:${PORT}`, localStorage: [{ name: 'osrip.intro.autoplay', value: 'off' }] }],
    },
  },
  webServer: {
    command: 'npm run dev',
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
    env: { VITE_DATA_ADAPTER: 'mock', OSRIP_WEB_PORT: String(PORT) },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel }, grep: /@mobile/ },
  ],
});
