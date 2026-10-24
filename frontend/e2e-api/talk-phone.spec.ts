import { expect, test, type Page } from '@playwright/test';

// The Talk page as one centred column, on the desktop and the Pixel 7 projects: the name, a
// compact still portrait (180–220px tall on desktop, 120–160px on a phone, never stretched),
// the persona choice, then the conversation with Send and Speak. No setup or technical notes
// on the page (they are in Settings), one scrolling region, English and Arabic, light and dark.

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}.png` });
}

async function openTalk(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((t) => window.localStorage.setItem('osrip.theme', t), theme);
  await page.goto('/talk?mode=synthetic');
  await expect(page.getByTestId('talk-workspace')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

async function rect(page: Page, testId: string) {
  const box = await page.getByTestId('talk-workspace').getByTestId(testId).first().boundingBox();
  expect(box, testId).not.toBeNull();
  return box!;
}

async function checkColumn(page: Page, phone: boolean): Promise<void> {
  const viewport = page.viewportSize()!;
  const column = await rect(page, 'talk-column');
  expect(column.width).toBeLessThanOrEqual(900);
  expect(Math.abs(column.x + column.width / 2 - viewport.width / 2)).toBeLessThan(2);
  // Name, portrait, persona choice and conversation, top to bottom.
  const name = await rect(page, 'talk-persona-name');
  const portrait = await rect(page, 'assistant-avatar');
  const picker = await rect(page, 'persona-picker');
  const sheet = await rect(page, 'talk-sheet');
  expect(name.y + name.height).toBeLessThanOrEqual(portrait.y);
  expect(portrait.y + portrait.height).toBeLessThanOrEqual(picker.y);
  expect(picker.y + picker.height).toBeLessThanOrEqual(sheet.y);
  // The portrait: compact, 3:4 like the image itself, cropped never stretched.
  const [low, high] = phone ? [120, 160] : [180, 220];
  expect(portrait.height).toBeGreaterThanOrEqual(low - 0.5);
  expect(portrait.height).toBeLessThanOrEqual(high + 0.5);
  expect(portrait.width / portrait.height).toBeCloseTo(0.75, 2);
  const image = page.getByTestId('talk-figure').locator('img');
  expect(await image.evaluate((img) => getComputedStyle(img).objectFit)).toBe('cover');
  // The conversation has more room than the portrait block (even 720px tall, the smallest
  // desktop here), its messages a usable area, and the message box is in view.
  const identity = await rect(page, 'talk-identity');
  const messages = await rect(page, 'assistant-messages');
  expect(sheet.height).toBeGreaterThan(identity.height);
  expect(messages.height).toBeGreaterThanOrEqual(phone ? 200 : 140);
  const input = await rect(page, 'assistant-input');
  expect(input.y + input.height).toBeLessThanOrEqual(viewport.height);
  // One scrolling region inside Talk (the message box only scrolls its own text), and no
  // sideways scrolling.
  const scrolling = await page.getByTestId('talk-workspace').evaluate((root) => [...root.querySelectorAll(':not(textarea)')]
    .filter((e) => /(auto|scroll)/.test(getComputedStyle(e).overflowY)).length);
  expect(scrolling).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

test('Talk is one centred column: name, portrait, persona choice, then the conversation', async ({ page }, info) => {
  const phone = info.project.name === 'mobile';
  await page.addInitScript(() => {
    const store = window as unknown as { __media: number };
    store.__media = 0;
    const media = navigator.mediaDevices;
    if (!media) return;
    const original = media.getUserMedia.bind(media);
    media.getUserMedia = async (constraints) => { store.__media += 1; return original(constraints); };
  });
  await openTalk(page, 'dark');
  const workspace = page.getByTestId('talk-workspace');
  await expect(page.getByRole('heading', { level: 1, name: 'Talk to Al Mulhim' })).toBeFocused();
  await checkColumn(page, phone);

  // No technical notes on the page: they are in Settings (linked from the header).
  for (const id of ['talk-mode', 'talk-mode-note', 'talk-realtime', 'talk-portrait-note', 'talk-voice', 'voice-support']) {
    await expect(workspace.getByTestId(id)).toHaveCount(0);
  }
  await expect(workspace.getByTestId('assistant-help')).toHaveCount(0);
  expect(await workspace.innerText()).not.toMatch(/LiveKit|lip.synchron|Fallback mode|speech service hears/i);
  await expect(workspace).toHaveAttribute('data-mode', 'push_to_talk');
  await expect(workspace.getByTestId('talk-help')).toHaveAttribute('href', /\/settings/);
  // Send, Speak, mute and the answer modes are all still there, as compact controls.
  for (const id of ['assistant-send', 'voice-start', 'voice-mute', 'assistant-mode', 'assistant-language']) {
    await expect(workspace.getByTestId(id)).toBeVisible();
  }
  expect(await page.evaluate(() => (window as unknown as { __media: number }).__media)).toBe(0); // no microphone yet
  await snap(page, `talk-${info.project.name}-en-dark`);

  // A conversation: the reply appears below, the message box stays in view.
  await workspace.getByTestId('assistant-input').fill('What is the latest electricity generation?');
  await workspace.getByTestId('assistant-send').click();
  await expect(workspace.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence|data_report/);
  await expect(workspace.getByTestId('assistant-input')).toBeInViewport();
  await snap(page, `talk-${info.project.name}-en-dark-conversation`);

  // Switching to Ilham keeps the same layout.
  await workspace.getByTestId('persona-option-ilham').click();
  await expect(workspace).toHaveAttribute('data-persona', 'ilham');
  await expect(page.getByTestId('talk-figure').locator('img')).toHaveAttribute('src', /ilham-figure/);
  await checkColumn(page, phone);
});

test('Talk in Arabic, right to left, in the light theme', async ({ page }, info) => {
  const phone = info.project.name === 'mobile';
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await openTalk(page, 'light');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('تحدّث مع');
  await checkColumn(page, phone);
  await snap(page, `talk-${info.project.name}-ar-light`);
});

test.describe('short screens', () => {
  test.skip(({ isMobile }) => !isMobile, 'checked once, on the phone');

  test('a phone in landscape: no large portrait, the conversation and message box in view', async ({ page }, info) => {
    // Playwright's Pixel 7 in landscape: 863×360 of page below the browser's own bars.
    await page.setViewportSize({ width: 863, height: 360 });
    await openTalk(page, 'dark');
    const workspace = page.getByTestId('talk-workspace');
    await expect(workspace.getByTestId('talk-figure')).toBeHidden();
    await expect(workspace.getByTestId('persona-picker')).toBeVisible(); // still shows both faces
    await expect(page.getByRole('heading', { level: 1, name: 'Talk to Al Mulhim' })).toBeVisible();
    // Name and choice share one row; the conversation has the rest, with no scrolling needed.
    const identity = await rect(page, 'talk-identity');
    const sheet = await rect(page, 'talk-sheet');
    expect(identity.height).toBeLessThan(60);
    expect(sheet.height).toBeGreaterThanOrEqual(224);
    expect((await rect(page, 'assistant-messages')).height).toBeGreaterThanOrEqual(50);
    for (const id of ['assistant-input', 'assistant-send', 'voice-start']) {
      await expect(workspace.getByTestId(id)).toBeInViewport({ ratio: 1 });
    }
    await snap(page, `talk-${info.project.name}-landscape`);
    await workspace.getByTestId('assistant-input').fill('What is the latest electricity generation?');
    await workspace.getByTestId('assistant-send').click();
    await expect(workspace.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence|data_report/);
    await expect(workspace.getByTestId('assistant-input')).toBeInViewport({ ratio: 1 });
  });

  test('an even shorter window: the conversation keeps its room and the message box can be scrolled to', async ({ page }) => {
    await page.setViewportSize({ width: 411, height: 257 });
    await openTalk(page, 'dark');
    const workspace = page.getByTestId('talk-workspace');
    expect((await rect(page, 'talk-sheet')).height).toBeGreaterThanOrEqual(224);
    const input = workspace.getByTestId('assistant-input');
    await input.scrollIntoViewIfNeeded();
    await expect(input).toBeInViewport({ ratio: 1 });
    await input.fill('Hello');
    await workspace.getByTestId('assistant-send').click();
    await expect(workspace.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  });
});

test('without a suitable voice, Talk says so in one line with a link to the fix', async ({ page }) => {
  // No server speech, and a browser with women's voices only: Al Mulhim cannot read aloud.
  await page.route(/\/api\/v1\/assistant\/voice$/, (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      configured: false, provider: null, max_seconds: 60, stores_audio: false,
      languages: { en: { locale: 'en-GB', voice: 'en-GB-RyanNeural' }, ar: { locale: 'ar-OM', voice: 'ar-OM-AbdullahNeural' } },
    }),
  }));
  await page.addInitScript(() => {
    const voices = [
      { name: 'Microsoft Aysha Online (Natural) - Arabic (Oman)', lang: 'ar-OM' },
      { name: 'Microsoft Sonia Online (Natural) - English (United Kingdom)', lang: 'en-GB' },
    ].map((v) => ({ ...v, voiceURI: v.name, default: false, localService: true }));
    Object.defineProperty(window.speechSynthesis, 'getVoices', { value: () => voices });
  });
  await page.goto('/talk?mode=synthetic');
  const workspace = page.getByTestId('talk-workspace');
  const notice = workspace.getByTestId('talk-no-voice');
  await expect(notice).toHaveText(/No suitable voice in this browser/);
  await expect(notice.getByRole('link', { name: 'How to fix' })).toHaveAttribute('href', /\/settings/);
  await expect(workspace.getByTestId('voice-no-male')).toHaveCount(0); // the long explanation is in Settings
});

test('the setup notes moved to Settings: live avatar status and help', async ({ page }) => {
  await page.goto('/settings?mode=synthetic');
  const realtime = page.getByTestId('service-realtime');
  await realtime.locator('summary').click();
  await expect(realtime).toContainText('OSRIP_LIVEKIT_URL');
  await page.getByTestId('help-talk').locator('summary').click();
  await expect(page.getByTestId('help-talk')).toContainText('push-to-talk');
  await page.getByTestId('help-browserVoices').locator('summary').click();
  await expect(page.getByTestId('help-browserVoices')).toContainText('Microsoft Abdullah or Aysha');
});
