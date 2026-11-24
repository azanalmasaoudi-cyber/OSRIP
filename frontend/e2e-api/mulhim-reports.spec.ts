import { expect, test, type Page } from '@playwright/test';

import { ask } from './chat';

// Reports without a Reports page in the navigation, through the real stack (scripted model,
// synthetic booklet data, real API and database): Al Mulhim builds a report from a request with
// OSRIP's own report service and shows it in the reply (headings, table, chart, calculations,
// findings to review, sources collapsed); anyone downloads its CSV; an analyst saves it as a
// frozen report whose PDF, Excel and CSV exports work and which then appears on its sector; a
// viewer cannot save one; saved report addresses keep working.

test.skip(({ isMobile }) => isMobile, 'desktop layout; a narrow screen is checked below');

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, username: string): Promise<void> {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username').fill(username);
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('the navigation has no Reports entry, and saved report addresses still open', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(nav.getByRole('link', { name: 'Al Mulhim', exact: true })).toBeVisible();
  for (const gone of ['Reports Dashboard', 'Reports', 'Saved reports', 'Export Center']) {
    await expect(nav.getByRole('link', { name: gone, exact: true })).toHaveCount(0);
  }
  await page.goto('/reports?mode=synthetic');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('reports-list').or(page.locator('[data-state="empty"]')).first()).toBeVisible();
  // A report that does not exist (or is someone else's private one) is "not found".
  await page.goto('/reports/00000000-0000-4000-8000-000000000000');
  await expect(page.locator('[data-state="empty"]')).toContainText('not visible to you');
  await expect(page.getByTestId('report')).toHaveCount(0);
});

test('a visitor asks for a report: built from published data, shown in the reply, CSV download', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Create a report on electricity generation in Oman.');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-intent')).toHaveText('Report');
  const report = reply.getByTestId('reply-report');
  await expect(report).toHaveAttribute('data-section', 'electricity');
  await expect(report).toHaveAttribute('data-type', 'sector');
  await expect(report.getByTestId('reply-report-title')).toContainText('Electricity report: Electricity generation');
  await expect(report.getByTestId('reply-report-scope')).toContainText('Oman (national)');
  // The published values, as a table and, for the main series, a chart named for what it shows.
  const series = report.getByTestId('reply-report-series').first();
  await expect(series).toHaveAttribute('data-indicator', 'ELEC_GENERATION');
  await expect(series.getByTestId('reply-report-row').last()).toContainText('50,100');
  await expect(series.getByTestId('forecast-chart')).toHaveAttribute('aria-label', /published values/);
  // Sources are kept but not spread over the conversation: one collapsed list.
  const sources = report.getByTestId('reply-report-sources');
  await expect(sources).toBeVisible();
  expect(await sources.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  // The text states only the published figure.
  await expect(reply).toContainText('50100');
  // CSV for everyone: the same rows, formula-safe.
  const [file] = await Promise.all([page.waitForEvent('download'), report.getByTestId('reply-report-csv').click()]);
  const csv = await (await file.createReadStream()).toArray().then((chunks) => Buffer.concat(chunks).toString('utf8'));
  expect(csv).toContain('Electricity generation');
  expect(csv).toContain(',50100,');
  // Saving needs an account with the report permission.
  await expect(report.getByTestId('reply-report-save')).toHaveCount(0);
  await expect(report.getByTestId('reply-report-save-note')).toContainText('Sign in to save this report');
});

test('an analyst saves the report: its PDF, Excel and CSV exports work, and it appears on its sector', async ({ page }) => {
  await signIn(page, 'e2eanalyst');
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Create a report on electricity generation in Oman.');
  const report = reply.getByTestId('reply-report');
  await report.getByTestId('reply-report-save').click();
  const saved = report.getByTestId('reply-report-saved');
  await expect(saved).toBeVisible();
  const id = (await saved.getAttribute('data-report')) ?? '';
  expect(id).toMatch(/^[0-9a-f-]{36}$/);
  for (const [testId, type] of [['reply-report-pdf', 'application/pdf'], ['reply-report-xlsx', 'spreadsheetml'], ['reply-report-export-csv', 'text/csv']] as const) {
    const href = (await saved.getByTestId(testId).getAttribute('href')) ?? '';
    const response = await page.request.get(href);
    expect(response.status(), testId).toBe(200);
    expect(response.headers()['content-type']).toContain(type);
  }
  // The saved report keeps its address and shows the same figures.
  await saved.getByTestId('reply-report-open').click();
  await expect(page).toHaveURL(new RegExp(`/reports/${id}`));
  await expect(page.getByTestId('report')).toContainText('50,100');
  // On its sector's Analysis: listed with the sector's saved reports, and opened from there.
  await page.goto('/energy/electricity?mode=synthetic');
  const list = page.getByTestId('sector-reports');
  await expect(list.getByTestId('sector-report-link').filter({ hasText: 'Electricity report: Electricity generation' }).first()).toBeVisible();
  await list.getByTestId('sector-report-link').first().click();
  await expect(page).toHaveURL(/\/reports\/[0-9a-f-]{36}/);
  // Private: a visitor gets nothing at that address.
  const anonymous = await page.context().browser()?.newContext();
  const other = await anonymous?.request.get(`${new URL(page.url()).origin}/api/v1/reports/${id}`);
  expect(other?.status()).toBe(404);
  await anonymous?.close();
});

test('a viewer cannot save a platform report, but can turn the answer into a downloadable report', async ({ page }) => {
  await signIn(page, 'e2eviewer');
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Create a report on electricity generation in Oman.');
  const report = reply.getByTestId('reply-report');
  await expect(report.getByTestId('reply-report-save')).toHaveCount(0);
  await expect(report.getByTestId('reply-report-save-note')).toContainText('cannot save platform reports');
  await reply.getByTestId('answer-report').click();
  await expect(reply.getByTestId('answer-report-created')).toBeVisible();
});

test('Arabic, right to left, dark and narrow: the report reads in Arabic and nothing scrolls sideways', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.theme', 'dark'));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const reply = await ask(page, 'أنشئ تقريرًا عن توليد الكهرباء');
  const report = reply.getByTestId('reply-report');
  await expect(report.getByTestId('reply-report-title')).toContainText('تقرير الكهرباء');
  await expect(report).toContainText('البيانات المنشورة');
  await expect(report.getByTestId('reply-report-csv')).toHaveText('تنزيل CSV');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('a sector asks Al Mulhim for a report on its current selection', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  await expect(page.getByTestId('sector-reports')).toBeVisible(); // on the guided analysis's first step
  await expect(page.getByTestId('sector-reports-all')).toHaveAttribute('href', /^\/reports/);
  // Al Mulhim's requests come with the analysis of a selection.
  await page.goto('/energy/electricity?mode=synthetic&ind=ELEC_GENERATION&at=OM&bd=%7C%7C&freq=annual&from=2001-01-01&to=2002-01-01&step=analysis');
  await page.getByTestId('sector-ask-report').click();
  await expect(page).toHaveURL(/\/assistant\?/);
  await expect(page.getByTestId('assistant-input')).toHaveValue(/^Create a report on .+ in .+\.$/);
  await expect(page.getByTestId('assistant-message')).toHaveCount(0); // never sent by itself
});
