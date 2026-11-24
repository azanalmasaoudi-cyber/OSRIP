import { expect, test, type Locator, type Page, type Route } from '@playwright/test';

import { ask, closeDrawer, openTools } from './chat';

// Al Mulhim runs studies, forecasts and hypothetical scenarios from a sentence and shows their
// results inside the conversation, through the real stack (scripted assistant and search, fake
// speech, the synthetic booklet data): the study itself (method, findings, table, limitations),
// the forecasting engine's estimate or the reasons none is made, and a scenario's table and
// chart labelled hypothetical. A reply's live study (steps, sources, validated tables and the
// narration highlighting the row it reads) opens under the reply. Stale events of a stopped or
// superseded study and a table that fails validation are exercised with a crafted stream.

test.skip(({ isMobile }) => isMobile, 'desktop layout; the phone layout is in sector-phone.spec.ts');

const digits = (s: string | null) => (s ?? '').replace(/[^\d.]/g, '');

/** An answer mode for the next questions, from the Tools drawer. */
async function chooseMode(page: Page, name: string) {
  await openTools(page);
  await page.getByTestId('chat-tools-sheet').getByTestId('assistant-mode').getByRole('radio', { name }).click();
  await closeDrawer(page);
}

/** The live study under a reply, opened with its button. */
async function openStudy(reply: Locator) {
  await reply.getByTestId('open-study').click();
  return reply.getByTestId('reply-live-study').getByTestId('live-study');
}

// ------------------------------------------------------------------ studies, forecasts, scenarios

test('a study request runs the study and shows it in the reply; its saved link still opens it', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Create a detailed study of electricity generation in Oman.');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-intent')).toHaveText('Study');
  const study = reply.getByTestId('reply-study').first();
  const view = study.getByTestId('study-view');
  await expect(view).toBeVisible();
  // Title, question, method, findings, the table of published values and the limitations.
  await expect(view.getByRole('heading', { level: 3 }).first()).toContainText('Electricity generation');
  await expect(view.getByTestId('study-findings')).toBeVisible();
  await expect(view.getByTestId('study-limitations')).toBeVisible();
  const values = (await view.getByTestId('study-row').allTextContents()).map(digits).join(' ');
  expect(values).toContain('50100');
  // The stored study is the same document at its own address (saved study links keep working).
  await study.getByTestId('reply-study-link').click();
  await expect(page).toHaveURL(/\/studies\/[0-9a-f-]{36}/);
  await expect(page.getByTestId('study-view')).toBeVisible();
  await expect(page.getByTestId('study-findings')).toBeVisible();
});

test('a forecast request asks the forecasting engine: an estimate with its method, or the reasons there is none', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Forecast electricity generation in Oman.');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-intent')).toHaveText('Forecast');
  const forecast = reply.getByTestId('reply-forecast');
  await expect(forecast).toHaveCount(1); // one card per series, the most informative
  const status = await forecast.getAttribute('data-status');
  if (status === 'ok') {
    await expect(forecast.getByTestId('reply-forecast-method')).toBeVisible();
    await expect(reply).toContainText('not an official statistic');
  } else {
    // Too short a history: no number at all, and the reasons from the engine's policy.
    expect(status).toBe('withheld');
    await expect(forecast.getByTestId('reply-forecast-reasons')).toBeVisible();
    await expect(forecast.locator('svg[role="img"]')).toHaveCount(0);
    await expect(reply).toContainText('No forecast is produced');
  }

  // The same in Arabic, right to left.
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const arabic = await ask(page, 'تنبأ بتوليد الكهرباء في عمان');
  await expect(arabic).toHaveAttribute('data-status', 'answered');
  await expect(arabic.getByTestId('reply-forecast')).toHaveAttribute('data-status', status ?? '');
  await expect(arabic).toContainText(status === 'ok' ? 'تقدير نموذج' : 'لا يُنتَج تنبؤ');
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('a scenario applies the stated change to the published base, labelled hypothetical; a missing change is asked for', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'What happens if electricity generation increases by 15% over five years?');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  // Answered in Scenario mode (the badge names the mode; the intent badge appears only when it differs).
  await expect(reply.getByTestId('reply-mode')).toHaveText('Scenario');
  await expect(reply.getByTestId('reply-intent')).toHaveCount(0);
  const scenario = reply.getByTestId('reply-scenario');
  await expect(scenario).toHaveCount(1);
  await expect(scenario.getByTestId('reply-scenario-label')).toContainText(/hypothetical/i);
  await expect(scenario.getByTestId('reply-scenario-assumptions')).toBeVisible();
  await expect(scenario.getByTestId('forecast-chart')).toHaveAttribute('aria-label', /hypothetical scenario \(not a forecast\)/);
  await expect(scenario.getByTestId('reply-scenario-table').locator('tbody tr')).toHaveCount(5);
  await expect(reply).toContainText('Hypothetical scenario, not a forecast');
  // Without a stated change nothing is assumed: Al Mulhim asks for it.
  const unclear = await ask(page, 'Create a scenario for electricity generation.');
  await expect(unclear).toHaveAttribute('data-status', 'clarification');
  await expect(unclear.getByTestId('reply-scenario')).toHaveCount(0);
});

