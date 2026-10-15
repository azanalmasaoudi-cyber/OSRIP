import { expect, test } from '@playwright/test';

// Runs last (file name) because it adds monthly SYNTHETIC water data next to the
// annual series, which makes the water section mixed for every later test.
// Regression for a defect found by the performance workload: a section with
// monthly and annual values could not be read or reported from the interface.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

test('a mixed-frequency section explains itself and lets the reader choose one frequency', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill('manager@e2e.invalid');
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();

  // Publish two monthly values through the API with the manager's session.
  const published = await page.evaluate(async () => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const headers = { 'X-CSRF-Token': csrf };
    const json = { ...headers, 'Content-Type': 'application/json' };
    const src = await (await fetch('/api/v1/sources', { method: 'POST', headers: json,
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: 'E2E monthly water (synthetic)', geographic_coverage: 'OM' }) })).json();
    const form = new FormData();
    form.set('source_id', src.id);
    form.set('version_label', 'monthly-v1');
    form.set('file', new Blob([
      'indicator_code,area_code,period_start,period_end,frequency,unit_code,value\n'
      + 'WATER_PRODUCTION,OM,2012-01-01,2012-01-31,monthly,million_m3,30.5\n'
      + 'WATER_PRODUCTION,OM,2012-02-01,2012-02-29,monthly,million_m3,28.25\n',
    ], { type: 'text/csv' }), 'monthly.csv');
    const imp = await (await fetch('/api/v1/imports', { method: 'POST', headers, body: form })).json();
    const v = await (await fetch(`/api/v1/imports/${imp.id}/validate`, { method: 'POST', headers })).json();
    await fetch(`/api/v1/imports/${imp.id}/approve`, { method: 'POST', headers: json,
      body: JSON.stringify({ acknowledged_rejected_rows: v.rejected_row_count, note: 'e2e' }) });
    return (await fetch(`/api/v1/imports/${imp.id}/publish`, { method: 'POST', headers })).status;
  });
  expect(published).toBe(200);

  await page.goto('/energy/water?mode=synthetic');
  const notice = page.locator('[data-state="mixed_frequency"]');
  await expect(notice).toContainText('Choose one frequency');
  await notice.getByTestId('choose-frequency-monthly').click();
  await expect(page).toHaveURL(/frequency=monthly/);
  await expect(page.getByTestId('filter-frequency')).toHaveValue('monthly');
  const card = page.getByTestId('series-card').filter({ hasText: 'Water production' });
  await expect(card.getByTestId('observation-value')).toHaveText(['30.5', '28.25']);
  // The page address keeps ?frequency=; the API receives it as a period kind.
  await expect(page.getByTestId('export-observations').first()).toHaveAttribute('href', /period_kind=monthly/);

  // Choosing annual shows the annual series instead; the workspace links to a choice too.
  await page.getByTestId('filter-frequency').selectOption('annual');
  await expect(page.getByTestId('series-card').filter({ hasText: 'Water production' }).getByTestId('observation-value'))
    .toHaveText(['412.5']);
  await page.goto('/overview?mode=synthetic&domain=energy_essential_services&section=water');
  await expect(page.locator('[data-state="mixed_frequency"]').first()).toBeVisible();
  // The choice stays in the workspace: its frequency filter is set and the cards appear.
  await page.getByTestId('workspace').getByTestId('choose-frequency-monthly').click();
  await expect(page).toHaveURL(/\/overview\?.*frequency=monthly/);
  await expect(page.getByTestId('workspace').getByTestId('filter-frequency')).toHaveValue('monthly');
  await expect(page.getByTestId('workspace').getByTestId('indicator-card').first()).toBeVisible();
});
