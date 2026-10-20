import { expect, test, type Page } from '@playwright/test';

// Runs last (file name) because it adds monthly SYNTHETIC water data next to the annual
// series, and year-to-date trade figures next to full years, which makes those sections
// mixed for every later test.
// Regressions: a section with monthly and annual values could not be read or reported from
// the interface; with the frequency on "All", a section holding full years and year-to-date
// totals was refused (422 incompatible_series) instead of shown; and partner slices of one
// indicator gave their change calculations the same id (duplicate React keys).

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

test('a mixed-frequency section lists each frequency apart and lets the reader choose one', async ({ page }) => {
  await signInAsManager(page);
  const published = await publishSynthetic(page, 'E2E monthly water (synthetic)', 'monthly-v1',
    'indicator_code,area_code,period_start,period_end,frequency,unit_code,value\n'
    + 'WATER_PRODUCTION,OM,2012-01-01,2012-01-31,monthly,million_m3,30.5\n'
    + 'WATER_PRODUCTION,OM,2012-02-01,2012-02-29,monthly,million_m3,28.25\n');
  expect(published).toEqual({ status: 200, rejected: 0 });
  const seen = watchForDefects(page);

  // "All": each period kind is read on its own and listed in its own group, never refused.
  await page.goto('/energy/water?mode=synthetic');
  const monthly = page.locator('[data-testid="period-kind-group"][data-period-kind="monthly"]');
  const annual = page.locator('[data-testid="period-kind-group"][data-period-kind="annual"]');
  await expect(monthly.getByRole('heading', { name: 'Monthly' })).toBeVisible();
  await expect(monthly.getByTestId('series-card').filter({ hasText: 'Water production' }).getByTestId('observation-value'))
    .toHaveText(['30.5', '28.25']);
  await expect(annual.getByTestId('series-card').filter({ hasText: 'Water production' }).getByTestId('observation-value'))
    .toHaveText(['412.5']);
  await expect(page.getByTestId('period-kinds-note')).toBeVisible();
  await expect(page.locator('[data-state="mixed_frequency"]')).toHaveCount(0);

  // Choosing one frequency shows it alone; the page address keeps ?frequency= and the API
  // receives it as a period kind.
  await page.getByTestId('filter-frequency').selectOption('monthly');
  await expect(page).toHaveURL(/frequency=monthly/);
  await expect(page.getByTestId('period-kind-group')).toHaveCount(0);
  const card = page.getByTestId('series-card').filter({ hasText: 'Water production' });
  await expect(card.getByTestId('observation-value')).toHaveText(['30.5', '28.25']);
  await expect(page.getByTestId('export-observations').first()).toHaveAttribute('href', /period_kind=monthly/);
  await page.getByTestId('filter-frequency').selectOption('annual');
  await expect(page.getByTestId('series-card').filter({ hasText: 'Water production' }).getByTestId('observation-value'))
    .toHaveText(['412.5']);

  // The workspace lists the kinds apart too; analysing a monthly card chooses that frequency.
  await page.goto('/overview?mode=synthetic&domain=energy_essential_services&section=water');
  const workspace = page.getByTestId('workspace');
  const production = '[data-testid="indicator-card"][data-indicator="WATER_PRODUCTION"]';
  const monthlyCard = workspace.locator('[data-testid="period-kind-group"][data-period-kind="monthly"]').locator(production);
  await expect(monthlyCard).toHaveCount(1);
  await expect(workspace.locator('[data-testid="period-kind-group"][data-period-kind="annual"]').locator(production)).toHaveCount(1);
  await monthlyCard.getByTestId('indicator-analyse').click();
  await expect(page).toHaveURL(/\/overview\?.*frequency=monthly/);
  await expect(workspace.getByTestId('filter-frequency')).toHaveValue('monthly');
  await expect(workspace.getByTestId('period-kind-group')).toHaveCount(1);
  await expect(workspace.locator(production)).toHaveAttribute('data-selected', 'true');

  expect(seen.refused).toEqual([]);
  expect(seen.duplicateKeys).toEqual([]);
});

test('trade with full years and year-to-date totals per partner: shown apart, no refused read, no duplicate keys', async ({ page }) => {
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

  await page.goto('/trade?mode=synthetic');
  const ytd = page.locator('[data-testid="period-kind-group"][data-period-kind="year_to_date"]');
  await expect(ytd.getByRole('heading', { name: 'Year to date' })).toBeVisible();
  await expect(ytd.locator('[data-testid="series-card"][data-indicator="TRADE_MERCH_IMPORTS"]')).toHaveCount(3);
  await expect(page.locator('[data-testid="period-kind-group"][data-period-kind="annual"]')
    .locator('[data-testid="series-card"][data-indicator="TRADE_MERCH_IMPORTS"]')).toHaveCount(3);
  // One change per year-to-date slice (absolute and percentage), each its own card.
  await expect(page.getByTestId('calculation').filter({ hasText: 'Recorded merchandise imports: growth' })).toHaveCount(3);

  await page.goto('/overview?mode=synthetic&domain=trade&section=trade');
  const workspace = page.getByTestId('workspace');
  await expect(workspace.locator('[data-testid="period-kind-group"][data-period-kind="year_to_date"]')
    .locator('[data-testid="indicator-card"][data-indicator="TRADE_MERCH_IMPORTS"]')).toHaveCount(1);
  await expect(workspace.locator('[data-state="mixed_frequency"]')).toHaveCount(0);

  expect(seen.refused).toEqual([]);
  expect(seen.duplicateKeys).toEqual([]);
});
