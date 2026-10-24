import { expect, test, type Page } from '@playwright/test';

import { closeDrawer, openChatSettings, openTools } from './chat';

// The shortage and surplus analysis, an optional tool of the AI Assistant page (Tools), through
// the real stack (scripted assistant and speech providers): "Run analysis" runs the server's
// analysis, and the results area shows its summary, tables, charts, sources and recommendation
// table from the one stored document. The voice check is in the conversation settings.

async function openAnalysis(page: Page): Promise<void> {
  await openTools(page);
  await page.getByTestId('open-analysis').click();
  await expect(page.getByTestId('chat-tools-sheet')).toBeHidden(); // Tools closes first
  await expect(page.getByTestId('analysis-form')).toBeVisible();
}

async function runAnalysis(page: Page, sector: string, explain = false): Promise<string> {
  if (!(await page.getByTestId('analysis-form').isVisible())) await openAnalysis(page);
  await expect(page.getByTestId('analysis-form')).toBeVisible();
  const box = page.getByTestId('analysis-explain');
  if (await box.count()) await box.setChecked(explain);
  await page.getByTestId('sector-select').selectOption(sector);
  const done = page.waitForResponse((r) => r.url().endsWith('/api/v1/analysis/balance') && r.request().method() === 'POST');
  await page.getByTestId('run-analysis').click();
  const response = await done;
  expect(response.status()).toBe(201);
  const body = (await response.json()) as { id: string };
  await expect(page.getByTestId('results-panel')).toHaveAttribute('data-kind', 'balance');
  return body.id;
}

interface Analysis {
  balances: { status: string; gap: string | null; table: { columns: { key: string; kind: string }[]; rows: Record<string, string | null>[] }; charts: unknown[] }[];
  sources: { id: string; dataset_version: string }[];
  recommendations: { cost_known: boolean; cost: { en: string } }[];
}

test('run analysis: summary, tables, charts, sources and recommendations agree with the stored result', async ({ page }) => {
  // Synthetic mode: the booklet fixtures publish trade values on both sides for this test database.
  await page.goto('/assistant?mode=synthetic');
  const id = await runAnalysis(page, 'trade');
  const stored = await page.request.get(`/api/v1/analysis/balance/${id}`);
  const a = ((await stored.json()) as { analysis: Analysis }).analysis;

  // The balance is exports minus imports, row by row; a missing side is never zero.
  for (const b of a.balances) {
    for (const row of b.table.rows) {
      if (row.exports != null && row.imports != null) {
        expect(Number(row.balance)).toBeCloseTo(Number(row.exports) - Number(row.imports), 6);
      } else {
        expect(row.balance ?? null).toBeNull();
      }
    }
  }
  const panel = page.getByTestId('results-panel');
  // The summary states the merchandise balance only when the data determine it.
  const merchandise = a.balances[0];
  if (merchandise && merchandise.status !== 'not_determinable') {
    await expect(panel.getByTestId('results-summary-text')).toContainText('Merchandise trade in');
  } else {
    await expect(panel.getByTestId('results-summary-text')).not.toContainText('Merchandise trade in');
  }
  await expect(panel.getByTestId('results-summary-text')).toContainText('not guaranteed outcomes');
  await expect(panel.getByTestId('results-card')).toHaveCount(a.balances.length);
  for (const [i, b] of a.balances.entries()) {
    await expect(panel.getByTestId('results-card').nth(i)).toHaveAttribute('data-status', b.status);
  }

  await panel.getByRole('tab', { name: /^Tables/ }).click();
  await expect(panel.getByTestId('results-table')).toHaveCount(a.balances.length);
  const firstRows = a.balances[0]?.table.rows.length ?? 0;
  await expect(panel.getByTestId('results-table').first().getByTestId('study-row')).toHaveCount(firstRows);

  await panel.getByRole('tab', { name: /^Charts/ }).click();
  const charts = panel.getByTestId('results-chart');
  await expect(charts).toHaveCount(a.balances.reduce((n, b) => n + b.charts.length, 0));
  for (const meta of await panel.getByTestId('results-chart-meta').allTextContents()) {
    expect(meta).toMatch(/Unit: .+ · Periods: .+ · Sources: .+/);
  }

  await panel.getByRole('tab', { name: /^Sources/ }).click();
  expect(a.sources.length).toBeGreaterThan(0);
  await expect(panel.getByTestId('results-source')).toHaveCount(a.sources.length);
  await expect(panel.getByTestId('results-source').first()).toContainText(a.sources[0]?.dataset_version ?? 'missing');

  await panel.getByRole('tab', { name: /^Recommendations/ }).click();
  const table = panel.getByTestId('results-recommendation-table');
  await expect(table.locator('th')).toHaveText([
    'Issue', 'Evidence', 'Proposed action', 'Quantity / unit', 'Feasibility constraints', 'Time horizon', 'Cost evidence',
    'Expected effect and assumptions', 'Priority', 'Monitoring KPI',
  ]);
  await expect(table.getByTestId('recommendation-row')).toHaveCount(a.recommendations.length);
  expect(a.recommendations.every((r) => !r.cost_known && r.cost.en.startsWith('Unknown'))).toBe(true);
  await expect(panel.getByTestId('results-decision-support')).toContainText('not guaranteed outcomes');

  // Downloads: the CSV and the report hold the same document, safely.
  const csv = await page.request.get((await panel.getByTestId('results-csv').getAttribute('href')) ?? '');
  expect(csv.status()).toBe(200);
  const text = await csv.text();
  expect(text).toContain('Proposed action');
  expect(text.split('\n').some((line) => /^[=+@]/.test(line))).toBe(false);
  const report = await page.request.get((await panel.getByTestId('results-report').getAttribute('href')) ?? '');
  expect(report.headers()['content-security-policy']).toContain("default-src 'none'");
  expect(await report.text()).not.toContain('<script');
});

