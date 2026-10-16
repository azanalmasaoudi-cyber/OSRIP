import { expect, test, type Page, type Route } from '@playwright/test';

// The analytical workspace through the real stack (scripted assistant and search, fake
// speech): filters, cards, one dataset drawn as chart and table, honest geographic and
// data-mode states, and the assistant's live study streamed as validated events, with the
// narration highlighting the row it reads. Stale events of a stopped or superseded study and
// a table that fails validation are exercised with a crafted stream.

test.skip(({ isMobile }) => isMobile, 'desktop layout; the phone layout is in workspace-phone.spec.ts');

const digits = (s: string | null) => (s ?? '').replace(/[^\d.]/g, '');

async function startChat(page: Page) {
  await page.getByTestId('workspace-start-chat').click();
  await expect(page.getByTestId('workspace-assistant').getByTestId('assistant-input')).toBeVisible();
}

async function ask(page: Page, question: string) {
  const panel = page.getByTestId('workspace-assistant');
  const before = await panel.getByTestId('assistant-message').count();
  await panel.getByTestId('assistant-input').fill(question);
  await panel.getByTestId('assistant-send').click();
  await expect(panel.getByTestId('assistant-message')).toHaveCount(before + 1);
}

test('filters, cards, one dataset as chart and table, and honest empty states', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const ws = page.getByTestId('workspace');
  await expect(ws.getByTestId('filter-domain')).toBeVisible();
  await expect(ws.getByTestId('filter-area')).toBeVisible();
  await expect(ws.getByTestId('workspace-data-mode')).toBeVisible();
  // The assistant sits beside the analysis on a wide screen; no floating button duplicates it.
  await expect(page.getByTestId('workspace-avatar')).toBeVisible();
  await expect(page.getByTestId('open-assistant')).toHaveCount(0);
  // Cards state unit, period and source; old data is flagged, never hidden.
  const card = ws.getByTestId('indicator-card').first();
  await expect(card).toContainText('gigawatt');
  await expect(card.getByTestId('source-details-button')).toBeVisible();
  await expect(card.getByTestId('indicator-stale')).toBeVisible();
  await expect(ws.getByTestId('workspace-stale')).toBeVisible();
  // The history: chart points and table rows are the same validated rows.
  const trend = ws.getByTestId('workspace-data').getByTestId('dataset').first();
  const rows = trend.getByTestId('study-row');
  const points = trend.locator('[data-point]');
  await expect(points).toHaveCount(await rows.count());
  const latest = await card.getByTestId('indicator-value').textContent();
  await expect(rows.last()).toContainText(latest ?? '-');
  // Sorting reorders, never changes, the values.
  const before = (await rows.allTextContents()).sort();
  const sortValue = trend.locator('thead th').nth(1).getByRole('button'); // the value column
  await sortValue.click();
  await sortValue.click();
  expect((await rows.allTextContents()).sort()).toEqual(before);
  await expect(trend.locator('th[aria-sort="descending"]')).toHaveCount(1);
  // Too few governorates publish their own value: no geographic view is drawn.
  await expect(ws.getByTestId('workspace-geography-none')).toBeVisible();
  await expect(ws.getByTestId('workspace-geography').getByTestId('dataset')).toHaveCount(0);
  // Domain filter, and the data mode: verified data are absent here and are said to be.
  await ws.getByTestId('filter-domain').selectOption('trade');
  await expect(ws.getByTestId('indicator-card').first()).toHaveAttribute('data-indicator', /^TRADE_/);
  const verified = ws.getByTestId('workspace-data-mode').getByRole('radio', { name: 'Verified' });
  await verified.click();
  await expect(verified).toBeChecked();
  await expect(page).not.toHaveURL(/mode=synthetic/); // the default mode is left out of the address
  await expect(ws.locator('[data-state="no_verified_data"]').first()).toBeVisible();
});

