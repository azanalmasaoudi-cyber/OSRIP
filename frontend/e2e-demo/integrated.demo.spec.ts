import { expect, test, type Page } from '@playwright/test';

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
  await page.goto('/overview'); // verified-source data (the reference pack) by default
  const ws = page.getByTestId('workspace');
  // Published electricity mixes annual, year-to-date and monthly series: choose one, here.
  await ws.getByTestId('choose-frequency-annual').click();
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
  const failed = page.getByTestId('assistant-message').last();
  await expect(failed).toHaveAttribute('data-status', 'unavailable');
  await expect(failed.getByRole('button', { name: 'Try again' })).toBeVisible();
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
  await page.goto('/overview?mode=synthetic&tab=assistant');
  await page.getByTestId('workspace-start-chat').click();
  const chat = page.getByTestId('workspace-assistant');
  await chat.getByTestId('assistant-input').fill('Show the history of electricity generation');
  await chat.getByTestId('assistant-send').click();
  await expect(page.getByTestId('live-study')).toHaveAttribute('data-status', 'completed');
  await shot(page, '16-phone-study-tab');
});