test('without peak demand, electricity states no shortage and names the missing information', async ({ page }) => {
  await page.goto('/assistant');
  await runAnalysis(page, 'electricity');
  const panel = page.getByTestId('results-panel');
  await expect(panel).toHaveAttribute('data-status', 'not_available');
  await expect(panel.getByTestId('results-gaps')).toContainText('peak demand (MW)');
  for (const card of await panel.getByTestId('results-card').all()) await expect(card).toHaveAttribute('data-status', 'not_determinable');
  await panel.getByRole('tab', { name: /^Recommendations/ }).click();
  const first = panel.getByTestId('recommendation-row').first();
  await expect(first).toHaveAttribute('data-nature', 'data_improvement');
  await expect(first.getByTestId('priority')).toHaveAttribute('data-priority', 'high');
  await expect(panel.locator('[data-testid="recommendation-row"][data-nature="conditional_option"]').first()).toBeVisible();
});

test('Arabic, right to left, light theme and a phone screen', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.theme', 'light'));
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await runAnalysis(page, 'food_security');
  const panel = page.getByTestId('results-panel');
  await expect(panel.locator('h2')).toHaveText('العجز والفائض: الأمن الغذائي');
  await panel.getByRole('tab', { name: /^التوصيات/ }).click();
  // On a phone each recommendation is a card with the same ten fields.
  await expect(panel.getByTestId('recommendation-card').first()).toContainText('الإجراء المقترح');
  await expect(panel.getByTestId('recommendation-card').first()).toContainText('مؤشر المتابعة');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('voice: the persona voice is checked and tested, and audio can be stopped', async ({ page }) => {
  await page.goto('/assistant');
  await page.getByTestId('chat-header').getByTestId('persona-option-ilham').click();
  await openChatSettings(page);
  await page.getByTestId('voice-details').locator('summary').click();
  const voice = page.getByTestId('voice-panel');
  await expect(voice).toHaveAttribute('data-configured', 'true');
  await expect(voice.getByTestId('voice-name-ar')).toHaveText('ar-OM-AyshaNeural');
  await expect(voice.getByTestId('voice-name-en')).toHaveText('en-GB-SoniaNeural');
  await expect(voice.getByTestId('voice-verified')).toHaveCount(2);
  await voice.getByTestId('voice-test-language').getByRole('radio', { name: 'العربية' }).click();
  const tested = page.waitForResponse((r) => r.url().endsWith('/api/v1/assistant/voice/test'));
  await voice.getByTestId('voice-test').click();
  const response = await tested;
  expect(response.headers()['x-voice']).toBe('ar-OM-AyshaNeural');
  // The words spoken are shown as a transcript beside the player.
  await expect(voice.getByTestId('voice-transcript')).toContainText('هذا اختبار للصوت');
  await expect(voice.getByTestId('voice-test-state')).toHaveAttribute('data-state', /playing|idle/);
  // Stop audio (status bar) stops any playback on the page.
  if (await page.getByTestId('stop-audio').isVisible()) await page.getByTestId('stop-audio').click();
  await expect(voice.getByTestId('voice-test-state')).toHaveAttribute('data-state', 'idle');
  await expect(page.getByTestId('assistant-status-bar')).toHaveAttribute('data-state', 'idle');
  await closeDrawer(page);
  await page.getByTestId('chat-header').getByTestId('persona-option-mulhim').click();
});

test('a suggested question for the chosen sector is asked in the conversation, without a chart', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await openAnalysis(page);
  await page.getByTestId('sector-select').selectOption('water');
  await expect(page.getByTestId('sector-suggestions')).toHaveAttribute('data-sector', 'water');
  const question = (await page.getByTestId('sector-question').first().textContent()) ?? '';
  await page.getByTestId('sector-question').first().click();
  // The analysis closes and the question is answered in the conversation.
  await expect(page.getByTestId('analysis-form')).toBeHidden();
  await expect(page.getByTestId('user-message').first()).toHaveText(question);
  await expect(page.getByTestId('assistant-message').last()).not.toHaveAttribute('data-status', '');
  await expect(page.getByTestId('inline-chart')).toHaveCount(0); // no chart unless asked for
});
