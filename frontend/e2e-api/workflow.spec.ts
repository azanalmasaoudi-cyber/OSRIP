import { expect, test, type Page } from '@playwright/test';

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
  // "All" frequencies reads each period kind apart; the fixture's full years are the annual read.
  const apiResponse = page.waitForResponse((r) => r.url().includes('/api/v1/observations') && r.url().includes('period_kind=annual') && r.ok());
  await page.goto('/energy/electricity?mode=synthetic');
  const body = await (await apiResponse).json();
  expect(body.status).toBe('ok');
  const generation = body.series.find((s: { indicator: { code: string } }) => s.indicator.code === 'ELEC_GENERATION');
  expect(generation.observations.map((o: { value: string }) => o.value)).toEqual(['48000', '50100']);

  const card = page.getByTestId('series-card').filter({ hasText: 'Electricity generation' }).first();
  await expect(card.getByTestId('observation-value')).toHaveText(['48,000', '50,100']);
  await expect(card.getByTestId('data-mode-badge').first()).toHaveText('Synthetic demonstration data');
  await expect(page.getByTestId('prototype-notice')).toContainText('Connected to the OSRIP API');

  await card.getByTestId('source-details-button').click();
  const details = page.getByRole('dialog').getByTestId('source-details');
  await expect(details).toContainText('OSRIP booklet worked-example fixtures (synthetic)');
  await expect(details).toContainText('None (synthetic data has no publisher)');
  await expect(details).toContainText('fixtures-v1');
});

test('verified-source mode never falls back to the synthetic fixture', async ({ page }) => {
  await page.goto('/energy/electricity');
  await expect(page.locator('[data-state="no_verified_data"]')).toBeVisible();
  await expect(page.getByTestId('series-card')).toHaveCount(0);
});

test('Arabic shows the same API values', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  const values = page.getByTestId('observation-value');
  await expect(values).toHaveText(['330', '343']);
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(values).toHaveText(['330', '343']);
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

  // The new value appears on the public dashboard; the rejected row does not.
  await page.goto('/energy/water?mode=synthetic');
  const card = page.getByTestId('series-card').filter({ hasText: 'Water production' });
  await expect(card.getByTestId('observation-value')).toHaveText(['412.5']);
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
