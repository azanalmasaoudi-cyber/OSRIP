import { expect, test, type Page } from '@playwright/test';

import { showResults } from './sector';

// Runs last (file name) because it adds monthly SYNTHETIC water data next to the annual
// series, and year-to-date trade figures next to full years, which makes those sections
// mixed for every later test.
// Regressions: a section with monthly and annual values could not be read or reported from
// the interface; a section holding full years and year-to-date totals was refused (422
// incompatible_series) instead of shown; partner slices of one indicator gave their change
// calculations the same id (duplicate React keys); and a year with only a year-to-date total
// could not be chosen at all.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signInAsManager(page: Page) {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill('manager@e2e.invalid');
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
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: title, geographic_coverage: 'OM' }) })).json();
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

/** Refused observation reads and duplicate-key warnings seen by the page. */
function watchForDefects(page: Page) {
  const refused: string[] = [];
  const duplicateKeys: string[] = [];
  page.on('response', (r) => {
    if (r.url().includes('/api/v1/observations') && r.status() >= 400) refused.push(`${r.status()} ${r.url()}`);
  });
  page.on('console', (m) => {
    if (m.type() === 'error' && m.text().includes('two children with the same key')) duplicateKeys.push(m.text());
  });
  return { refused, duplicateKeys };
}

test('a mixed-frequency indicator offers each frequency apart and shows only the chosen one', async ({ page }) => {
  await signInAsManager(page);
  const published = await publishSynthetic(page, 'E2E monthly water (synthetic)', 'monthly-v1',
    'indicator_code,area_code,period_start,period_end,frequency,unit_code,value\n'
    + 'WATER_PRODUCTION,OM,2012-01-01,2012-01-31,monthly,million_m3,30.5\n'
    + 'WATER_PRODUCTION,OM,2012-02-01,2012-02-29,monthly,million_m3,28.25\n');
  expect(published).toEqual({ status: 200, rejected: 0 });
  const seen = watchForDefects(page);

  // Each frequency is offered with its own published periods; nothing is derived from two
  // months of a quarter or a year, and annual values are never split into months.
  await page.goto('/energy/water?mode=synthetic');
  await page.getByTestId('sector-indicator').selectOption('WATER_PRODUCTION');
  const frequency = page.getByTestId('sector-frequency');
  await frequency.locator('[data-value="monthly"]').click();
  const options = (id: string) => page.getByTestId(id).locator('option:not([value=""])');
  await expect(options('sector-from')).toHaveText(['Jan 2012', 'Feb 2012']);
  await expect(frequency.locator('[data-value="quarterly"]')).toContainText('not published');
  await showResults(page, { view: 'monthly', from: '2012-01-01', to: '2012-02-01' });
  await expect(page.getByTestId('series-row').locator('td:first-of-type')).toHaveText(['30.5', '28.25']);
  await expect(page.getByTestId('summary-total')).toContainText('58.75');
  await expect(page.getByTestId('export-observations').first()).toHaveAttribute('href', /period_kind=monthly/);

  // Changing the frequency hides the monthly results until the annual ones are asked for.
  await frequency.locator('[data-value="annual"]').click();
  await expect(page.getByTestId('sector-stale')).toBeVisible();
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
  await expect(options('sector-from')).toHaveText(['2009']); // 2012 has only two months
  await showResults(page, { view: 'annual', from: '2009-01-01', to: '2009-01-01' });
  await expect(page.getByTestId('series-row').locator('td:first-of-type')).toHaveText(['412.5']);

  // The workspace lists the kinds apart too; analysing a monthly card chooses that frequency.
  await page.goto('/workspace?mode=synthetic&domain=energy_essential_services&section=water');
  const workspace = page.getByTestId('workspace');
  const production = '[data-testid="indicator-card"][data-indicator="WATER_PRODUCTION"]';
  const monthlyCard = workspace.locator('[data-testid="period-kind-group"][data-period-kind="monthly"]').locator(production);
  await expect(monthlyCard).toHaveCount(1);
  await expect(workspace.locator('[data-testid="period-kind-group"][data-period-kind="annual"]').locator(production)).toHaveCount(1);
  await monthlyCard.getByTestId('indicator-analyse').click();
  await expect(page).toHaveURL(/\/workspace\?.*frequency=monthly/);
  await expect(workspace.getByTestId('filter-frequency')).toHaveValue('monthly');
  await expect(workspace.getByTestId('period-kind-group')).toHaveCount(1);
  await expect(workspace.locator(production)).toHaveAttribute('data-selected', 'true');

  expect(seen.refused).toEqual([]);
  expect(seen.duplicateKeys).toEqual([]);
});

