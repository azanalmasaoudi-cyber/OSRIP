import { writeFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

import { chooseSelection } from '../e2e-api/sector';

// The integrated experience, demonstrated on the real stack (scripted assistant, search and
// speech; verified reference pack loaded). Every step asserts what it shows, and saves a
// screenshot to docs/evidence/integrated/. Live provider voices are NOT demonstrated here:
// Azure AI Speech is not configured, so the scripted speech provider plays a test tone.

const OUT = '../docs/evidence/integrated';
const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
const digits = (s: string | null) => (s ?? '').replace(/[^\d.]/g, '');

async function ordinaryDevice(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  });
}

test.describe('1-2. Entrance', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('Al Mulhim and Ilham arrive, the OSRIP sign is set between them; bilingual resources and goals; skip and replay', async ({ page }) => {
    await ordinaryDevice(page);
    await page.goto('/');
    await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
    await page.waitForTimeout(600);
    await shot(page, '01-entrance-arriving');
    const sign = await page.getByTestId('entrance-sign').boundingBox();
    const stage = await page.getByTestId('entrance-stage').boundingBox();
    await expect(page.getByTestId('entrance-goals')).toHaveCSS('opacity', '1');
    const placed = await page.getByTestId('entrance-sign').boundingBox();
    expect(placed && stage && Math.abs(placed.x + placed.width / 2 - (stage.x + stage.width / 2))).toBeLessThan(3);
    expect(sign).not.toBeNull();
    await expect(page.getByTestId('entrance-sign-text')).toHaveText('OSRIP');
    await shot(page, '03-entrance-placed-in-centre');
    const goals = page.getByTestId('entrance-goals');
    for (const text of ['Understand Oman’s resources', 'افهم موارد عُمان', 'Analyse reliable data', 'حلّل البيانات الموثوقة',
      'Support informed decisions', 'ادعم القرار بالمعلومة']) await expect(goals).toContainText(text);
    await expect(page.getByTestId('entrance-sector')).toHaveCount(3);
    await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
    await shot(page, '04-entrance-bilingual-goals');
    // Skip closes it at once; the footer's Replay introduction plays it again.
    await page.getByTestId('entrance-skip').click();
    await expect(page.getByTestId('entrance')).toBeHidden();
    await page.getByTestId('replay-entrance').click();
    await expect(page.getByTestId('entrance')).toBeVisible();
    await expect(page.getByTestId('entrance-goals')).toHaveCSS('opacity', '1');
    await shot(page, '05-entrance-replayed');
    await page.getByTestId('entrance-skip').click();
    await expect(page.getByTestId('entrance')).toBeHidden();
  });
});

test('3-4. Choosing Al Mulhim or Ilham; each has its own voice (configured ids)', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const picker = page.getByTestId('persona-picker').first();
  await picker.getByTestId('persona-option-ilham').click();
  await expect(picker).toHaveAttribute('data-selected', 'ilham');
  await expect(page.getByTestId('mulhim-name').first()).toHaveText('Ilham');
  await shot(page, '06-persona-ilham-selected');
  // Talk shows the voice each persona speaks with (the scripted speech service here).
  await page.getByTestId('open-talk').click();
  await expect(page.getByTestId('talk-voice')).toHaveText('Voice: en-GB-SoniaNeural');
  await shot(page, '07-talk-ilham-female-voice');
  await page.getByTestId('talk-workspace').getByTestId('persona-picker').getByTestId('persona-option-mulhim').click();
  await expect(page.getByTestId('talk-voice')).toHaveText('Voice: en-GB-RyanNeural');
  await shot(page, '08-talk-mulhim-male-voice');
  const voices = await page.evaluate(async () => (await (await fetch('/api/v1/assistant/voice')).json()) as { personas: { code: string; gender: string; voices: Record<string, string> }[] });
  expect(voices.personas.map((p) => [p.code, p.gender, p.voices.ar, p.voices.en])).toEqual([
    ['mulhim', 'male', 'ar-OM-AbdullahNeural', 'en-GB-RyanNeural'],
    ['ilham', 'female', 'ar-OM-AyshaNeural', 'en-GB-SoniaNeural'],
  ]);
});

