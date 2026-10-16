import { expect, test, type Page } from '@playwright/test';

// Al Mulhim speaks only with a man's voice and Ilham only with a woman's. When the server
// speech service is not configured, the browser's own voices are used: the test installs a
// realistic mix of male and female voices (as Windows and Edge provide) and checks which one
// reads the answer. Without a voice of the persona's gender, nothing is read aloud and the
// panel says why.

type FakeVoice = { name: string; lang: string };

const MIXED: FakeVoice[] = [
  { name: 'Microsoft Hoda - Arabic (Egypt)', lang: 'ar-EG' },
  { name: 'Microsoft Aysha Online (Natural) - Arabic (Oman)', lang: 'ar-OM' },
  { name: 'Microsoft Naayf - Arabic (Saudi Arabia)', lang: 'ar-SA' },
  { name: 'Microsoft Abdullah Online (Natural) - Arabic (Oman)', lang: 'ar-OM' },
  { name: 'Microsoft Hazel - English (United Kingdom)', lang: 'en-GB' },
  { name: 'Microsoft Sonia Online (Natural) - English (United Kingdom)', lang: 'en-GB' },
  { name: 'Google UK English Female', lang: 'en-GB' },
  { name: 'Microsoft Ryan Online (Natural) - English (United Kingdom)', lang: 'en-GB' },
  { name: 'Microsoft Zira - English (United States)', lang: 'en-US' },
];
const FEMALE_ONLY: FakeVoice[] = MIXED.filter((v) => /Hoda|Aysha|Hazel|Sonia|Female|Zira/.test(v.name));

async function setUp(page: Page, voices: FakeVoice[]): Promise<void> {
  // Browser speech: report the server speech service as not configured.
  await page.route(/\/api\/v1\/assistant\/voice$/, (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      configured: false, provider: null, max_seconds: 60, stores_audio: false,
      languages: { en: { locale: 'en-GB', voice: 'en-GB-RyanNeural' }, ar: { locale: 'ar-OM', voice: 'ar-OM-AbdullahNeural' } },
    }),
  }));
  await page.addInitScript((list: FakeVoice[]) => {
    const spoken: string[] = [];
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    const voices = list.map((v) => ({ ...v, voiceURI: v.name, default: false, localService: true }));
    // A stand-in utterance: the real one accepts only the browser's own voice objects.
    class FakeUtterance {
      text: string;
      lang = '';
      voice: { name: string } | null = null;
      onstart: ((e: Event) => void) | null = null;
      onend: ((e: Event) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      constructor(text: string) { this.text = text; }
    }
    Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: FakeUtterance, configurable: true });
    const synth = window.speechSynthesis;
    Object.defineProperty(synth, 'getVoices', { value: () => voices });
    Object.defineProperty(synth, 'speak', {
      value: (utterance: FakeUtterance) => {
        spoken.push(utterance.voice?.name ?? '(none)');
        setTimeout(() => utterance.onstart?.(new Event('start')), 10);
        setTimeout(() => utterance.onend?.(new Event('end')), 60);
      },
    });
    Object.defineProperty(synth, 'cancel', { value: () => undefined });
  }, voices);
}

async function askAndReadAloud(page: Page, question: string): Promise<string> {
  await page.getByTestId('assistant-input').fill(question);
  await page.getByTestId('assistant-send').click();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', /answered|no_evidence/);
  await reply.getByTestId('read-aloud').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBeGreaterThan(0);
  return page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.at(-1) ?? '');
}

test('answers are read with a man’s voice in Arabic and in English', async ({ page }) => {
  await setUp(page, MIXED);
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  expect(await askAndReadAloud(page, 'ما نمو توليد الكهرباء؟')).toBe('Microsoft Abdullah Online (Natural) - Arabic (Oman)');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'English' }).click();
  expect(await askAndReadAloud(page, 'What was the growth of electricity generation?')).toBe('Microsoft Ryan Online (Natural) - English (United Kingdom)');
  await expect(page.getByTestId('voice-no-male')).toHaveCount(0);
});

test('Ilham reads with a woman’s voice in Arabic and in English', async ({ page }) => {
  await setUp(page, MIXED);
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('persona-picker').first().getByTestId('persona-option-ilham').click();
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  expect(await askAndReadAloud(page, 'ما نمو توليد الكهرباء؟')).toBe('Microsoft Aysha Online (Natural) - Arabic (Oman)');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'English' }).click();
  expect(await askAndReadAloud(page, 'What was the growth of electricity generation?')).toBe('Microsoft Sonia Online (Natural) - English (United Kingdom)');
  // An earlier reply keeps the voice of the persona that gave it.
  await page.getByTestId('persona-picker').first().getByTestId('persona-option-mulhim').click();
  await page.getByTestId('assistant-message').last().getByTestId('read-aloud').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.at(-1)))
    .toBe('Microsoft Sonia Online (Natural) - English (United Kingdom)');
});

test('Ilham with only male voices installed reads nothing aloud and says why', async ({ page }) => {
  await setUp(page, MIXED.filter((v) => /Naayf|Abdullah|Ryan/.test(v.name)));
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('persona-picker').first().getByTestId('persona-option-ilham').click();
  await expect(page.getByTestId('voice-no-female')).toContainText('only with a woman’s voice');
  await expect(page.getByTestId('voice-no-male')).toHaveCount(0);
});

test('with no Arabic voice installed, Arabic answers are shown as text and the panel says why, for both personas', async ({ page }) => {
  // As on a Windows laptop with only English voices (David, Mark, Zira).
  await setUp(page, MIXED.filter((v) => v.lang.startsWith('en')));
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  const notice = page.getByTestId('voice-no-language');
  await expect(notice).toHaveAttribute('data-language', 'ar');
  await expect(notice).toContainText('This browser has no Arabic voice installed');
  await expect(page.getByTestId('voice-no-male')).toHaveCount(0); // not a gender problem
  await page.getByTestId('assistant-input').fill('ما نمو توليد الكهرباء؟');
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence/);
  await expect(page.getByTestId('read-aloud')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(0);
  // Ilham has no Arabic voice either; in English both can speak, and the notice goes.
  await page.getByTestId('persona-picker').first().getByTestId('persona-option-ilham').click();
  await expect(notice).toBeVisible();
  await expect(page.getByTestId('voice-no-female')).toHaveCount(0);
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'English' }).click();
  await expect(notice).toHaveCount(0);
  await expect(page.getByTestId('voice-mute')).toBeVisible();
});

test('the missing-voice notice is in Arabic in the Arabic interface', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  await setUp(page, MIXED.filter((v) => v.lang.startsWith('en')));
  await page.goto('/assistant?mode=synthetic');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('voice-no-language')).toContainText('لا يوجد في هذا المتصفح صوت عربي مثبّت');
});

test('with no voices listed yet, no missing-voice notice is shown', async ({ page }) => {
  await setUp(page, []); // some browsers load their voices later
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  await expect(page.getByTestId('voice-support')).toBeVisible();
  await expect(page.getByTestId('voice-no-language')).toHaveCount(0);
});

test('with only female voices installed, nothing is read aloud and the panel says why', async ({ page }) => {
  await setUp(page, FEMALE_ONLY);
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('voice-no-male')).toContainText('only with a man’s voice');
  await page.getByTestId('assistant-input').fill('Hello');
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
  await expect(page.getByTestId('read-aloud')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(0);
});
