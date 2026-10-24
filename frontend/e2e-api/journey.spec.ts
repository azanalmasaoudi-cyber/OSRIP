import { expect, test, type Browser, type Page } from '@playwright/test';

import { openCalculations, showResults } from './sector';

// One complete journey through the real stack (browser -> Vite proxy -> FastAPI ->
// PostgreSQL): a data manager uploads and publishes a file, an analyst freezes a
// report from it, a revision is published, and the report keeps its original inputs
// (booklet 3.9, 3.12; FR01, FR02, FR05; T05, T07). All values are SYNTHETIC.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const SOURCE = 'E2E journey electricity file (synthetic)';

async function signedIn(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  return page;
}

async function uploadAndPublish(page: Page, label: string, rows: string[], expectRejected: number): Promise<void> {
  await page.goto('/data-management');
  const csv = ['indicator_code,area_code,period_start,period_end,frequency,unit_code,value', ...rows].join('\n');
  const upload = page.getByTestId('upload-form');
  await upload.getByTestId('upload-source').selectOption({ label: SOURCE });
  await upload.getByTestId('upload-label').fill(label);
  await upload.getByTestId('upload-file').setInputFiles({
    name: `${label}.csv`, mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8'),
  });
  await upload.getByRole('button', { name: 'Upload privately' }).click();
  const detail = page.getByTestId('import-detail');
  await expect(detail.getByTestId('import-status')).toHaveText('Draft');
  await detail.getByTestId('validate-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Validated');
  await expect(detail.locator('[data-count="rejected"] dd')).toHaveText(String(expectRejected));
  await detail.getByTestId('approve-ack').check();
  await detail.getByTestId('approve-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Approved');
  await detail.getByTestId('publish-button').click();
  await expect(detail.getByTestId('import-status')).toHaveText('Published');
}

function consumptionGrowth(page: Page) {
  return page.locator('[data-testid="calculation"][data-kind="percentage_change"]').filter({ hasText: 'Electricity consumption' });
}

test('upload -> validate -> approve -> publish -> report -> revision; the report keeps its inputs', async ({ browser }) => {
  test.setTimeout(120_000);
  const manager = await signedIn(browser, 'manager@e2e.invalid');

  // 1. Register a synthetic source and publish v1 (one invalid row is rejected, not dropped silently).
  await manager.goto('/data-management');
  await manager.getByRole('button', { name: 'Register a source' }).click();
  const form = manager.getByTestId('register-source-form');
  await form.getByLabel('Dataset title').fill(SOURCE);
  await form.getByRole('button', { name: 'Register source' }).click();
  await expect(manager.getByRole('listitem').filter({ hasText: SOURCE })).toBeVisible();
  await uploadAndPublish(manager, 'journey-v1', [
    'ELEC_CONSUMPTION,OM,2011-01-01,2011-12-31,annual,GWh,31000',
    'ELEC_CONSUMPTION,OM,2012-01-01,2012-12-31,annual,GWh,32550',
    'ELEC_CONSUMPTION,OM,2013-01-01,2013-12-31,annual,MW,5',
  ], 1);

  // 2. An analyst sees the published values and the calculation, then freezes a report.
  const analyst = await signedIn(browser, 'analyst@e2e.invalid');
  await analyst.goto('/energy/electricity?mode=synthetic');
  // The 2013 row in another unit was rejected, so only 2011 and 2012 can be chosen.
  await analyst.getByTestId('sector-indicator').selectOption('ELEC_CONSUMPTION');
  await expect(analyst.getByTestId('sector-to').locator('option[value="2013-01-01"]')).toHaveCount(0);
  await showResults(analyst, { indicator: 'ELEC_CONSUMPTION', view: 'annual', from: '2011-01-01', to: '2012-01-01' });
  await openCalculations(analyst);
  await expect(consumptionGrowth(analyst).getByTestId('calc-value')).toHaveText('5%');
  await expect(consumptionGrowth(analyst).getByTestId('calc-inputs')).toContainText('journey-v1');
  await analyst.getByTestId('save-report').click();
  const title = `Journey report ${Date.now()}`;
  const saveForm = analyst.getByTestId('save-report-form');
  await saveForm.getByLabel('Report title').fill(title);
  await saveForm.getByRole('button', { name: 'Create report' }).click();
  await analyst.getByTestId('open-new-report').click();
  const report = analyst.getByTestId('report');
  await expect(report).toHaveAttribute('data-mode', 'synthetic');
  await expect(report.getByTestId('report-label')).toContainText('SYNTHETIC DEMONSTRATION DATA');
  await expect(report.getByTestId('report-sources')).toContainText('journey-v1');
  await expect(report.locator('[data-testid="calculation"][data-kind="percentage_change"]').filter({ hasText: 'Electricity consumption' })
    .getByTestId('calc-value')).toHaveText('5%');
  const reportUrl = analyst.url();

  // The CSV export carries the label, the version and the unrounded values.
  const href = await report.getByTestId('report-export').getAttribute('href');
  const csv = await (await analyst.request.get(href ?? '')).text();
  expect(csv).toContain('SYNTHETIC DEMONSTRATION DATA');
  expect(csv).toContain('journey-v1');
  expect(csv).toContain('32550');

  // 3. A revision (v2) supersedes v1: live views change, the frozen report does not.
  await uploadAndPublish(manager, 'journey-v2', [
    'ELEC_CONSUMPTION,OM,2011-01-01,2011-12-31,annual,GWh,31000',
    'ELEC_CONSUMPTION,OM,2012-01-01,2012-12-31,annual,GWh,34100',
  ], 0);
  // Returning to the sector shows the remembered selection again, now from v2.
  await analyst.goto('/energy/electricity?mode=synthetic');
  await expect(analyst.getByTestId('applied-range')).toHaveText('2011 – 2012');
  await expect(analyst.getByTestId('series-chart')).toHaveCount(0); // never drawn on return
  await openCalculations(analyst);
  await expect(consumptionGrowth(analyst).getByTestId('calc-value')).toHaveText('10%');
  await expect(consumptionGrowth(analyst).getByTestId('calc-inputs')).toContainText('journey-v2');
  await analyst.goto(reportUrl);
  await expect(report.getByTestId('report-sources')).toContainText('journey-v1');
  await expect(report.getByTestId('report-sources')).not.toContainText('journey-v2');
  await expect(report.locator('[data-testid="calculation"][data-kind="percentage_change"]').filter({ hasText: 'Electricity consumption' })
    .getByTestId('calc-value')).toHaveText('5%');
});