test('5-6. A sourced analysis on approved data; table, chart and spoken explanation match', async ({ page }) => {
  await page.goto('/workspace'); // verified-source data (the reference pack) by default
  const ws = page.getByTestId('workspace');
  // Published electricity mixes annual, year-to-date and monthly series: choose one, here.
  await ws.getByTestId('filter-frequency').selectOption('annual');
  await expect(page).toHaveURL(/frequency=annual/);
  await expect(ws.getByTestId('indicator-card').first()).toBeVisible();
  await ws.getByTestId('filter-indicator').selectOption('ELEC_GROSS_GENERATION');
  await expect(ws.getByTestId('workspace-data').getByTestId('dataset').first()).toHaveAttribute('data-state', 'reference');
  await shot(page, '09-workspace-verified-data');
  // Governorates are shown because several publish their own comparable value.
  const geo = ws.getByTestId('workspace-geography');
  await expect(geo.getByTestId('dataset')).toBeVisible();
  await geo.scrollIntoViewIfNeeded();
  await shot(page, '09b-workspace-governorates');
  await page.getByTestId('workspace-start-chat').click();
  const chat = page.getByTestId('workspace-assistant');
  await chat.getByTestId('assistant-input').fill('Show the history of gross generation');
  await chat.getByTestId('assistant-send').click();
  const study = page.getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  const dataset = study.getByTestId('study-datasets').getByTestId('dataset').first();
  await expect(dataset).toHaveAttribute('data-state', 'final');
  await expect(dataset.getByTestId('data-status').first()).toHaveAttribute('data-status', 'approved_official');
  // Play: each sentence lights its own row and chart point; the numbers are the same.
  const narration = study.getByTestId('narration');
  await narration.getByTestId('narration-play').click();
  const findings = study.getByTestId('study-finding');
  const count = await findings.count();
  for (let i = 0; i < Math.min(count, 2); i += 1) {
    await expect(narration).toHaveAttribute('data-segment', `N${i + 1}`);
    const row = dataset.locator('tr[data-highlighted="true"]');
    await expect(row).toHaveCount(1);
    await expect(dataset.locator('[data-point][data-highlighted="true"]')).toHaveCount(1);
    const cell = await row.locator('td').nth(1).textContent();
    expect(digits(await findings.nth(i).textContent())).toContain(digits(cell));
    await dataset.scrollIntoViewIfNeeded();
    await shot(page, `${10 + i}-narration-sentence-${i + 1}-highlights-row`);
  }
  await narration.getByTestId('narration-stop').click();

  // External research where needed (scripted search here; labelled, unreviewed).
  await chat.getByTestId('assistant-mode').getByRole('radio', { name: 'Research' }).click();
  await chat.getByTestId('assistant-input').fill('Search the web for electricity generation 2023');
  await chat.getByTestId('assistant-send').click();
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.locator('[data-testid="study-source"] [data-status="unreviewed_external"]').first()).toBeVisible();
  await study.getByTestId('study-evidence').scrollIntoViewIfNeeded();
  await shot(page, '12-research-sources-labelled');
});

test('7. A failing provider and a denied microphone are explained; nothing is charged', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-input').fill('please fail');
  await page.getByTestId('assistant-send').click();
  // The answer service failed: a labelled data-based report instead, not charged.
  const failed = page.getByTestId('assistant-message').last();
  await expect(failed).toHaveAttribute('data-status', 'data_report');
  await expect(failed.getByTestId('non-ai-label')).toBeVisible();
  await expect(failed.getByRole('button', { name: 'Try the AI answer again' })).toBeVisible();
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  await shot(page, '13-provider-unavailable-not-charged');
  await page.getByTestId('open-talk').click();
  const sheet = page.getByTestId('talk-sheet');
  await sheet.getByTestId('voice-start').click(); // no microphone permission granted
  await expect(sheet.getByTestId('voice-notice')).toBeVisible();
  await shot(page, '14-microphone-denied-typing-works');
});

test('8. Five answers shared across personas: switching persona does not reset the count', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const picker = page.getByTestId('persona-picker').first();
  const ask = async (text: string) => {
    const n = await page.getByTestId('assistant-message').count();
    await page.getByTestId('assistant-input').fill(text);
    await page.getByTestId('assistant-send').click();
    await expect(page.getByTestId('assistant-message')).toHaveCount(n + 1);
  };
  await ask('Hello'); // the fixed greeting: free
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  for (let i = 0; i < 5; i += 1) {
    await picker.getByTestId(i % 2 ? 'persona-option-ilham' : 'persona-option-mulhim').click();
    await ask('What is the latest electricity generation?');
    await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', String(4 - i));
  }
  await expect(page.getByTestId('assistant-sign-in')).toBeVisible();
  await expect(page.getByTestId('assistant-input')).toBeDisabled();
  await shot(page, '15-guest-limit-after-switching-persona');
});

test('@phone the workspace on a phone: tabs and the study', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic&tab=assistant');
  await page.getByTestId('workspace-start-chat').click();
  const chat = page.getByTestId('workspace-assistant');
  await chat.getByTestId('assistant-input').fill('Show the history of electricity generation');
  await chat.getByTestId('assistant-send').click();
  await expect(page.getByTestId('live-study')).toHaveAttribute('data-status', 'completed');
  await shot(page, '16-phone-study-tab');
});

