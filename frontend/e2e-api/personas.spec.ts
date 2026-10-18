import { expect, test, type Page } from '@playwright/test';

// Two selectable personas through the real stack (scripted model and speech services):
// Al Mulhim (male) and Ilham (female). Choosing one changes the name, portrait, introduction and
// voice; the conversation, the guest allowance and the facts stay the same. Talk shows the
// chosen persona large, says which fallback it is in, asks for the microphone only when the
// mic is pressed and never for the camera.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

// A fake microphone device (permission is granted only in the Talk group).
test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] } });

async function ask(page: Page, text: string): Promise<void> {
  const before = await page.getByTestId('assistant-message').count();
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(before + 1);
  await expect(page.getByTestId('assistant-message').last()).not.toHaveAttribute('data-status', '');
}

async function choose(page: Page, code: 'mulhim' | 'ilham'): Promise<void> {
  await page.getByTestId('persona-picker').first().getByTestId(`persona-option-${code}`).click();
  await expect(page.getByTestId('persona-picker').first()).toHaveAttribute('data-selected', code);
}

test('choosing Ilham changes who answers; switching back keeps the conversation, allowance and facts', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const picker = page.getByTestId('persona-picker').first();
  await expect(picker).toHaveAttribute('data-selected', 'mulhim'); // the default
  await expect(page.getByTestId('mulhim-name')).toHaveText('Al Mulhim');

  await choose(page, 'ilham');
  await expect(page.getByTestId('mulhim-name')).toHaveText('Ilham');
  const avatar = page.getByTestId('assistant-identity').getByTestId('assistant-avatar');
  await expect(avatar).toHaveAttribute('data-persona', 'ilham');
  await expect(avatar.locator('img')).toHaveAttribute('src', /ilham-portrait/);
  await expect(avatar.locator('img')).toHaveAttribute('alt', /fictional Omani woman/);

  // «السلام عليكم» → the approved greeting, in Ilham's words, not charged.
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  await ask(page, 'السلام عليكم');
  const greeting = page.getByTestId('assistant-message').last();
  await expect(greeting).toHaveAttribute('data-persona', 'ilham');
  await expect(greeting.getByTestId('assistant-text')).toContainText('وعليكم السلام ورحمة الله وبركاته');
  await expect(greeting.getByTestId('assistant-text')).toContainText('أنا إلهام، مساعدة OSRIP');
  await expect(greeting.getByTestId('message-persona')).toHaveText('Ilham');
  const allowance = page.getByTestId('guest-allowance');
  await expect(allowance).toHaveAttribute('data-remaining', '5');

  // A factual question as Ilham, then the same question as Al Mulhim.
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'English' }).click();
  await ask(page, 'What was the growth of electricity generation?');
  const asIlham = page.getByTestId('assistant-message').last();
  await expect(asIlham).toHaveAttribute('data-persona', 'ilham');
  const ilhamText = await asIlham.getByTestId('assistant-text').textContent();
  await expect(allowance).toHaveAttribute('data-remaining', '4');

  await choose(page, 'mulhim');
  await ask(page, 'What was the growth of electricity generation?');
  const asMulhim = page.getByTestId('assistant-message').last();
  await expect(asMulhim).toHaveAttribute('data-persona', 'mulhim');
  await expect(asMulhim.getByTestId('assistant-text')).toHaveText(ilhamText ?? '');
  await expect(allowance).toHaveAttribute('data-remaining', '3'); // the count simply continues
  // The same conversation: Ilham's replies are still there, under her name.
  await expect(page.getByTestId('assistant-message')).toHaveCount(3);
  await expect(page.getByTestId('assistant-message').first()).toHaveAttribute('data-persona', 'ilham');

  // The choice is kept in this browser.
  await choose(page, 'ilham');
  await page.reload();
  await expect(page.getByTestId('persona-picker').first()).toHaveAttribute('data-selected', 'ilham');
});

