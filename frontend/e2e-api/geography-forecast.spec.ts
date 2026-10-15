import { expect, test, type Page } from '@playwright/test';

// Full stack: the sourced area registry, statistical coverage by area and the
// forecast eligibility check. The basemap style points at a URL that is not a
// map style (playwright.api.config.ts), so these runs make no external requests
// and exercise the "map unavailable" path.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

function row(page: Page, code: string) {
  return page.locator(`[data-testid="area-table"] tbody tr[data-code="${code}"]`);
}

test('registry lists 11 governorates and 63 wilayats, separately from statistical coverage', async ({ page }) => {
  await page.goto('/geography');
  await expect(page.getByTestId('registry-counts')).toContainText('11 governorates and 63 wilayats');
  await expect(page.getByTestId('registry-summary')).toContainText('Complete');
  await expect(page.locator('[data-testid="area-table"] tbody tr')).toHaveCount(75);
  // Verified mode has no published data: every area reads "No data", never 0.
  await expect(page.getByTestId('coverage-counts')).toHaveText('0 of 75 registry areas have published observations.');
  await expect(row(page, 'OM-ZU')).toContainText('No data');
  await expect(page.locator('[data-testid="area-table"] [data-coverage="some"]')).toHaveCount(0);

  // The map service is unavailable here; the page says so and the table remains.
  await expect(page.getByTestId('map-unavailable')).toBeVisible();
  await expect(page.getByTestId('map-notes')).toContainText('No boundary geometry is included');
});

test('filters and selection: a wilayat shows its sources and "No data"', async ({ page }) => {
  await page.goto('/geography?mode=synthetic');
  await page.getByTestId('filter-governorate').selectOption('OM-DA');
  await expect(page).toHaveURL(/governorate=OM-DA/);
  await expect(page.locator('[data-testid="area-table"] tbody tr')).toHaveCount(10); // the governorate + 9 wilayats
  await row(page, 'OM-DA-09').getByRole('button').click();
  const selected = page.getByTestId('selected-area');
  await expect(selected).toHaveAttribute('data-area', 'OM-DA-09');
  await expect(selected).toContainText('Al Jabal Al Akhdar');
  await expect(selected).toContainText('assigned by OSRIP, not official');
  await expect(selected).toContainText('Established as a wilayat in 2022');
  await expect(selected.getByTestId('area-no-data')).toContainText('missing data, not zero');
  await expect(page).toHaveURL(/area=OM-DA-09/);

  // Same selection and filters after a language switch.
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(page.getByTestId('selected-area')).toContainText('الجبل الأخضر');
  await expect(page.locator('[data-testid="area-table"] tbody tr')).toHaveCount(10);
  await page.getByRole('button', { name: 'English' }).click();
});

test('the national area shows its synthetic observations; governorates do not inherit them', async ({ page }) => {
  await page.goto('/geography?mode=synthetic&area=OM');
  const selected = page.getByTestId('selected-area');
  await expect(selected.getByTestId('area-observations')).toContainText('48,000');
  await expect(row(page, 'OM')).toContainText('Observations:');
  await expect(row(page, 'OM-MA')).toContainText('No data');
  await page.getByTestId('filter-coverage').selectOption('with_data');
  await expect(page.locator('[data-testid="area-table"] tbody tr')).toHaveCount(1);
});

test('forecasts: withheld for every target in both modes, with reasons and conditions', async ({ page }) => {
  await page.goto('/forecasts');
  await expect(page.getByTestId('forecast-unavailable')).toContainText(
    'Insufficient comparable historical data for a reliable forecast.',
  );
  const targets = page.getByTestId('forecast-target');
  await expect(targets).toHaveCount(15);
  // Each domain on its own: A history, B forecasts, development conditions and C scenarios.
  await page.getByTestId('forecast-domain').getByRole('radio', { name: 'Water' }).click();
  await expect(page).toHaveURL(/domain=water/);
  await expect(targets).toHaveCount(2);
  await expect(page.getByTestId('history-panel')).toContainText('Water');
  await expect(page.locator('[data-testid="condition"][data-code="network_losses"]')).toHaveAttribute('data-status', 'scenario_assumption');
  await page.getByTestId('forecast-domain').getByRole('radio', { name: 'All domains' }).click();
  await expect(page.locator('[data-testid="forecast-target"][data-status="available"]')).toHaveCount(0);
  await expect(targets.first().getByTestId('insufficient')).toContainText('No published series');
  await expect(page.getByTestId('forecast-demo-label')).toHaveCount(0);
  await expect(page.getByTestId('run-forecast')).toHaveCount(0);

  // The old address still works and keeps the data mode.
  await page.goto('/forecast?mode=synthetic');
  await expect(page).toHaveURL(/\/forecasts\?mode=synthetic/);
  await expect(page.getByTestId('forecast-demo-label').first()).toContainText('Not a validated forecast for Oman');
  const generation = page.locator('[data-testid="forecast-target"][data-indicator="ELEC_GENERATION"]');
  await expect(generation).toHaveAttribute('data-status', 'insufficient_data');
  await expect(generation.getByTestId('insufficient')).toContainText('needs at least 12');
  const method = page.getByTestId('forecast-method');
  await method.locator('summary').click();
  await expect(method).toContainText('Seasonal naive');
  await expect(method).toContainText('strictly lower mean absolute error');
});

test('an analyst request on an ineligible series is recorded as withheld (T10)', async ({ page }) => {
  await signIn(page, 'analyst@e2e.invalid');
  await page.goto('/forecasts?mode=synthetic');
  // The page offers no run for an ineligible series; a direct API request is recorded as withheld.
  const result = await page.evaluate(async () => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const overview = await (await fetch('/api/v1/forecast/overview?data_mode=synthetic')).json();
    const target = overview.targets.find((t: { indicator: string }) => t.indicator === 'ELEC_GENERATION');
    const response = await fetch('/api/v1/forecast-runs', {
      method: 'POST', headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
      body: JSON.stringify({ data_mode: 'synthetic', series_id: target.series[0].series_id }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(result.status).toBe(201);
  expect(result.body.status).toBe('withheld');
  expect(result.body.status_reason).toContain('needs at least 12');
  expect(result.body.outputs).toEqual([]);
});
