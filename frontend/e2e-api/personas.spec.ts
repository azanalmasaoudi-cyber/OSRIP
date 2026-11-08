import { expect, test, type Page } from '@playwright/test';

import { closeDrawer, openChatSettings } from './chat';

// One assistant persona through the real stack (scripted model and speech services): Al Mulhim
// (assistant profile version 4). There is no persona choice anywhere; a question that still names
// the retired persona (Ilham) is answered by Al Mulhim, while an earlier reply keeps its text
// under a neutral name. Talk shows Al Mulhim large, asks for the microphone only when the mic is
// pressed and never for the camera.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const API = '/api/v1';

// A fake microphone device (permission is granted only in the Talk group).
test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] } });

async function ask(page: Page, text: string): Promise<void> {
  const before = await page.getByTestId('assistant-message').count();
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(before + 1);
  await expect(page.getByTestId('assistant-message').last()).not.toHaveAttribute('data-status', '');
}

/** The answer language is in the conversation settings. */
async function answerIn(page: Page, name: 'العربية' | 'English'): Promise<void> {
  await openChatSettings(page);
  await page.getByTestId('assistant-language').getByRole('radio', { name }).click();
  await closeDrawer(page);
}

async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('Username').fill('viewer@e2e.invalid');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
}

test('Al Mulhim is the only assistant: no persona choice, his name, portrait and greeting', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('persona-picker')).toHaveCount(0);
  await expect(page.getByTestId('mulhim-name')).toHaveText('Al Mulhim');
  const avatar = page.getByTestId('chat-header').getByTestId('assistant-avatar');
  await expect(avatar).toHaveAttribute('data-persona', 'mulhim');
  await expect(avatar.locator('img')).toHaveAttribute('src', /mulhim-portrait/);
  await expect(page.locator('img[src*="ilham"]')).toHaveCount(0);

  // «السلام عليكم» → the approved greeting, in Al Mulhim's words, not charged.
  await answerIn(page, 'العربية');
  await ask(page, 'السلام عليكم');
  const greeting = page.getByTestId('assistant-message').last();
  await expect(greeting).toHaveAttribute('data-persona', 'mulhim');
  await expect(greeting.getByTestId('assistant-text')).toContainText('وعليكم السلام ورحمة الله وبركاته');
  await expect(greeting.getByTestId('assistant-text')).toContainText('أنا المُلْهِم');
  await expect(greeting.getByTestId('message-persona')).toHaveText('Al Mulhim');
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  await expect(page.locator('body')).not.toContainText('إلهام');
  await expect(page.locator('body')).not.toContainText('Ilham');
});

test('a question naming the retired persona is answered by Al Mulhim; it cannot be saved as a choice', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await ask(page, 'Hello'); // opens the guest session
  const csrf = (await page.context().cookies()).find((c) => c.name === 'osrip_guest_csrf')?.value ?? '';
  const asked = await page.request.post(`${API}/assistant/guest/messages`, {
    headers: { 'X-Guest-CSRF': csrf },
    data: { content: 'Who are you?', language: 'en', request_id: crypto.randomUUID(), data_mode: 'synthetic', persona: 'ilham' },
  });
  expect(asked.status()).toBe(201);
  const body = await asked.json();
  expect(body.message.persona).toBe('mulhim');
  expect(body.message.content).toContain('I am Al Mulhim');

  await signIn(page);
  const csrfToken = (await page.context().cookies()).find((c) => c.name === 'osrip_csrf')?.value ?? '';
  const saved = await page.request.put(`${API}/assistant/persona`, {
    headers: { 'X-CSRF-Token': csrfToken }, data: { persona: 'ilham' },
  });
  expect(saved.status()).toBe(422);
  // The account settings name the one assistant and offer no choice.
  const settings = page.getByTestId('settings-persona');
  await expect(settings).toContainText('Al Mulhim answers your questions');
  await expect(settings.getByTestId('persona-picker')).toHaveCount(0);
});

test('an earlier reply by the retired persona keeps its text under a neutral name', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await ask(page, 'Who are you?');
  const text = await page.getByTestId('assistant-message').last().getByTestId('assistant-text').textContent();
  // The stored reply as an earlier conversation would hold it: given by Ilham.
  await page.route(/\/api\/v1\/assistant\/guest\/conversations\/[0-9a-f-]+$/, async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    for (const m of json.messages) if (m.role === 'assistant') m.persona = 'ilham';
    await route.fulfill({ response, json });
  });
  await page.reload();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-persona', 'ilham');
  await expect(reply.getByTestId('message-persona')).toHaveText('Earlier assistant persona');
  await expect(reply.getByTestId('message-persona').locator('img')).toHaveAttribute('data-testid', 'persona-image-fallback');
  await expect(reply.getByTestId('assistant-text')).toHaveText(text ?? '');
  await expect(page.getByTestId('mulhim-name')).toHaveText('Al Mulhim');
});

