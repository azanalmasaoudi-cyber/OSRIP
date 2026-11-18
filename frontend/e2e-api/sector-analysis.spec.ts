import { expect, test } from '@playwright/test';

// Each of the four sectors holds what the Analysis Workspace offered, for that sector only,
// through the real stack: "Data and indicators" (cards with unit, period, source and freshness),
// "Analysis" (the current selection, the server's validated findings, governorates compared
// where that is valid, Al Mulhim's requests and this session's studies) and "Tables and charts"
// (the period-first workflow). The old /workspace address opens a sector's Analysis. The
// navigation has no separate Workspace, Studies or Forecasts entry (interface.spec.ts).

test.skip(({ isMobile }) => isMobile, 'desktop layout; the phone layout is in sector-phone.spec.ts');

const SECTORS = ['/energy/electricity', '/energy/water', '/food-security', '/trade'];

test('every sector has Data, Analysis and Tables and charts, opens on its Analysis, and the tabs work by keyboard', async ({ page }) => {
  for (const path of SECTORS) {
    await page.goto(`${path}?mode=synthetic`);
    const tabs = page.getByTestId('sector-tabs');
    await expect(tabs.getByRole('tab')).toHaveText(['Data and indicators', 'Analysis', 'Tables and charts']);
    const tab = (id: string) => tabs.locator(`[data-tab="${id}"]`);
    await expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-analysis').or(page.getByTestId('sector-no-data'))).toBeVisible();
    // One panel at a time: the arrows and Home move along the tabs.
    await tab('analysis').focus();
    await page.keyboard.press('ArrowRight');
    await expect(tab('charts')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-analysis')).toHaveCount(0);
    await page.keyboard.press('Home');
    await expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sector-indicators')).toBeVisible();
    await expect(page).toHaveURL(/tab=data/);
  }
});

test('Data and indicators: cards with unit, period, source and freshness; Analyse opens the Analysis for that indicator', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic&tab=data');
  const data = page.getByTestId('sector-indicators');
  await expect(data.getByTestId('filter-area')).toBeVisible();
  await expect(data.getByTestId('filter-frequency')).toBeVisible();
  const card = data.locator('[data-testid="indicator-card"][data-indicator="ELEC_GENERATION"]').first();
  await expect(card).toContainText('gigawatt');
  await expect(card.getByTestId('source-details-button')).toBeVisible();
  // Old data is flagged, never hidden.
  await expect(card.getByTestId('indicator-stale')).toBeVisible();
  await expect(data.getByTestId('workspace-stale')).toBeVisible();
  await expect(page.getByTestId('workspace-sources').getByTestId('workspace-source').first()).toContainText('No publisher (synthetic data)');
  await card.getByTestId('indicator-analyse').click();
  await expect(page.getByTestId('sector-tabs').locator('[data-tab="analysis"]')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('sector-analysis')).toHaveAttribute('data-indicator', 'ELEC_GENERATION');
  // Verified mode: no verified trade data is published here, and the sector says so.
  await page.goto('/trade?tab=data');
  await expect(page.locator('[data-state="no_verified_data"]').first()).toBeVisible();
  await expect(page.getByTestId('indicator-card')).toHaveCount(0);
});

test('Analysis: the selection, validated findings, the comparison, the same selection in Tables and charts, and Al Mulhim\'s request', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const analysis = page.getByTestId('sector-analysis');
  await page.getByTestId('analysis-indicator').selectOption('ELEC_GENERATION');
  await expect(analysis).toHaveAttribute('data-indicator', 'ELEC_GENERATION');
  await expect(page.getByTestId('sector-analysis-title')).toHaveText('Electricity generation');
  // The server's findings for this selection (nothing here is written by AI), the comparison of
  // governorates (honestly empty: too few publish their own value) and no studies yet.
  await expect(page.getByTestId('sector-findings').getByTestId('selection-study')).toBeVisible();
  await expect(page.getByTestId('workspace-geography-none')).toBeVisible();
  await expect(page.getByTestId('recent-studies-empty')).toBeVisible();
  // Tables and charts open on the same selection.
  await page.getByTestId('sector-open-charts').click();
  await expect(page.getByTestId('sector-indicator')).toHaveValue('ELEC_GENERATION');
  // Al Mulhim: the request is written for this selection, and nothing is sent by itself.
  await page.getByTestId('sector-tabs').locator('[data-tab="analysis"]').click();
  await page.getByTestId('sector-ask-forecast').click();
  await expect(page).toHaveURL(/\/assistant\?/);
  await expect(page.getByTestId('assistant-input')).toHaveValue(/^Forecast Electricity generation in /);
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
});

test('the old /workspace address opens the sector\'s Analysis, keeping only safe filters', async ({ page }) => {
  // An indicator other than the one the sector opens on, from those published here.
  await page.goto('/energy/electricity?mode=synthetic');
  const analysis = page.getByTestId('sector-analysis');
  const first = await analysis.getAttribute('data-indicator');
  const codes = await page.getByTestId('analysis-indicator').locator('option').evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
  const other = codes.find((c) => c !== first) ?? '';
  expect(other).not.toBe('');
  await page.goto(`/workspace?mode=synthetic&section=electricity&indicator=${other}&frequency=annual&q=%3Cscript%3E`);
  await expect(page).toHaveURL(/\/energy\/electricity\?/);
  await expect(page).toHaveURL(/mode=synthetic/);
  await expect(page).not.toHaveURL(/q=|script/);
  await expect(analysis).toHaveAttribute('data-indicator', other);
  await expect(page).not.toHaveURL(/indicator=/); // read once into the selection, then removed
  await page.goto('/workspace?mode=synthetic&section=water');
  await expect(page).toHaveURL(/\/energy\/water\?/);
  await page.goto('/workspace?mode=synthetic&domain=trade');
  await expect(page).toHaveURL(/\/trade\?/);
  // An indicator code that is not one is dropped, never passed on.
  await page.goto('/workspace?indicator=..%2F..%2Fetc');
  await expect(page).toHaveURL(/\/energy\/electricity/);
  await expect(page).not.toHaveURL(/etc/);
});

test('Arabic, right to left and dark: the tabs and Al Mulhim\'s requests in Arabic, nothing scrolls sideways', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.theme', 'dark'));
  await page.goto('/energy/water?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const tabs = page.getByTestId('sector-tabs');
  await expect(tabs.getByRole('tab')).toHaveText(['البيانات والمؤشرات', 'التحليل', 'الجداول والرسوم البيانية']);
  // Right to left, the arrow that moves forward is the left one.
  await tabs.locator('[data-tab="analysis"]').focus();
  await page.keyboard.press('ArrowLeft');
  await expect(tabs.locator('[data-tab="charts"]')).toHaveAttribute('aria-selected', 'true');
  await tabs.locator('[data-tab="analysis"]').click();
  await expect(page.getByTestId('sector-ask-mulhim')).toContainText('اسأل المُلْهِم');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByTestId('sector-ask-study').click();
  await expect(page.getByTestId('assistant-input')).toHaveValue(/^أنشئ دراسة مفصلة عن /);
  await page.getByRole('button', { name: 'English' }).first().click();
});
