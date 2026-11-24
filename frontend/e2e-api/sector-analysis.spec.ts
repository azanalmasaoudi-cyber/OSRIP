import { expect, test } from '@playwright/test';

// Each of the four sectors through the real stack: "Data and indicators" (cards, and the data
// freshness panel), "Guided analysis" (one step at a time: selection, results, analysis,
// objectives, recommendations; components/sector/SectorGuide) and "Tables and charts" (the
// period-first workflow). The guided analysis keeps its step, selection and objectives in the
// address. The old /workspace address opens a sector's guided analysis. The navigation has no
// separate Workspace, Studies or Forecasts entry (interface.spec.ts).

test.skip(({ isMobile }) => isMobile, 'desktop layout; the phone layout is in sector-phone.spec.ts');

const SECTORS = ['/energy/electricity', '/energy/water', '/food-security', '/trade'];
// The synthetic national electricity generation: 48,000 GWh in 2001 and 50,100 GWh in 2002.
const APPLIED = 'mode=synthetic&ind=ELEC_GENERATION&at=OM&bd=%7C%7C&freq=annual&from=2001-01-01&to=2002-01-01';

test('every sector has Data, the guided analysis and Tables and charts, opens on the guided analysis, and the tabs work by keyboard', async ({ page }) => {
  for (const path of SECTORS) {
    await page.goto(`${path}?mode=synthetic`);
    const tabs = page.getByTestId('sector-tabs');
    await expect(tabs.getByRole('tab')).toHaveText(['Data and indicators', 'Guided analysis', 'Tables and charts']);
    const tab = (id: string) => tabs.locator(`[data-tab="${id}"]`);
    await expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-guide').or(page.getByTestId('sector-no-data'))).toBeVisible();
    // One panel at a time: the arrows and Home move along the tabs.
    await tab('analysis').focus();
    await page.keyboard.press('ArrowRight');
    await expect(tab('charts')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-guide')).toHaveCount(0);
    await page.keyboard.press('Home');
    await expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-indicators')).toBeVisible();
    await expect(page).toHaveURL(/tab=data/);
  }
});

test('Data and indicators: cards and the data freshness panel; Analyse starts the guided analysis on that indicator', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic&tab=data');
  const data = page.getByTestId('sector-indicators');
  const card = data.locator('[data-testid="indicator-card"][data-indicator="ELEC_GENERATION"]').first();
  await expect(card).toContainText('gigawatt');
  await expect(card.getByTestId('indicator-stale')).toBeVisible(); // old data is flagged, never hidden
  // Freshness: period end, unit, scope, publication and retrieval, review status and source.
  const source = page.getByTestId('workspace-sources').getByTestId('workspace-source').first();
  await expect(source).toContainText('No publisher (synthetic data)');
  const fields = source.getByTestId('freshness');
  for (const field of ['period_end', 'unit', 'geographic_scope', 'publication_date', 'retrieved_at', 'review_status', 'source_url']) {
    await expect(fields.locator(`[data-field="${field}"]`)).toBeVisible();
  }
  await expect(fields.locator('[data-field="review_status"]')).toHaveText('Synthetic demonstration data');
  await card.getByTestId('indicator-analyse').click();
  await expect(page.getByTestId('sector-tabs').locator('[data-tab="analysis"]')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-step', 'select');
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-indicator', 'ELEC_GENERATION');
  // Verified mode: no verified trade data is published here, and the sector says so.
  await page.goto('/trade?tab=data');
  await expect(page.locator('[data-state="no_verified_data"]').first()).toBeVisible();
});

test('the guided analysis, one step at a time: selection, results, analysis, objectives, recommendations', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const guide = page.getByTestId('sector-guide');
  await expect(guide).toHaveAttribute('data-step', 'select');
  await expect(page.getByTestId('guide-step-select')).toHaveAttribute('data-state', 'current');
  await expect(page.getByTestId('guide-step-results')).toHaveAttribute('data-state', 'upcoming');
  // Nothing analytical before the results are asked for.
  for (const id of ['sector-results', 'sector-analysis', 'guide-objectives', 'guide-recommendations', 'sector-chart', 'sector-findings']) {
    await expect(page.getByTestId(id)).toHaveCount(0);
  }
  await page.getByTestId('sector-indicator').selectOption('ELEC_GENERATION');
  await expect(page.getByTestId('guide-governorate')).toHaveValue('OM');
  await page.getByTestId('sector-show-results').click();
  await expect(page.getByTestId('sector-error')).toBeVisible(); // a period first
  await page.getByTestId('sector-from').selectOption('2001-01-01');
  await page.getByTestId('sector-to').selectOption('2002-01-01');
  await page.getByTestId('sector-show-results').click();

  // 2. Results: the published values, their unit and coverage; no analysis yet.
  await expect(guide).toHaveAttribute('data-step', 'results');
  await expect(page).toHaveURL(/step=results/);
  await expect(page).toHaveURL(/ind=ELEC_GENERATION/);
  await expect(page.getByTestId('applied-details')).toContainText('gigawatt');
  await expect(page.getByTestId('summary-latest')).toContainText(/50,?100/);
  await expect(page.getByTestId('guide-sources')).toBeVisible();
  await expect(page.getByTestId('sector-analysis')).toHaveCount(0);
  await expect(page.getByTestId('guide-step-select')).toHaveAttribute('data-state', 'done');
  await page.getByTestId('guide-analyze').click();

  // 3. Analysis: the server's findings and calculations; the chart only on request.
  await expect(guide).toHaveAttribute('data-step', 'analysis');
  await expect(page.getByTestId('sector-findings').getByTestId('selection-study')).toBeVisible();
  await expect(page.getByTestId('guide-limitations')).toBeVisible();
  await expect(page.getByTestId('sector-chart')).toHaveCount(0);
  await page.getByTestId('sector-show-chart').click();
  await expect(page.getByTestId('sector-chart')).toBeVisible();
  await expect(page.getByTestId('sector-ask-forecast')).toHaveAttribute('href', /^\/assistant\?/);
  // The browser's Back and Forward move between the steps.
  await page.goBack();
  await expect(guide).toHaveAttribute('data-step', 'results');
  await page.goForward();
  await expect(guide).toHaveAttribute('data-step', 'analysis');
  await page.getByTestId('guide-set-objectives').click();

  // 4. Objectives: no recommendation until one is chosen or written.
  await expect(guide).toHaveAttribute('data-step', 'objectives');
  await page.getByTestId('guide-show-recommendations').click();
  await expect(page.getByTestId('guide-need-objective')).toBeVisible();
  await expect(guide).toHaveAttribute('data-step', 'objectives');
  await expect(page.getByTestId('guide-recommendations')).toHaveCount(0);
  await page.getByTestId('guide-objective-reduce_shortages').check();
  await page.getByTestId('guide-objective-diversify').check();
  await page.getByTestId('guide-show-recommendations').click();

  // 5. Recommendations: ranked, with why, prerequisites, risks and missing evidence.
  await expect(guide).toHaveAttribute('data-step', 'recommendations');
  await expect(page).toHaveURL(/goals=reduce_shortages%2Cdiversify/);
  await expect(page.getByTestId('guide-facts')).toContainText('Change from 2001 to 2002: +4.4%.');
  const first = page.getByTestId('guide-action').first();
  await expect(first).toHaveAttribute('data-rank', '1');
  await expect(first).toHaveAttribute('data-objective', 'reduce_shortages');
  await expect(first).toContainText('is rising');
  await expect(first).toContainText('Needed first');
  await expect(page.getByTestId('guide-action').last()).toHaveAttribute('data-evidence', 'gap');
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('guide-download-csv').click()]);
  expect(download.suggestedFilename()).toBe('osrip-recommendations-electricity-ELEC_GENERATION-OM.csv');
  await expect(page.getByTestId('guide-full-report')).toHaveAttribute('href', /\/assistant\?.*Create\+a\+report/);

  // A reload (or a shared link) returns to the same step, selection and objectives.
  await page.reload();
  await expect(guide).toHaveAttribute('data-step', 'recommendations');
  await expect(page.getByTestId('guide-objectives-chosen')).toContainText('Reduce shortages');
  // Change the objectives, then start again: the objectives go, the selection stays chosen.
  await page.getByTestId('guide-back').click();
  await expect(page.getByTestId('guide-objective-diversify')).toBeChecked();
  await page.getByTestId('guide-step-select').getByRole('button').click();
  await expect(guide).toHaveAttribute('data-step', 'select');
  await expect(page.getByTestId('sector-from')).toHaveValue('2001-01-01');
});