test('a signed-in choice is saved on the account and follows to another browser', async ({ page, browser }) => {
  const signIn = async (p: Page) => {
    await p.goto('/sign-in');
    await p.getByTestId('sign-in-form').getByLabel('E-mail address').fill('viewer@e2e.invalid');
    await p.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
    await p.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
    await expect(p.getByTestId('account-page')).toBeVisible();
  };
  await signIn(page);
  const settings = page.getByTestId('settings-persona');
  await expect(settings.getByTestId('persona-note')).toContainText('saved on your account');
  const saved = page.waitForResponse((r) => r.url().endsWith('/assistant/persona') && r.request().method() === 'PUT');
  await settings.getByTestId('persona-option-ilham').click();
  expect((await saved).status()).toBe(200);

  // Another browser: no cookies or saved choice; only the introduction is switched off.
  const baseURL = test.info().project.use.baseURL ?? '';
  const other = await browser.newContext({
    baseURL,
    storageState: { cookies: [], origins: [{ origin: baseURL, localStorage: [{ name: 'osrip.intro.autoplay', value: 'off' }] }] },
  });
  const second = await other.newPage();
  try {
    await signIn(second);
    await expect(second.getByTestId('settings-persona').getByTestId('persona-picker')).toHaveAttribute('data-selected', 'ilham');
    await second.goto('/assistant?mode=synthetic');
    await ask(second, 'Who are you?');
    await expect(second.getByTestId('assistant-message').last().getByTestId('assistant-text')).toContainText('I am Ilham');
  } finally {
    // Leave the shared test account as it was (Al Mulhim, the default).
    await page.goto('/account');
    await page.getByTestId('settings-persona').getByTestId('persona-option-mulhim').click();
    await expect(page.getByTestId('settings-persona').getByTestId('persona-picker')).toHaveAttribute('data-selected', 'mulhim');
    await other.close();
  }
});

test.describe('Talk with the chosen persona', () => {
  test.use({ permissions: ['microphone'] });

  test('Ilham is shown large, the fallback mode is stated, the camera is never requested', async ({ page }) => {
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
    await choose(page, 'ilham');
    await page.getByTestId('open-talk').click();
    const workspace = page.getByTestId('talk-workspace');
    await expect(workspace).toHaveAttribute('data-persona', 'ilham');
    await expect(page.getByRole('heading', { level: 1, name: 'Talk to Ilham' })).toBeFocused();
    await expect(page.getByTestId('talk-figure').locator('img')).toHaveAttribute('src', /ilham-figure/);
    await expect(page.getByTestId('talk-mode')).toHaveText('Fallback mode: push-to-talk, still portrait');
    await expect(page.getByTestId('talk-mode-note')).toContainText('Live avatar mode');
    await expect(page.getByTestId('talk-voice')).toHaveText('Voice: en-GB-SoniaNeural');
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

    // Interrupt: the answer is read with Ilham's configured server voice; Stop speaking ends it.
    const spoken = page.waitForResponse(/\/assistant\/voice\/speak/);
    await sheet.getByTestId('assistant-message').last().getByTestId('read-aloud').click();
    expect((await spoken).headers()['x-voice']).toBe('en-GB-SoniaNeural');
    await page.getByTestId('voice-stop-speaking').click();
    await expect(page.getByTestId('voice-stop-speaking')).toHaveCount(0);

    // The microphone is asked for only now, audio only.
    await sheet.getByTestId('voice-start').click();
    await expect(page.getByTestId('talk-state')).toHaveAttribute('data-state', 'listening');
    const constraints = await page.evaluate(() => (window as unknown as { __media: MediaStreamConstraints[] }).__media);
    expect(constraints).toHaveLength(1);
    expect(constraints[0]?.audio).toBeTruthy();
    expect(constraints[0]?.video ?? false).toBe(false);

    // Switching persona inside Talk keeps the transcript.
    const count = await sheet.getByTestId('assistant-message').count();
    await sheet.getByTestId('voice-cancel').click();
    await page.getByTestId('talk-workspace').getByTestId('persona-option-mulhim').click();
    await expect(page.getByRole('heading', { level: 1, name: 'Talk to Al Mulhim' })).toBeVisible();
    await expect(page.getByTestId('talk-figure').locator('img')).toHaveAttribute('src', /mulhim-figure/);
    await expect(sheet.getByTestId('assistant-message')).toHaveCount(count);

    // End call releases the microphone.
    await page.getByTestId('talk-end').click();
    await expect(page).toHaveURL(/\/assistant/);
    await expect.poll(() => page.evaluate(() => (window as unknown as { __streams: MediaStream[] }).__streams
      .flatMap((s) => s.getTracks()).filter((track) => track.readyState === 'live').length)).toBe(0);
  });
});
