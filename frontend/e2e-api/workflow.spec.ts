import { expect, test, type Page } from '@playwright/test';

import { showResults } from './sector';

// Full stack: browser -> Vite proxy -> FastAPI -> PostgreSQL. The database was
// seeded with the booklet's SYNTHETIC fixtures through the import workflow.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('the published synthetic fixture is served by the API and shown in the interface', async ({ page }) => {
  // The selectors are filled from the availability the API reports, before any figure is read.
  const availability = page.waitForResponse((r) => r.url().includes('/api/v1/series/availability') && r.ok());
  await page.goto('/energy/electricity?mode=synthetic');
  const body = await (await availability).json();
  const generation = body.indicators.find((i: { code: string }) => i.code === 'ELEC_GENERATION');
  expect(generation.series[0].views.annual.map((p: { start: string }) => p.start)).toEqual(['2001-01-01', '2002-01-01']);
  await expect(page.getByTestId('sector-results')).toHaveCount(0); // nothing before Show results

  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  const rows = page.getByTestId('series-row');
  await expect(rows.locator('td').first()).toHaveText('48,000');
  await expect(rows.nth(1).locator('td').first()).toHaveText('50,100');
  await expect(page.getByTestId('data-mode-banner')).toHaveAttribute('data-mode', 'synthetic');
  await expect(page.getByTestId('prototype-notice')).toHaveCount(0); // the API address is under Settings › Services
  await expect(page.getByTestId('series-sources')).toContainText('OSRIP booklet worked-example fixtures (synthetic)');
  const evidence = page.getByTestId('insight-evidence');
  await evidence.locator('summary').click();
  await expect(evidence).toContainText('fixtures-v1');
});

test('verified-source mode never falls back to the synthetic fixture', async ({ page }) => {
  await page.goto('/energy/electricity');
  await expect(page.locator('[data-state="no_verified_data"]')).toBeVisible();
  await expect(page.getByTestId('sector-form')).toHaveCount(0);
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
});

test('Arabic shows the same API values', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  await showResults(page, { indicator: 'WATER_CONSUMPTION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  const values = page.getByTestId('series-row').locator('td:first-of-type');
  await expect(values).toHaveText(['330', '343']);
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(values).toHaveText(['330', '343']);
  await expect(page.getByTestId('sector-show-results')).toHaveText('عرض النتائج');
});

test('a data manager uploads, maps, validates, reviews, approves and publishes a CSV', async ({ page }) => {
  await signIn(page, 'manager@e2e.invalid');
  await page.goto('/data-management');

  // Register a synthetic source.
  await page.getByRole('button', { name: 'Register a source' }).click();
  const form = page.getByTestId('register-source-form');
  await form.getByLabel('Dataset title').fill('E2E synthetic water file');
  await form.getByRole('button', { name: 'Register source' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'E2E synthetic water file' })).toBeVisible();

  // Upload a file with one valid row and one row in the wrong unit.
  const csv = [
    'indicator_code,area_code,period_start,period_end,frequency,unit_code,value',
    'WATER_PRODUCTION,OM,2009-01-01,2009-12-31,annual,million_m3,412.5',
    'WATER_PRODUCTION,OM,2010-01-01,2010-12-31,annual,GWh,400',
  ].join('\n');
  const upload = page.getByTestId('upload-form');
  await upload.getByTestId('upload-source').selectOption({ label: 'E2E synthetic water file' });
  await upload.getByTestId('upload-label').fill('e2e-v1');
  await upload.getByTestId('upload-file').setInputFiles({
    name: 'e2e-water.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8'),
  });
  await upload.getByRole('button', { name: 'Upload privately' }).click();

  // Mapping was suggested from the header; validate.
  const detail = page.getByTestId('import-detail');
  await expect(detail.getByTestId('import-status')).toHaveText('Draft');
  await detail.getByTestId('validate-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Validated');
  await expect(detail.locator('[data-count="valid"] dd')).toHaveText('1');
  await expect(detail.locator('[data-count="rejected"] dd')).toHaveText('1');

  // Error preview names the row, the original value and the reason.
  const preview = detail.getByTestId('error-preview');
  await expect(preview).toContainText('3');
  await expect(preview).toContainText('GWh');
  await expect(preview).toContainText('unit_incompatible');

  // Explicit approval, then publication.
  await expect(detail.getByTestId('approve-button')).toBeDisabled();
  await detail.getByTestId('approve-ack').check();
  await detail.getByTestId('approve-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Approved');
  await detail.getByTestId('publish-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Published');
  await expect(detail.getByTestId('published-note')).toContainText('1 observations are now public');

  // The new value appears on the public sector page; the rejected row (2010) does not.
  await page.goto('/energy/water?mode=synthetic');
  await page.getByTestId('sector-indicator').selectOption('WATER_PRODUCTION');
  await page.getByTestId('sector-frequency').locator('[data-value="annual"]').click();
  await expect(page.getByTestId('sector-from').locator('option[value="2010-01-01"]')).toHaveCount(0);
  await showResults(page, { view: 'annual', from: '2009-01-01', to: '2009-01-01' });
  await expect(page.getByTestId('series-row').locator('td').first()).toHaveText('412.5');
});

test('a viewer is refused by the server even when calling the API directly', async ({ page }) => {
  await signIn(page, 'viewer@e2e.invalid');
  await page.goto('/data-management');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();

  // Bypass the interface: a hand-made request with a valid session and CSRF token.
  const status = await page.evaluate(async () => {
    const csrf = document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '';
    const response = await fetch('/api/v1/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: 'Sneaky', geographic_coverage: 'OM' }),
    });
    return response.status;
  });
  expect(status).toBe(403);
});