test('an address asks only for what it can show: no results before a selection, no recommendations before an objective', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic&step=analysis');
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-step', 'select');
  await page.goto(`/energy/electricity?${APPLIED}&step=recommendations`);
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-step', 'objectives');
  // An objective written in the person's own words is matched by fixed rules.
  await page.getByTestId('guide-goal').fill('We want less waste in the network');
  await page.getByTestId('guide-show-recommendations').click();
  await expect(page.getByTestId('guide-goal-echo')).toContainText('less waste');
  await expect(page.getByTestId('guide-objectives-chosen')).toContainText('Improve efficiency');
  // Words that match no objective give no rule-based recommendation, and say so.
  await page.goto(`/energy/electricity?${APPLIED}&step=recommendations&goal=something+nice`);
  await expect(page.getByTestId('guide-goal-not-recognised')).toBeVisible();
  await expect(page.getByTestId('guide-action')).toHaveCount(0);
});

test('the old /workspace address opens the sector\'s guided analysis, keeping only safe filters', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic&section=electricity&indicator=ELEC_GENERATION&frequency=annual&q=%3Cscript%3E');
  await expect(page).toHaveURL(/\/energy\/electricity\?/);
  await expect(page).toHaveURL(/mode=synthetic/);
  await expect(page).not.toHaveURL(/q=|script/);
  await expect(page.getByTestId('sector-guide')).toHaveAttribute('data-indicator', 'ELEC_GENERATION');
  await expect(page).not.toHaveURL(/indicator=/); // read once into the selection, then removed
  await page.goto('/workspace?mode=synthetic&section=water');
  await expect(page).toHaveURL(/\/energy\/water\?/);
  await page.goto('/workspace?indicator=..%2F..%2Fetc');
  await expect(page).toHaveURL(/\/energy\/electricity/);
  await expect(page).not.toHaveURL(/etc/);
});