test('the dashboard: four resources with their latest published values, the chart beside its findings, and comparison, studies and sources below', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const kpi = (section: string) => page.locator(`[data-testid="resource-kpi"][data-section="${section}"]`);
  await expect(page.getByTestId('resource-kpi')).toHaveCount(4);
  const electricity = kpi('electricity');
  await expect(electricity).toHaveAttribute('data-state', 'ok');
  await expect(electricity.getByTestId('kpi-value')).toHaveText('50,100');
  await expect(electricity).toContainText('gigawatt-hour');
  await expect(electricity.getByTestId('kpi-period')).toHaveText('2002');
  await expect(electricity).toContainText('Previous: 48,000 (2001)');
  await expect(electricity).toContainText('Source:');
  await expect(electricity.getByTestId('data-mode-badge')).toHaveText('Synthetic');
  // The large chart sits beside the findings for the same selection.
  const chart = await page.locator('section[aria-labelledby="ws-trend"]').boundingBox();
  const findings = await page.getByTestId('workspace-findings').boundingBox();
  expect(findings?.x ?? 0).toBeGreaterThan((chart?.x ?? 0) + (chart?.width ?? 0) - 1);
  await expect(page.getByTestId('workspace-findings').getByTestId('selection-study')).toBeVisible();
  // "Analyse" on a resource analyses its headline indicator below.
  await kpi('water').getByRole('button', { name: /Analyse/ }).click();
  await expect(page).toHaveURL(/section=water/);
  await expect(kpi('water').getByRole('button', { name: /Analyse/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('workspace-data').getByTestId('indicator-card').first()).toHaveAttribute('data-indicator', /^WATER_/);
  // Below: the comparison (honestly empty here), recent studies (none yet) and the sources shown.
  await expect(page.getByTestId('workspace-geography-none')).toBeVisible();
  await expect(page.getByTestId('recent-studies-empty')).toBeVisible();
  await expect(page.getByTestId('workspace-sources').getByTestId('workspace-source').first()).toContainText('No publisher (synthetic data)');
  // Verified mode: no verified trade data is published, and the card says so instead of a number.
  await page.getByTestId('workspace-data-mode').getByRole('radio', { name: 'Verified' }).click();
  await expect(kpi('trade')).toHaveAttribute('data-state', 'empty');
  await expect(kpi('trade')).toContainText('No published data for this resource in the chosen data mode.');
  await expect(kpi('trade').getByTestId('kpi-value')).toHaveCount(0);
});

test('a live study streams steps, sources and a validated table; narration highlights its row', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  await startChat(page);
  await ask(page, 'What is the latest electricity generation?');
  // The Study tab comes forward with the study.
  await expect(page.getByRole('tab', { name: /Study/ })).toHaveAttribute('aria-selected', 'true');
  const study = page.getByTestId('live-study');
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
  await expect(page.getByTestId('workspace-assistant-state')).toHaveAttribute('data-state', 'speaking');
  // Interrupt: stop the narration; the highlight stays on the sentence reached.
  await narration.getByTestId('narration-stop').click();
  await expect(narration).toHaveAttribute('data-playing', 'false');
  await expect(row).toHaveAttribute('data-highlighted', 'true');
});

test('a failed search is a visible partial failure; sources open and close by keyboard', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  await startChat(page);
  const panel = page.getByTestId('workspace-assistant');
  await panel.getByTestId('assistant-mode').getByRole('radio', { name: 'Research' }).click();
  await ask(page, 'web search that will fail');
  const study = page.getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.locator('[data-testid="study-warning"][data-code="search_failed"]')).toBeVisible();
  await expect(study.locator('[data-testid="study-search"][data-status="failed"]')).toBeVisible();
  await expect(study.getByTestId('study-datasets')).toHaveCount(0);

  await ask(page, 'What is the latest electricity generation?');
  await expect(study).toHaveAttribute('data-status', 'completed');
  const source = study.getByTestId('study-source').first().getByRole('button');
  await source.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByTestId('study-source-details')).toContainText('Synthetic demonstration data');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(source).toBeFocused();
  // Tabs by keyboard: arrows move between Data and Study.
  await page.getByRole('tab', { name: /Study/ }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByRole('tab', { name: 'Data' })).toBeFocused();
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: /Study/ })).toHaveAttribute('aria-selected', 'true');
});

test('the person returns to an earlier study, and switching language keeps the values', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  await startChat(page);
  await ask(page, 'What is the latest electricity generation?');
  const study = page.getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  const firstId = await study.getAttribute('data-study');
  await ask(page, 'What is the latest water production?');
  await expect(study).not.toHaveAttribute('data-study', firstId ?? '');
  await expect(study).toHaveAttribute('data-status', 'completed');
  // Back to the first study: its events are replayed and it looks as it did.
  await study.getByTestId('study-history').selectOption(firstId ?? '');
  await expect(study).toHaveAttribute('data-study', firstId ?? '');
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.getByTestId('study-finding').first()).toContainText('50100');
  await expect(page.getByTestId('workspace-assistant').getByTestId('open-study').first()).toHaveAttribute('aria-pressed', 'true');
  // Both studies of this session are listed under Recent studies.
  await expect(page.getByTestId('recent-studies').getByTestId('recent-study-open')).toHaveCount(2);
  // Arabic: labels change, the table's values do not.
  const values = await study.getByTestId('study-datasets').getByTestId('study-row').allTextContents();
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(study.getByTestId('study-findings-panel')).toContainText('النتائج');
  const arabic = await study.getByTestId('study-datasets').getByTestId('study-row').allTextContents();
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
  await page.goto('/overview?mode=synthetic');
  await startChat(page);
  await ask(page, 'What is the latest electricity generation?');
  const study = page.getByTestId('live-study');
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
  await page.goto('/overview?mode=synthetic');
  await startChat(page);
  await ask(page, 'What is the latest electricity generation?');
  const study = page.getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.locator('[data-testid="study-warning"][data-code="dataset_rejected_client"]')).toBeVisible();
  await expect(study.getByTestId('dataset')).toHaveCount(0);
});
