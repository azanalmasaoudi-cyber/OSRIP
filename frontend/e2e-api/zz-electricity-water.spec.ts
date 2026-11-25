import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

import { ask } from './chat';

// Runs near the end (file name): it publishes SYNTHETIC national electricity for 2022-2025 and
// stages and approves the verified outlook items (docs/data-imports/2026-11-electricity-water).
// The electricity and water sectors show their annual indicators side by side as distinct series,
// and the official outlook apart from them, each item with its evidence class; Al Mulhim answers
// outlook questions with the same classes.

test.skip(({ isMobile }) => isMobile, 'desktop layout; a narrow screen is tested below');

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const ITEMS = JSON.parse(readFileSync(new URL('../../docs/data-imports/2026-11-electricity-water/outlook-items.json', import.meta.url), 'utf8')) as unknown[];

async function signInAsManager(page: Page) {
  await page.goto('/sign-in');
  await page.getByLabel('Username').fill('e2emanager');
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

/** With the manager's session: publish a synthetic CSV; stage the outlook and approve it all. */
async function prepare(page: Page, csv: string) {
  return page.evaluate(async ({ csv, items }) => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const headers = { 'X-CSRF-Token': csrf };
    const json = { ...headers, 'Content-Type': 'application/json' };
    const src = await (await fetch('/api/v1/sources', { method: 'POST', headers: json,
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: 'E2E electricity 2022-2025 (synthetic)', geographic_coverage: 'OM' }) })).json();
    const form = new FormData();
    form.set('source_id', src.id);
    form.set('version_label', 'elec-2022-2025');
    form.set('file', new Blob([csv], { type: 'text/csv' }), 'elec.csv');
    const imp = await (await fetch('/api/v1/imports', { method: 'POST', headers, body: form })).json();
    const v = await (await fetch(`/api/v1/imports/${imp.id}/validate`, { method: 'POST', headers })).json();
    await fetch(`/api/v1/imports/${imp.id}/approve`, { method: 'POST', headers: json, body: JSON.stringify({ acknowledged_rejected_rows: v.rejected_row_count, note: 'e2e' }) });
    const published = (await fetch(`/api/v1/imports/${imp.id}/publish`, { method: 'POST', headers })).status;
    const staged = await (await fetch('/api/v1/outlook/batches', { method: 'POST', headers: json, body: JSON.stringify({ batch_label: 'e2e-outlook', items }) })).json();
    const review = await (await fetch('/api/v1/outlook/review', { headers })).json();
    for (const item of review.items) {
      if (item.review_status === 'pending') {
        await fetch(`/api/v1/outlook/${item.id}/review`, { method: 'POST', headers: json, body: JSON.stringify({ decision: 'approved', note: 'e2e' }) });
      }
    }
    return { published, rejected: v.rejected_row_count as number, staged: staged.inserted as number };
  }, { csv, items: ITEMS });
}

