import { expect, test, type Page } from '@playwright/test';

// Runs near the end (file name) because it publishes SYNTHETIC water distributed for two
// governorates and one wilayat, which later tests would otherwise see.
// A governorate, then only its wilayats that publish the indicator: in a sector's guided analysis
// and on the map. A governorate's figure is never painted on its wilayats or shared out among
// them; a governorate whose wilayats publish nothing says "No published wilayat data".

test.skip(({ isMobile }) => isMobile, 'desktop layout');

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signInAsManager(page: Page) {
  await page.goto('/sign-in');
  await page.getByLabel('Username').fill('e2emanager');
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

/** Publishes a synthetic CSV through the import workflow with the manager's session. */
async function publishSynthetic(page: Page, title: string, label: string, csv: string) {
  return page.evaluate(async ({ title, label, csv }) => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const headers = { 'X-CSRF-Token': csrf };
    const json = { ...headers, 'Content-Type': 'application/json' };
    const src = await (await fetch('/api/v1/sources', { method: 'POST', headers: json,
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: title, geographic_coverage: 'Dhofar, Salalah, Muscat' }) })).json();
    const form = new FormData();
    form.set('source_id', src.id);
    form.set('version_label', label);
    form.set('file', new Blob([csv], { type: 'text/csv' }), `${label}.csv`);
    const imp = await (await fetch('/api/v1/imports', { method: 'POST', headers, body: form })).json();
    const v = await (await fetch(`/api/v1/imports/${imp.id}/validate`, { method: 'POST', headers })).json();
    await fetch(`/api/v1/imports/${imp.id}/approve`, { method: 'POST', headers: json,
      body: JSON.stringify({ acknowledged_rejected_rows: v.rejected_row_count, note: 'e2e' }) });
    const status = (await fetch(`/api/v1/imports/${imp.id}/publish`, { method: 'POST', headers })).status;
    return { status, rejected: v.rejected_row_count as number };
  }, { title, label, csv });
}

test('a governorate, then only its wilayats that publish the indicator: in the guided analysis and on the map', async ({ page }) => {
  await signInAsManager(page);
  const published = await publishSynthetic(page, 'E2E places (synthetic)', 'places-v1',
    'indicator_code,area_code,period_start,period_end,frequency,unit_code,value\n'
    + 'WATER_DISTRIBUTION,OM-ZU,2015-01-01,2015-12-31,annual,million_m3,70\n'
    + 'WATER_DISTRIBUTION,OM-ZU,2016-01-01,2016-12-31,annual,million_m3,74\n'
    + 'WATER_DISTRIBUTION,OM-ZU-01,2015-01-01,2015-12-31,annual,million_m3,41\n'
    + 'WATER_DISTRIBUTION,OM-ZU-01,2016-01-01,2016-12-31,annual,million_m3,43\n'
    + 'WATER_DISTRIBUTION,OM-MA,2015-01-01,2015-12-31,annual,million_m3,190\n'
    + 'WATER_DISTRIBUTION,OM-MA,2016-01-01,2016-12-31,annual,million_m3,200\n');
  expect(published).toEqual({ status: 200, rejected: 0 });

  // The guided analysis: governorates that publish the indicator, then their own wilayats.
  await page.goto('/energy/water?mode=synthetic');
  await page.getByTestId('sector-indicator').selectOption('WATER_DISTRIBUTION');
  const governorate = page.getByTestId('guide-governorate');
  const values = await governorate.locator('option').evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
  expect(values).toEqual(expect.arrayContaining(['OM-ZU', 'OM-MA']));
  expect(values).not.toContain('OM-ZU-01'); // a wilayat is listed under its governorate, not beside it
  await governorate.selectOption('OM-ZU');
  const wilayat = page.getByTestId('guide-wilayat');
  await expect(wilayat.locator('option')).toHaveText(['Whole governorate', 'Salalah']);
  // Muscat publishes the indicator for itself only: no wilayat list, and it says so.
  await governorate.selectOption('OM-MA');
  await expect(page.getByTestId('guide-wilayat')).toHaveCount(0);
  await expect(page.getByTestId('guide-no-wilayat-data')).toHaveText('No published wilayat data for this indicator in Muscat.');
  // Salalah's own values; Dhofar's are not shown for it.
  await governorate.selectOption('OM-ZU');
  await wilayat.selectOption('OM-ZU-01');
  await page.getByTestId('sector-from').selectOption('2015-01-01');
  await page.getByTestId('sector-to').selectOption('2016-01-01');
  await page.getByTestId('sector-show-results').click();
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-area', 'OM-ZU-01');
  await expect(page).toHaveURL(/at=OM-ZU-01/);
  await expect(page.getByTestId('applied-details')).toContainText('Salalah');
  await expect(page.getByTestId('summary-latest')).toContainText('43');
  await expect(page.getByTestId('summary-latest')).not.toContainText('74');

  // The map: Dhofar's ten wilayats; only Salalah has a value, the other nine have none (not zero).
  await page.goto('/geography?mode=synthetic&governorate=OM-ZU');
  await expect(page.getByTestId('map-focus-status')).toHaveText('Showing Dhofar and its 10 wilayats only.');
  const comparison = page.getByTestId('governorate-comparison');
  await expect(comparison).toHaveAttribute('data-level', 'wilayat');
  await comparison.getByTestId('compare-indicator').selectOption('WATER_DISTRIBUTION');
  await comparison.getByTestId('compare-period').selectOption('2016-01-01');
  const rows = comparison.getByTestId('compare-row');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toHaveAttribute('data-area', 'OM-ZU-01');
  await expect(rows.first()).toContainText('43');
  await expect(comparison).toContainText('9');
  await expect(comparison).not.toContainText('74'); // the governorate's figure is not a wilayat's
  // No share of a national total is computed for a wilayat.
  await expect(page.getByTestId('oman-map')).not.toContainText('of the national total');
});