// ------------------------------------------------------------------ the live study under a reply

test('a live study streams steps, sources and a validated table under its reply; narration highlights its row', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'What is the latest electricity generation?');
  const study = await openStudy(reply);
  await expect(study).toHaveAttribute('data-status', 'completed');
  const stages = await study.getByTestId('study-progress').locator('li').evaluateAll((l) => l.map((x) => x.getAttribute('data-stage')));
  expect(stages).toEqual(expect.arrayContaining(['received', 'published_data', 'validating_data', 'checking']));
  await expect(study.getByTestId('study-source')).toHaveCount(1);
  const dataset = study.getByTestId('study-datasets').getByTestId('dataset');
  await expect(dataset).toHaveAttribute('data-state', 'final');
  // The finding, the table and the narration state the same number.
  const finding = study.getByTestId('study-finding').first();
  const row = dataset.getByTestId('study-row').first();
  const value = await row.locator('td').nth(1).textContent();
  expect(digits(await finding.textContent())).toContain(digits(value));
  // Playing reads segment by segment; the row and the source it is about light up.
  const narration = study.getByTestId('narration');
  await expect(narration).toHaveAttribute('data-mode', 'server');
  await narration.getByTestId('narration-play').click();
  await expect(narration).toHaveAttribute('data-segment', 'N1');
  await expect(row).toHaveAttribute('data-highlighted', 'true');
  await expect(finding).toHaveAttribute('data-highlighted', 'true');
  await expect(study.getByTestId('study-source').first()).toHaveAttribute('data-highlighted', 'true');
  // Interrupt: stop the narration; the highlight stays on the sentence reached.
  await narration.getByTestId('narration-stop').click();
  await expect(narration).toHaveAttribute('data-playing', 'false');
  await expect(row).toHaveAttribute('data-highlighted', 'true');
  // The study closes again with the same button.
  await reply.getByTestId('open-study').click();
  await expect(reply.getByTestId('reply-live-study')).toHaveCount(0);
});

test('a failed search is a visible partial failure; sources open and close by keyboard', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await chooseMode(page, 'Deep research');
  const failed = await openStudy(await ask(page, 'web search that will fail'));
  await expect(failed).toHaveAttribute('data-status', 'completed');
  await expect(failed.locator('[data-testid="study-warning"][data-code="search_failed"]')).toBeVisible();
  await expect(failed.locator('[data-testid="study-search"][data-status="failed"]')).toBeVisible();
  await expect(failed.getByTestId('study-datasets')).toHaveCount(0);

  // Deep research works from the web only: OSRIP's published data are asked in Data analysis.
  await chooseMode(page, 'Data analysis');
  const study = await openStudy(await ask(page, 'What is the latest electricity generation?'));
  await expect(study).toHaveAttribute('data-status', 'completed');
  const source = study.getByTestId('study-source').first().getByRole('button');
  await source.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByTestId('study-source-details')).toContainText('Synthetic demonstration data');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(source).toBeFocused();
});

test('a sector lists this session\'s studies; one opens again under its reply, and Arabic keeps the values', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const first = await openStudy(await ask(page, 'What is the latest electricity generation?'));
  await expect(first).toHaveAttribute('data-status', 'completed');
  const firstId = await first.getAttribute('data-study');
  const second = await openStudy(await ask(page, 'What is the latest water production?'));
  await expect(second).toHaveAttribute('data-status', 'completed');
  expect(await second.getAttribute('data-study')).not.toBe(firstId);
  // Each reply keeps its own study: there is no study picker under a reply.
  await expect(page.getByTestId('study-history')).toHaveCount(0);

  // The sector's guided analysis lists both on its first step; the older one opens under its reply.
  await page.goto('/energy/electricity?mode=synthetic');
  const recent = page.getByTestId('recent-studies').getByTestId('recent-study-open');
  await expect(recent).toHaveCount(2);
  await recent.last().click();
  await expect(page).toHaveURL(new RegExp(`/assistant\\?.*study=${firstId}`));
  const reopened = page.locator(`[data-testid="live-study"][data-study="${firstId}"]`);
  await expect(reopened).toHaveAttribute('data-status', 'completed');
  await expect(reopened.getByTestId('study-finding').first()).toContainText('50100');
  // Arabic: labels change, the table's values do not.
  const values = await reopened.getByTestId('study-datasets').getByTestId('study-row').allTextContents();
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(reopened.getByTestId('study-findings-panel')).toContainText('النتائج');
  const arabic = await reopened.getByTestId('study-datasets').getByTestId('study-row').allTextContents();
  expect(arabic.map((r) => digits(r).slice(0, 8))).toEqual(values.map((r) => digits(r).slice(0, 8)));
  await page.getByRole('button', { name: 'English' }).first().click();
});

