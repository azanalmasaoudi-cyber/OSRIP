import { expect, test, type Page } from '@playwright/test';

// "Talk to Al Mulhim" on the real API with the scripted model and speech services: the
// workspace states honestly that it is push-to-talk (no LiveKit project is configured), the
// portrait is labelled static, typing still works, a spoken question is transcribed for review
// before it is sent, the answer is read aloud and can be interrupted, and ending the call
// stops everything. Microphone permission is denied unless a test grants it.

// A fake microphone device for every test here; permission is granted only where a test asks.
test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] } });

async function openTalk(page: Page): Promise<void> {
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('open-talk').click();
  await expect(page.getByTestId('talk-workspace')).toBeVisible();
}

test('the workspace is full-viewport, labelled push-to-talk, and typing works as a fallback', async ({ page }) => {
  await openTalk(page);
  await expect(page).toHaveURL(/\/talk\?mode=synthetic/);
  await expect(page.getByRole('heading', { level: 1, name: 'Talk to Al Mulhim' })).toBeFocused();
  await expect(page.getByTestId('talk-mode')).toHaveText('Fallback mode: push-to-talk, still portrait');
  await expect(page.getByTestId('talk-portrait-note')).toContainText('does not move its lips');
  await page.getByTestId('talk-realtime').locator('summary').click();
  await expect(page.getByTestId('talk-realtime')).toContainText('OSRIP_LIVEKIT_URL');
  // The page behind is inert: the floating orb is gone and the app root cannot take focus.
  await expect(page.getByTestId('open-assistant')).toHaveCount(0);
  await expect(page.locator('#root')).toHaveAttribute('inert', '');

  const sheet = page.getByTestId('talk-sheet');
  await sheet.getByTestId('assistant-input').fill('What was the growth of electricity generation?');
  await sheet.getByTestId('assistant-send').click();
  await expect(sheet.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence/);

  await page.getByTestId('talk-end').click();
  await expect(page).toHaveURL(/\/assistant\?mode=synthetic/);
  await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
});

test('a denied microphone is explained and the text box still works', async ({ page }) => {
  await openTalk(page);
  const sheet = page.getByTestId('talk-sheet');
  await sheet.getByTestId('voice-start').click();
  await expect(sheet.getByTestId('voice-notice')).toBeVisible();
  await expect(sheet.getByTestId('voice-recording')).toHaveCount(0);
  await sheet.getByTestId('assistant-input').fill('Hello');
  await sheet.getByTestId('assistant-send').click();
  await expect(sheet.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
});

test.describe('with a (fake) microphone', () => {
  test.use({ permissions: ['microphone'] });

  test('push-to-talk: speak, review, send, hear the answer, interrupt it and end the call', async ({ page }) => {
    // Record every microphone stream the page opens, to check they are all stopped at the end.
    await page.addInitScript(() => {
      const media = navigator.mediaDevices;
      const original = media.getUserMedia.bind(media);
      const store = window as unknown as { __streams: MediaStream[] };
      store.__streams = [];
      media.getUserMedia = async (constraints) => {
        const stream = await original(constraints);
        store.__streams.push(stream);
        return stream;
      };
    });
    await openTalk(page);
    const sheet = page.getByTestId('talk-sheet');
    await sheet.getByTestId('voice-start').click();
    await expect(sheet.getByTestId('voice-recording')).toBeVisible();
    await expect(page.getByTestId('talk-state')).toHaveAttribute('data-state', 'listening');
    await page.waitForTimeout(800); // a little fake microphone audio
    await sheet.getByTestId('voice-stop').click();
    // The transcript fills the box for review; nothing is sent by itself.
    await expect(sheet.getByTestId('assistant-input')).toHaveValue('What is the latest electricity generation figure?');
    await expect(sheet.getByTestId('voice-review')).toBeVisible();
    const before = await sheet.getByTestId('assistant-message').count();
    await sheet.getByTestId('assistant-send').click();
    await expect(sheet.getByTestId('assistant-message')).toHaveCount(before + 1); // the reply (questions are not counted)
    // The spoken reply plays (scripted tone); Stop speaking interrupts it.
    const stopSpeaking = page.getByTestId('voice-stop-speaking');
    await expect(stopSpeaking).toBeVisible();
    await stopSpeaking.click();
    await expect(stopSpeaking).toHaveCount(0);
    await expect(page.getByTestId('talk-state')).not.toHaveAttribute('data-state', 'speaking');
    // Ending the call while listening releases the microphone.
    await sheet.getByTestId('voice-start').click();
    await expect(page.getByTestId('talk-state')).toHaveAttribute('data-state', 'listening');
    await page.getByTestId('talk-end').click();
    await expect(page).toHaveURL(/\/assistant/);
    // A microphone that was still opening is closed as soon as it opens.
    await expect.poll(() => page.evaluate(() => (window as unknown as { __streams: MediaStream[] }).__streams
      .flatMap((s) => s.getTracks()).filter((track) => track.readyState === 'live').length)).toBe(0);
  });

  test('switching the answer language to Arabic transcribes and answers in Arabic', async ({ page }) => {
    await openTalk(page);
    const sheet = page.getByTestId('talk-sheet');
    await sheet.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
    await sheet.getByTestId('voice-start').click();
    await expect(sheet.getByTestId('voice-recording')).toBeVisible();
    await page.waitForTimeout(800);
    await sheet.getByTestId('voice-stop').click();
    await expect(sheet.getByTestId('assistant-input')).toHaveValue('ما آخر رقم لتوليد الكهرباء؟');
  });

  test('a failing speech service is reported and typing still works', async ({ page }) => {
    await page.route(/\/api\/v1\/assistant\/voice\/transcribe/, (route) => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'speech_unavailable', message: 'The speech service is not available.' } }),
    }));
    await openTalk(page);
    const sheet = page.getByTestId('talk-sheet');
    await sheet.getByTestId('voice-start').click();
    await expect(sheet.getByTestId('voice-recording')).toBeVisible();
    await page.waitForTimeout(800);
    await sheet.getByTestId('voice-stop').click();
    await expect(sheet.getByTestId('voice-notice')).toBeVisible();
    await expect(sheet.getByTestId('assistant-input')).toHaveValue('');
    await sheet.getByTestId('assistant-input').fill('Hello');
    await sheet.getByTestId('assistant-send').click();
    await expect(sheet.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
  });
});
