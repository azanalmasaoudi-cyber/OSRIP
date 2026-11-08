import { expect, test, type Page } from '@playwright/test';

import { closeDrawer, openChatSettings, setAnswerLanguage } from './chat';

// Al Mulhim speaks only with a man's voice. When the server speech service is not configured,
// the browser's own voices are used: the test installs a realistic mix of male and female
// voices (as Windows and Edge provide) and checks which one reads the answer. Without a
// suitable voice nothing is read aloud, and the conversation's settings say so in one line
// with a link to the fix (the conversation itself carries no voice notes).

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

/** The one conversation (the AI Assistant page). */
async function openChat(page: Page): Promise<void> {
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('assistant-panel')).toBeVisible();
}

/** The one-line notice in the conversation settings (null when there is none). */
async function voiceNotice(page: Page): Promise<string | null> {
  await openChatSettings(page);
  const notice = page.getByTestId('talk-no-voice');
  const text = (await notice.count()) ? await notice.innerText() : null;
  await closeDrawer(page);
  return text;
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
  await openChat(page);
  await setAnswerLanguage(page, 'العربية');
  expect(await askAndReadAloud(page, 'ما نمو توليد الكهرباء؟')).toBe('Microsoft Abdullah Online (Natural) - Arabic (Oman)');
  await setAnswerLanguage(page, 'English');
  expect(await askAndReadAloud(page, 'What was the growth of electricity generation?')).toBe('Microsoft Ryan Online (Natural) - English (United Kingdom)');
  expect(await voiceNotice(page)).toBeNull();
});

test('with no Arabic voice installed, Arabic answers are shown as text and the settings say why', async ({ page }) => {
  // As on a Windows laptop with only English voices (David, Mark, Zira).
  await setUp(page, MIXED.filter((v) => v.lang.startsWith('en')));
  await openChat(page);
  await setAnswerLanguage(page, 'العربية');
  await page.getByTestId('assistant-input').fill('ما نمو توليد الكهرباء؟');
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence/);
  await expect(page.getByTestId('read-aloud')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(0);
  expect(await voiceNotice(page)).toContain('No suitable voice in this browser');
  // In English Al Mulhim can speak, and the notice goes.
  await setAnswerLanguage(page, 'English');
  expect(await voiceNotice(page)).toBeNull();
  await openChatSettings(page);
  await expect(page.getByTestId('voice-mute')).toBeVisible();
});

test('the missing-voice notice is in Arabic in the Arabic interface', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  await setUp(page, MIXED.filter((v) => v.lang.startsWith('en')));
  await openChat(page);
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  expect(await voiceNotice(page)).toContain('لا يوجد صوت مناسب في هذا المتصفح');
});

test('with no voices listed yet, no missing-voice notice is shown', async ({ page }) => {
  await setUp(page, []); // some browsers load their voices later
  await openChat(page);
  await setAnswerLanguage(page, 'العربية');
  expect(await voiceNotice(page)).toBeNull();
});

test('with only female voices installed, nothing is read aloud and the settings say why, with a link to the fix', async ({ page }) => {
  await setUp(page, FEMALE_ONLY);
  await openChat(page);
  // The conversation itself carries no voice explanations.
  await expect(page.getByTestId('assistant-messages')).not.toContainText('voice');
  await page.getByTestId('assistant-input').fill('Hello');
  await page.getByTestId('assistant-input').press('Enter');
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
  await expect(page.getByTestId('read-aloud')).toHaveCount(0); // Al Mulhim has no man's voice here
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(0);
  await openChatSettings(page);
  const notice = page.getByTestId('talk-no-voice');
  await expect(notice).toContainText('No suitable voice in this browser');
  await expect(notice.getByRole('link', { name: 'How to fix' })).toHaveAttribute('href', /\/settings/);
});