// ------------------------------------------------------------------ crafted streams

const DATASET = (id: string, unit = true) => ({
  dataset_id: id, origin: 'get_observations', provisional: true, data_status: 'synthetic_demonstration',
  title: { en: `Table ${id}`, ar: `جدول ${id}` },
  table: {
    columns: [
      { key: 'period', label: { en: 'Period', ar: 'الفترة' }, kind: 'period' },
      { key: 'value', label: { en: 'Value', ar: 'القيمة' }, kind: 'number', ...(unit ? { unit: { code: 'GWH', label_en: 'GWh', label_ar: 'جيجاواط ساعة' } } : {}) },
    ],
    rows: [{ period: '2001', value: '48000' }, { period: '2002', value: '50100' }],
  },
  charts: [], rows_meta: [{ row_id: 'r1', evidence_id: 'E1' }, { row_id: 'r2', evidence_id: 'E2' }], evidence_ids: ['E1', 'E2'],
});

function sse(events: { type: string; payload: unknown; study_id?: string; result_version?: number }[], studyId: string): string {
  return events.map((e, i) => {
    const body = { study_id: e.study_id ?? studyId, seq: i + 1, type: e.type, result_version: e.result_version ?? 0, at: null, payload: e.payload };
    return `id: ${i + 1}\nevent: ${e.type}\ndata: ${JSON.stringify(body)}\n\n`;
  }).join('') + 'event: end\ndata: {"reason":"finished"}\n\n';
}

async function crafted(page: Page, make: (studyId: string) => string) {
  await page.route('**/api/v1/assistant/guest/requests/*/events*', async (route: Route) => {
    const id = /requests\/([^/]+)\/events/.exec(route.request().url())?.[1] ?? '';
    await route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' }, body: make(id) });
  });
}

test('after a stop, late and superseded events are ignored and nothing becomes final', async ({ page }) => {
  await crafted(page, (id) => sse([
    { type: 'study.started', payload: { attempt: 1, mode: 'ask', language: 'en', data_mode: 'synthetic' } },
    { type: 'stage', payload: { stage: 'published_data', label: { en: 'Checking OSRIP’s published data', ar: 'مراجعة' } } },
    { type: 'dataset', payload: DATASET('D1'), result_version: 1 },
    { type: 'dataset', payload: DATASET('D9'), result_version: 2, study_id: '00000000-0000-4000-8000-000000000000' },
    { type: 'study.cancelled', payload: { reason: 'requested' } },
    { type: 'dataset', payload: DATASET('D2'), result_version: 3 },
    { type: 'study.completed', result_version: 4, payload: { status: 'answered', language: 'en', findings: [{ finding_id: 'F1', text: 'Late.', evidence_ids: [] }], narration: [], final_datasets: ['D2'], provisional_datasets: [] } },
  ], id));
  await page.goto('/assistant?mode=synthetic');
  const study = await openStudy(await ask(page, 'What is the latest electricity generation?'));
  await expect(study).toHaveAttribute('data-status', 'cancelled');
  await expect(study.getByTestId('study-stopped')).toBeVisible();
  const datasets = study.getByTestId('study-datasets').getByTestId('dataset');
  await expect(datasets).toHaveCount(1);
  await expect(datasets.first()).toHaveAttribute('data-dataset', 'D1');
  await expect(datasets.first()).toHaveAttribute('data-state', 'stopped');
  await expect(study.getByTestId('study-finding')).toHaveCount(0);
});

test('a table that fails validation in the browser is reported, never drawn', async ({ page }) => {
  await crafted(page, (id) => sse([
    { type: 'study.started', payload: { attempt: 1, mode: 'ask', language: 'en', data_mode: 'synthetic' } },
    { type: 'dataset', payload: DATASET('D1', false), result_version: 1 },
    { type: 'study.completed', result_version: 2, payload: { status: 'no_evidence', language: 'en', findings: [{ finding_id: 'F1', text: 'No published data.', evidence_ids: [] }], narration: [{ narration_segment_id: 'N1', finding_id: 'F1', text: 'No published data.', evidence_ids: [], targets: [], section: 'findings' }], final_datasets: [], provisional_datasets: [] } },
  ], id));
  await page.goto('/assistant?mode=synthetic');
  const study = await openStudy(await ask(page, 'What is the latest electricity generation?'));
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.locator('[data-testid="study-warning"][data-code="dataset_rejected_client"]')).toBeVisible();
  await expect(study.getByTestId('dataset')).toHaveCount(0);
});