test('Arabic, right to left and dark: the steps and Al Mulhim\'s requests in Arabic, nothing scrolls sideways', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.theme', 'dark'));
  await page.goto('/energy/water?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const tabs = page.getByTestId('sector-tabs');
  await expect(tabs.getByRole('tab')).toHaveText(['البيانات والمؤشرات', 'التحليل الموجَّه', 'الجداول والرسوم البيانية']);
  await expect(page.getByTestId('guide-steps').getByRole('listitem')).toHaveText(['1الاختيار', '2النتائج', '3التحليل', '4الأهداف', '5التوصيات']);
  // Right to left, the arrow that moves forward is the left one.
  await tabs.locator('[data-tab="analysis"]').focus();
  await page.keyboard.press('ArrowLeft');
  await expect(tabs.locator('[data-tab="charts"]')).toHaveAttribute('aria-selected', 'true');
  await page.goto(`/energy/electricity?${APPLIED}&step=analysis`);
  await expect(page.getByTestId('sector-ask-mulhim')).toContainText('اسأل المُلْهِم');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByTestId('guide-set-objectives').click();
  await expect(page.getByTestId('guide-objective-list')).toContainText('تقليل العجز');
  await page.getByTestId('sector-guide').getByRole('heading', { level: 2 }).first().focus();
  await page.getByRole('button', { name: 'English' }).first().click();
});