test('electricity: distinct annual indicators side by side, then the official outlook apart, then Al Mulhim', async ({ page }) => {
  await signInAsManager(page);
  const rows = ['indicator_code,area_code,period_start,period_end,frequency,unit_code,value,revision_status'];
  const series: [string, number[]][] = [['ELEC_CONSUMPTION', [3642.7, 3929.6, 4215.6, 4503.3]], ['ELEC_DISTRIBUTION', [3617.8, 3929.6, 4215.6, 4503.3]],
    ['ELEC_GROSS_GENERATION', [4251, 4496.5, 4913.2, 5097.3]], ['ELEC_CONSUMPTION_RESIDENTIAL', [1577.6, 1718.7, 1811.5, 1862.4]]];
  for (const [code, values] of series) {
    values.forEach((v, i) => rows.push(`${code},OM,${2022 + i}-01-01,${2022 + i}-12-31,annual,GWh,${v},${i === 3 ? 'provisional' : 'reported'}`));
  }
  expect(await prepare(page, `${rows.join('\n')}\n`)).toEqual({ published: 200, rejected: 0, staged: 19 });

  // Data and indicators: each indicator its own row; 2022 consumption and distribution differ.
  await page.goto('/energy/electricity?mode=synthetic&tab=data');
  const annual = page.getByTestId('annual-indicators');
  const row = (code: string) => annual.locator(`[data-testid="annual-row"][data-indicator="${code}"]`);
  await expect(row('ELEC_CONSUMPTION').locator('td[data-year="2022"]')).toContainText('3,642.7');
  await expect(row('ELEC_DISTRIBUTION').locator('td[data-year="2022"]')).toContainText('3,617.8');
  await expect(row('ELEC_GROSS_GENERATION')).toBeVisible();
  await expect(row('ELEC_CONSUMPTION').locator('td[data-year="2025"]')).toHaveAttribute('data-provisional', 'true');
  await expect(row('ELEC_CONSUMPTION').locator('td[data-year="2023"]')).toContainText('+7.9%'); // the server's change
  await expect(annual.getByTestId('annual-notes')).toContainText('different published indicators');
  // The export: the same cells, the two indicators apart, provisional marked, sources kept.
  const csv = await (await page.request.get((await annual.getByTestId('annual-csv').getAttribute('href')) ?? '')).text();
  expect(csv).toContain('electricity,totals,ELEC_CONSUMPTION,');
  expect(csv).toMatch(/ELEC_CONSUMPTION,[^\n]*,OM,2022,3642\.7,/);
  expect(csv).toMatch(/ELEC_DISTRIBUTION,[^\n]*,OM,2022,3617\.8,/);
  expect(csv).toMatch(/ELEC_CONSUMPTION,[^\n]*,OM,2025,4503\.3,[^\n]*,true,/);
  // One year at a time.
  await annual.getByTestId('annual-year').selectOption('2024');
  await expect(row('ELEC_CONSUMPTION').locator('td[data-year]')).toHaveCount(1);

  // The guided analysis: the outlook only on request, grouped by class, never "achieved".
  await page.goto('/energy/electricity?mode=synthetic&ind=ELEC_CONSUMPTION&at=OM&bd=%7C%7C&freq=annual&from=2022-01-01&to=2025-01-01&step=analysis');
  await expect(page.getByTestId('sector-outlook')).toHaveCount(0);
  await page.getByTestId('guide-outlook-toggle').click();
  const outlook = page.getByTestId('sector-outlook');
  await expect(outlook.getByTestId('outlook-legend')).toContainText('Policy target (not achieved)');
  const peak2032 = outlook.locator('[data-testid="outlook-item"][data-metric="ELEC_PEAK_DEMAND_MIS"][data-year="2032"]');
  await expect(peak2032).toHaveAttribute('data-class', 'forecast');
  await expect(peak2032).toHaveAttribute('data-achieved', 'false');
  await expect(peak2032).toContainText('14,147 MW');
  await expect(outlook.locator('[data-testid="outlook-item"][data-metric="ELEC_RENEWABLE_SHARE_TARGET"]')).toHaveAttribute('data-class', 'policy_target');
  await expect(outlook.locator('[data-testid="outlook-item"][data-metric="ELEC_BESS_FIRST_COD"]')).toContainText('a date, not a quantity');
  // Al Mulhim: the same items with their classes.
  await page.goto('/assistant?mode=verified_source');
  const reply = await ask(page, 'What is the planned renewable generation?');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  const items = reply.getByTestId('reply-outlook').getByTestId('outlook-item');
  await expect(items.first()).toBeVisible();
  for (const cls of await items.evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.class))) expect(cls).not.toBe('');
});

test('water in Arabic on a narrow screen: the outlook reads in Arabic and nothing scrolls sideways', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/energy/water?mode=synthetic&tab=data');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('annual-indicators')).toContainText('المؤشرات السنوية');
  await expect(page.getByTestId('annual-indicators')).toContainText('عمليات المرفق');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByRole('button', { name: 'English' }).first().click();
});