test.describe('Talk with Al Mulhim', () => {
  test.use({ permissions: ['microphone'] });

  test('Al Mulhim is shown in Talk, push-to-talk with his voice, the camera is never requested', async ({ page }) => {
    await page.addInitScript(() => {
      const store = window as unknown as { __media: MediaStreamConstraints[]; __streams: MediaStream[] };
      store.__media = [];
      store.__streams = [];
      const media = navigator.mediaDevices;
      const original = media.getUserMedia.bind(media);
      media.getUserMedia = async (constraints) => {
        store.__media.push(constraints ?? {});
        const stream = await original(constraints);
        store.__streams.push(stream);
        return stream;
      };
    });
    await page.goto('/assistant?mode=synthetic');
    await openChatSettings(page); // Talk is offered in the conversation settings (Voice)
    await page.getByTestId('open-talk').click();
    const workspace = page.getByTestId('talk-workspace');
    await expect(workspace).toHaveAttribute('data-persona', 'mulhim');
    await expect(page.getByRole('heading', { level: 1, name: 'Talk to Al Mulhim' })).toBeFocused();
    await expect(page.getByTestId('talk-figure').locator('img')).toHaveAttribute('src', /mulhim-figure/);
    await expect(workspace.getByTestId('persona-picker')).toHaveCount(0);
    await expect(workspace).toHaveAttribute('data-mode', 'push_to_talk');
    await expect(workspace).toHaveAttribute('data-voice', 'en-GB-RyanNeural');
    // Every control is there: transcript, language, microphone, mute, End call, Close.
    const sheet = page.getByTestId('talk-sheet');
    for (const id of ['assistant-language', 'voice-start', 'voice-mute', 'assistant-input']) {
      await expect(sheet.getByTestId(id)).toBeVisible();
    }
    await expect(page.getByTestId('talk-end')).toBeVisible();
    await expect(page.getByTestId('talk-close')).toBeVisible();
    // Nothing has asked for a device yet.
    expect(await page.evaluate(() => (window as unknown as { __media: unknown[] }).__media.length)).toBe(0);

    // Greeting and the purpose with the three domains.
    await sheet.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
    await sheet.getByTestId('assistant-input').fill('السلام عليكم');
    await sheet.getByTestId('assistant-send').click();
    await expect(sheet.getByTestId('assistant-message').last().getByTestId('assistant-text')).toContainText('وعليكم السلام ورحمة الله وبركاته');
    await sheet.getByTestId('assistant-language').getByRole('radio', { name: 'English' }).click();
    await sheet.getByTestId('assistant-input').fill('What is OSRIP?');
    await sheet.getByTestId('assistant-send').click();
    const about = sheet.getByTestId('assistant-message').last().getByTestId('assistant-text');
    await expect(about).toContainText('decision support on Oman');
    await expect(about).toContainText('Energy and Essential Services');
    await expect(about).toContainText('Food Security');
    await expect(about).toContainText('Trade');

    // Interrupt: the answer is read with Al Mulhim's configured server voice; Stop speaking ends it.
    const spoken = page.waitForResponse(/\/assistant\/voice\/speak/);
    await sheet.getByTestId('assistant-message').last().getByTestId('read-aloud').click();
    expect((await spoken).headers()['x-voice']).toBe('en-GB-RyanNeural');
    await page.getByTestId('voice-stop-speaking').click();
    await expect(page.getByTestId('voice-stop-speaking')).toHaveCount(0);

    // The microphone is asked for only now, audio only.
    await sheet.getByTestId('voice-start').click();
    await expect(page.getByTestId('talk-state')).toHaveAttribute('data-state', 'listening');
    const constraints = await page.evaluate(() => (window as unknown as { __media: MediaStreamConstraints[] }).__media);
    expect(constraints).toHaveLength(1);
    expect(constraints[0]?.audio).toBeTruthy();
    expect(constraints[0]?.video ?? false).toBe(false);
    await sheet.getByTestId('voice-cancel').click();

    // End call releases the microphone.
    await page.getByTestId('talk-end').click();
    await expect(page).toHaveURL(/\/assistant/);
    await expect.poll(() => page.evaluate(() => (window as unknown as { __streams: MediaStream[] }).__streams
      .flatMap((s) => s.getTracks()).filter((track) => track.readyState === 'live').length)).toBe(0);
  });
});