test('trade with full years and year-to-date totals per partner: year-to-date years can be chosen, shown apart, no refused read, no duplicate keys', async ({ page }) => {
  await signInAsManager(page);
  // A national total and two (fictional) partner slices, each with one full year and two
  // year-to-date totals: before the fix every slice's change shared one id.
  const rows = [['', '900', '560', '610'], ['PARTNER_A', '300', '190', '205'], ['PARTNER_B', '200', '120', '131']]
    .flatMap(([partner, year, ytd1, ytd2]) => [
      `TRADE_MERCH_IMPORTS,OM,2001-01-01,2001-12-31,annual,million_OMR,${year},true,import,${partner}`,
      `TRADE_MERCH_IMPORTS,OM,2002-01-01,2002-07-31,annual,million_OMR,${ytd1},false,import,${partner}`,
      `TRADE_MERCH_IMPORTS,OM,2003-01-01,2003-07-31,annual,million_OMR,${ytd2},false,import,${partner}`,
    ]);
  const published = await publishSynthetic(page, 'E2E trade year to date (synthetic)', 'ytd-v1',
    `indicator_code,area_code,period_start,period_end,frequency,unit_code,value,period_complete,flow,partner_code\n${rows.join('\n')}\n`);
  expect(published).toEqual({ status: 200, rejected: 0 });
  const seen = watchForDefects(page);

  // The years with only year-to-date totals can be chosen; they are listed apart from the
  // full year and compared only with the same months a year earlier.
  await page.goto('/trade?mode=synthetic');
  await page.getByTestId('sector-indicator').selectOption('TRADE_MERCH_IMPORTS');
  await expect(page.getByTestId('sector-breakdown').locator('option')).toHaveCount(3); // total and two partners
  await page.getByTestId('sector-breakdown').selectOption('||import');
  await expect(page.getByTestId('sector-to').locator('option:not([value=""])'))
    .toHaveText(['2001', '2002 (year to date only)', '2003 (year to date only)']);
  await showResults(page, { breakdown: '||import', view: 'annual', from: '2001-01-01', to: '2003-01-01' });
  await expect(page.getByTestId('series-row').locator('td:first-of-type')).toHaveText(['900']);
  const ytd = page.getByTestId('series-ytd-row');
  await expect(ytd).toHaveCount(2);
  await expect(ytd.nth(1)).toContainText('610');
  await expect(ytd.nth(1)).toContainText('+50');
  // A partner slice: its own rows, no shared ids.
  await showResults(page, { breakdown: '|PARTNER_A|import', view: 'annual', from: '2001-01-01', to: '2003-01-01' });
  await expect(page.getByTestId('series-row').locator('td:first-of-type')).toHaveText(['300']);
  await expect(page.getByTestId('series-ytd-row')).toHaveCount(2);

  await page.goto('/workspace?mode=synthetic&domain=trade&section=trade');
  const workspace = page.getByTestId('workspace');
  await expect(workspace.locator('[data-testid="period-kind-group"][data-period-kind="year_to_date"]')
    .locator('[data-testid="indicator-card"][data-indicator="TRADE_MERCH_IMPORTS"]')).toHaveCount(1);
  await expect(workspace.locator('[data-state="mixed_frequency"]')).toHaveCount(0);

  expect(seen.refused).toEqual([]);
  expect(seen.duplicateKeys).toEqual([]);
});
