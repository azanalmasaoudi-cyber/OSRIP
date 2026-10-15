import { expect, test, type Page } from '@playwright/test';

// Runs after every other full-stack spec (file name) because it publishes 36
// monthly SYNTHETIC electricity-consumption values for the nation, which makes
// the electricity section mixed-frequency for anything that runs later.
// The values are declared test inputs with a fixed seasonal pattern; they are
// not Omani statistics, and the page labels the result as a demonstration.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('a data manager publishes an eligible monthly synthetic series', async ({ page }) => {
  await signIn(page, 'manager@e2e.invalid');
  const status = await page.evaluate(async () => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const headers = { 'X-CSRF-Token': csrf };
    const json = { ...headers, 'Content-Type': 'application/json' };
    const season = [0.9, 0.85, 0.95, 1.05, 1.2, 1.35, 1.4, 1.38, 1.25, 1.1, 0.95, 0.9];
    // Fixed irregular component, so year-on-year changes vary and intervals can be estimated.
    const noise = [0, 21, -13, 34, -27, 8, 16, -30, 25, -6, 12, -19];
    const lines = ['indicator_code,area_code,period_start,period_end,frequency,unit_code,value'];
    for (let i = 0; i < 36; i += 1) {
      const year = 2022 + Math.floor(i / 12);
      const month = i % 12;
      const start = `${year}-${String(month + 1).padStart(2, '0')}-01`;
      const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
      const end = `${year}-${String(month + 1).padStart(2, '0')}-${String(last).padStart(2, '0')}`;
      lines.push(`ELEC_CONSUMPTION,OM,${start},${end},monthly,GWh,${(2000 * season[month] + 4 * i + noise[i % 11]).toFixed(1)}`);
    }
    const src = await (await fetch('/api/v1/sources', { method: 'POST', headers: json,
      body: JSON.stringify({ data_mode: 'synthetic', dataset_title: 'E2E monthly electricity (synthetic)', geographic_coverage: 'OM' }) })).json();
    const form = new FormData();
    form.set('source_id', src.id);
    form.set('version_label', 'monthly-elec-v1');
    form.set('file', new Blob([`${lines.join('\n')}\n`], { type: 'text/csv' }), 'monthly-elec.csv');
    const imp = await (await fetch('/api/v1/imports', { method: 'POST', headers, body: form })).json();
    const v = await (await fetch(`/api/v1/imports/${imp.id}/validate`, { method: 'POST', headers })).json();
    await fetch(`/api/v1/imports/${imp.id}/approve`, { method: 'POST', headers: json,
      body: JSON.stringify({ acknowledged_rejected_rows: v.rejected_row_count, note: 'e2e forecast series' }) });
    return (await fetch(`/api/v1/imports/${imp.id}/publish`, { method: 'POST', headers })).status;
  });
  expect(status).toBe(200);
});

test('an analyst runs a forecast: baseline comparison, intervals, labels and an assistant hand-off', async ({ page }) => {
  await signIn(page, 'analyst@e2e.invalid');
  await page.goto('/forecasts?mode=synthetic');
  const target = page.locator('[data-testid="forecast-target"][data-indicator="ELEC_CONSUMPTION"]');
  await expect(target).toHaveAttribute('data-status', 'available');
  await expect(page.getByTestId('forecast-unavailable')).toHaveCount(0);
  await target.getByTestId('run-forecast').click();

  const run = page.getByTestId('forecast-run');
  await expect(run).toHaveAttribute('data-status', 'succeeded', { timeout: 30_000 });
  await expect(run.getByTestId('estimate-label')).toContainText(/estimate/i);
  await expect(run.getByTestId('forecast-demo-label')).toContainText('Not a validated forecast for Oman');
  const meta = run.getByTestId('forecast-meta');
  await expect(meta).toContainText('2022-01-01');
  await expect(meta).toContainText('Training cutoff');
  await expect(meta).toContainText('monthly-elec-v1');
  // Three models were backtested on the same periods; the selection is stated.
  await expect(run.getByTestId('forecast-metrics').locator('tbody tr')).toHaveCount(3);
  await expect(run.getByTestId('forecast-metrics')).toContainText('baseline');
  await expect(run.getByTestId('selected-model')).not.toHaveText('—');
  // History and estimates are drawn differently; intervals are shaded.
  const chart = run.getByTestId('forecast-chart');
  await expect(chart.getByTestId('estimate-line')).toHaveAttribute('stroke-dasharray', '7 5');
  await expect(chart.getByTestId('band-80')).toHaveCount(1);
  await expect(chart.getByTestId('band-95')).toHaveCount(1);
  await expect(chart.getByTestId('cutoff-line')).toBeVisible();
  await expect(run.getByTestId('forecast-explanation')).toContainText('baseline');
  await run.getByTestId('forecast-assumptions').locator('summary').click();
  await expect(run.getByTestId('forecast-assumptions')).toContainText(/interval/i);

  // The assistant explains the stored result; the question is prefilled, not sent.
  await expect(run.getByTestId('explain-with-assistant')).toHaveAttribute('href', /\/assistant\?.*q=Explain/);

  // Arabic keeps the chart left-to-right and the labels translated.
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(run.getByTestId('forecast-chart').locator('svg')).toHaveCSS('direction', 'ltr');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('التنبؤات والسيناريوهات');
});

test('the scenario explorer is separate from forecasts and recalculates from the chosen assumptions', async ({ page }) => {
  await page.goto('/forecasts?mode=synthetic');
  const explorer = page.getByTestId('scenario-explorer');
  await expect(explorer.getByTestId('scenario-label')).toContainText('not a forecast');
  await page.getByTestId('scenario-series').selectOption({ label: 'Electricity generation · Oman (national)' });
  await page.getByTestId('scenario-growth').fill('5');
  await page.getByTestId('scenario-years').fill('2');
  await page.getByTestId('scenario-oneoff').fill('10');
  // 50,100 × 1.10 × 1.05^k, from the published synthetic 2002 value.
  await expect(explorer.getByTestId('scenario-summary')).toContainText('60,758.78');
  await expect(explorer.getByTestId('scenario-table').locator('tbody tr')).toHaveCount(2);
  await expect(explorer.getByTestId('scenario-table')).toContainText('57,865.5');
  await expect(explorer.getByTestId('forecast-chart').getByTestId('scenario-line')).toBeVisible();
  await expect(explorer.getByTestId('forecast-chart').getByTestId('estimate-line')).toHaveCount(0);
});
