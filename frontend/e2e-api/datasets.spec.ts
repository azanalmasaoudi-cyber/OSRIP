import { readFile } from 'node:fs/promises';

import { expect, test, type Page } from '@playwright/test';

// Full stack: an analyst uploads a CSV; the API computes the statistics, trends, unusual
// values and charts from the file's own values; the chart type can be switched; the rows can
// be searched; and the analysis is frozen as a report downloaded as PDF, Excel and CSV.
// No model is called here (the AI summary is not requested).

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const CSV = `Year,Region,Generation (GWh),Peak load (MW)
2020,Muscat,"10,120.5",3100
2021,Muscat,10500,3200
2022,Muscat,11020.25,3350
2023,Muscat,,3400
2024,Muscat,12010,3550
2020,Dhofar,2100,500
2021,Dhofar,2200,520
2022,Dhofar,2350,540
2023,Dhofar,2400,560
2024,Dhofar,25000,600
2020,Batinah,4100,1200
2021,Batinah,4300,1250
2022,Batinah,4550,1300
2023,Batinah,4700,1340
2024,Batinah,4900,1400
`;

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('datasets need a signed-in account with the analysis permission', async ({ page }) => {
  await page.goto('/datasets');
  await expect(page.getByRole('link', { name: 'Sign in' }).last()).toBeVisible();
  await expect(page.getByTestId('dataset-upload')).toHaveCount(0);
});

test('an analyst uploads a CSV, reads computed results and charts, and downloads a report', async ({ page }) => {
  await signIn(page, 'analyst@e2e.invalid');
  await page.goto('/datasets');
  await page.getByLabel('File (CSV, Excel .xlsx or JSON)').setInputFiles({
    name: 'generation-by-region.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV),
  });
  await page.getByRole('button', { name: 'Upload and analyse' }).click();
  await expect(page.getByTestId('dataset-detail')).toBeVisible();

  const findings = page.getByTestId('dataset-findings');
  await expect(findings).toContainText('Generation (GWh) (Muscat): 10,120.5 in 2020 to 12,010 in 2024 (+18.67%)');
  await expect(findings.locator('[data-kind="jump"]')).toContainText('2,400 in 2023 to 25,000 in 2024 (data row 10)');
  await expect(findings.locator('[data-kind="quality"]').first()).toContainText('never counted as zero');

  const shares = page.getByTestId('dataset-view-compare_3_by_1');
  await expect(shares.getByTestId('study-bar-chart')).toBeVisible();
  await shares.getByRole('radio', { name: 'Pie' }).click();
  await expect(shares.getByTestId('study-pie-chart')).toContainText('64.3%');

  await page.getByTestId('dataset-tabs').getByRole('radio', { name: 'Statistics' }).click();
  await expect(page.getByTestId('dataset-detail')).toContainText('100,250.75');

  await page.getByTestId('dataset-tabs').getByRole('radio', { name: 'Data' }).click();
  const table = page.getByTestId('dataset-table');
  await table.getByLabel('Search all columns').fill('Dhofar');
  await expect(table.locator('tbody tr')).toHaveCount(5);

  await page.getByTestId('dataset-report-open').click();
  await page.getByLabel('Research questions (one per line, up to five; optional)').fill('How did generation change by region?');
  await page.getByRole('button', { name: 'Create report', exact: true }).click();
  const report = page.getByTestId('analysis-report');
  await expect(report).toContainText('How did generation change by region?');
  await expect(report).toContainText('Statistics');

  const download = page.waitForEvent('download');
  await page.getByTestId('analysis-report-export-pdf').click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  const bytes = await readFile(await file.path());
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');

  const workbook = page.waitForEvent('download');
  await page.getByTestId('analysis-report-export-xlsx').click();
  expect((await workbook).suggestedFilename()).toMatch(/\.xlsx$/);
});