test('9. Evaluation scenario: electricity, a published period, table, chart on request, sourced analysis, references, missing data', async ({ page }) => {
  // Each step is timed from the action to its asserted result (browser, API and the scripted
  // model on this machine); the times are written beside the screenshots.
  const steps: { step: string; ms: number }[] = [];
  const timed = async (step: string, run: () => Promise<void>) => {
    const started = performance.now();
    await run();
    steps.push({ step, ms: Math.round(performance.now() - started) });
  };

  await timed('Open electricity', async () => {
    await page.goto('/energy/electricity'); // verified-source data (the reference pack) by default
    await expect(page.getByTestId('sector-form')).toBeVisible();
  });
  await expect(page.getByTestId('sector-results')).toHaveCount(0); // nothing before Show results
  await timed('Choose a published period', async () => {
    await chooseSelection(page, { indicator: 'ELEC_GROSS_GENERATION', area: 'OM', view: 'monthly', from: '2026-06-01', to: '2026-08-01' });
  });
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
  await shot(page, '20-scenario-period-chosen');

  await timed('Show results (table)', async () => {
    await page.getByTestId('sector-show-results').click();
    await expect(page.getByTestId('series-row')).toHaveCount(3);
  });
  const rows = page.getByTestId('series-row');
  for (const [i, value] of ['5,755.4', '5,676.9', '5,743.9'].entries()) await expect(rows.nth(i)).toContainText(value);
  await expect(page.getByTestId('summary-latest')).toContainText('5,743.9');
  await expect(page.getByTestId('summary-total')).toContainText('17,176.2'); // a flow, every month published
  await expect(page.getByTestId('sector-chart')).toHaveCount(0); // no chart until asked for
  await page.getByTestId('sector-results').scrollIntoViewIfNeeded();
  await shot(page, '21-scenario-table');

  await timed('Show chart', async () => {
    await page.getByTestId('sector-show-chart').click();
    await expect(page.getByTestId('sector-chart')).toBeVisible();
  });
  await page.getByTestId('sector-chart').scrollIntoViewIfNeeded();
  await shot(page, '22-scenario-chart-on-request');

  await page.getByTestId('sector-request-analysis').click();
  await expect(page).toHaveURL(/\/assistant\?.*ind=ELEC_GROSS_GENERATION/);
  await expect(page.getByTestId('assistant-selection')).toContainText('Gross electricity generation');
  const reply = page.getByTestId('assistant-message').last();
  await timed('Ask for a sourced analysis (scripted model)', async () => {
    await page.getByTestId('assistant-send').click();
    await expect(reply).toHaveAttribute('data-status', 'answered');
  });
  // Exactly the applied months, each figure cited to the bulletin that published it.
  const citations = reply.getByTestId('citation');
  await expect(citations).toHaveCount(3);
  await expect(reply.getByTestId('ai-label')).toBeVisible();
  for (const value of ['5755.4', '5676.9', '5743.9']) await expect(reply.getByTestId('assistant-text')).toContainText(value);
  await expect(citations.first()).toContainText('Monthly Statistical Bulletin, September 2026');
  await shot(page, '23-scenario-sourced-analysis');

  await timed('Inspect a reference', async () => {
    const chip = reply.getByTestId('citation-chip').first();
    const id = await chip.getAttribute('data-evidence');
    await chip.click();
    await expect(reply.locator(`[data-testid="citation"][data-evidence="${id}"]`)).toBeFocused();
  });
  const link = citations.first().getByRole('link');
  await expect(link).toHaveAttribute('href', /^https:\/\/api\.ncsi\.gov\.om\/uploads\//);
  await shot(page, '24-scenario-reference-inspected');

  // Missing data: the 2026 full year is not published (only January to August, shown apart).
  await timed('Missing-data case', async () => {
    await page.goto('/energy/electricity');
    await chooseSelection(page, { indicator: 'ELEC_GROSS_GENERATION', area: 'OM', view: 'annual', from: '2022-01-01', to: '2026-01-01' });
    await page.getByTestId('sector-show-results').click();
    await expect(page.getByTestId('series-row')).toHaveCount(5);
  });
  const year2026 = page.locator('[data-testid="series-row"][data-period="2026-01-01"]');
  await expect(year2026).toHaveAttribute('data-nature', 'missing');
  await expect(year2026).toContainText('Not published');
  await expect(year2026).not.toContainText(/\b0\b/); // never shown as zero
  await expect(page.getByTestId('series-ytd')).toContainText('37,481.8');
  await expect(page.getByTestId('summary-total')).toHaveCount(0); // no total over a gap
  await page.getByTestId('sector-results').scrollIntoViewIfNeeded();
  await shot(page, '25-scenario-missing-year');
  await page.getByTestId('sector-frequency').locator('[data-value="quarterly"]').click();
  await expect(page.getByTestId('sector-no-periods')).toBeVisible();
  await page.getByTestId('sector-form').scrollIntoViewIfNeeded();
  await shot(page, '26-scenario-no-quarterly-figures');

  // The same results in Arabic, right to left (changing the frequency cleared the periods).
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await chooseSelection(page, { view: 'annual', from: '2022-01-01', to: '2026-01-01' });
  await page.getByTestId('sector-show-results').click();
  await expect(page.getByTestId('series-row')).toHaveCount(5);
  await expect(page.getByTestId('summary-latest')).toContainText('50,973.5');
  await page.getByTestId('sector-results').scrollIntoViewIfNeeded();
  await shot(page, '27-scenario-arabic');

  writeFileSync(`${OUT}/scenario-timings.json`, `${JSON.stringify({
    measured_at: new Date().toISOString(),
    note: 'Local run: Vite dev server, FastAPI, PostgreSQL and the scripted test model; not a live AI provider.',
    steps,
  }, null, 2)}\n`);
});
