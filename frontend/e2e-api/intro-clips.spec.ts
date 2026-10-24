import { expect, test, type Page } from '@playwright/test';

// The recorded introductions (Canva AI Voice clips listed in public/audio/intro/manifest.json):
// hidden while no clip is listed; with clips, played only after a click, stopped by Stop and
// by choosing the other persona, with a volume control and clear loading errors. The audio
// here is a generated test tone served in place of the clips, not a voice and not shipped.

const SCRIPTS = { mulhim: 'السلام عليكم، أنا مُلهم', ilham: 'مرحبًا بك، أنا إلهام' };

/** A short WAV tone (PCM 16-bit mono) as bytes. */
function tone(seconds: number, hz: number): Buffer {
  const rate = 16000;
  const n = Math.round(seconds * rate);
  const data = Buffer.alloc(44 + n * 2);
  data.write('RIFF', 0); data.writeUInt32LE(36 + n * 2, 4); data.write('WAVE', 8);
  data.write('fmt ', 12); data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(rate, 24); data.writeUInt32LE(rate * 2, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34);
  data.write('data', 36); data.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(8000 * Math.sin((2 * Math.PI * hz * i) / rate)), 44 + i * 2);
  return data;
}

async function serveClips(page: Page, { missingFile = false } = {}): Promise<void> {
  await page.route('**/audio/intro/manifest.json', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ clips: {
      mulhim: { ar: { src: 'mulhim-intro-ar.wav', transcript: SCRIPTS.mulhim } },
      ilham: { ar: { src: 'ilham-intro-ar.wav', transcript: SCRIPTS.ilham } },
    } }),
  }));
  await page.route('**/audio/intro/*.wav', (route) => (missingFile
    ? route.fulfill({ status: 404, body: '' })
    : route.fulfill({ contentType: 'audio/wav', body: tone(6, route.request().url().includes('ilham') ? 330 : 220) })));
  // Record what the page does with audio volume (the element is not in the document).
  await page.addInitScript(() => {
    const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'volume');
    Object.defineProperty(HTMLMediaElement.prototype, 'volume', {
      configurable: true,
      get() { return desc?.get?.call(this) as number; },
      set(v: number) { (window as unknown as { __volume: number }).__volume = v; desc?.set?.call(this, v); },
    });
  });
}

test('without a clip the introduction is not offered and the page works', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('assistant-identity-card')).toBeVisible();
  await expect(page.getByTestId('intro-player')).toHaveCount(0);
  await expect(page.getByTestId('assistant-input')).toBeEditable();
});

test('a listed clip plays only after a click, with stop, volume and transcript', async ({ page }) => {
  await serveClips(page);
  const requests: string[] = [];
  page.on('request', (r) => { if (r.url().includes('/audio/intro/') && r.url().endsWith('.wav')) requests.push(r.url()); });
  await page.goto('/assistant?mode=synthetic');
  const player = page.getByTestId('intro-player');
  await expect(player).toHaveAttribute('data-state', 'idle');
  await expect(page.getByTestId('intro-play')).toHaveText('استمع إلى الترحيب / Play introduction');
  await expect(player.getByTestId('intro-recorded')).toContainText('not live speech');
  await page.waitForTimeout(500);
  expect(requests).toHaveLength(0); // nothing is fetched or played on page load

  await player.getByTestId('intro-volume').fill('40');
  await page.getByTestId('intro-play').click();
  await expect(player).toHaveAttribute('data-state', 'playing');
  expect(requests[0]).toContain('mulhim-intro-ar.wav');
  expect(await page.evaluate(() => (window as unknown as { __volume: number }).__volume)).toBeCloseTo(0.4, 2);
  await player.getByTestId('intro-volume').fill('70');
  expect(await page.evaluate(() => (window as unknown as { __volume: number }).__volume)).toBeCloseTo(0.7, 2);
  await expect(page.getByTestId('assistant-status-bar')).toHaveAttribute('data-state', 'speaking');

  await page.getByTestId('intro-stop').click();
  await expect(player).toHaveAttribute('data-state', 'idle');
  await player.getByTestId('intro-transcript-toggle').click();
  await expect(player.getByTestId('intro-transcript')).toContainText(SCRIPTS.mulhim);
  // The volume is remembered for the next visit.
  expect(await page.evaluate(() => window.localStorage.getItem('osrip.intro.volume'))).toBe('70');
});

test('choosing the other persona stops the playing introduction', async ({ page }) => {
  await serveClips(page);
  await page.goto('/assistant?mode=synthetic');
  const card = page.getByTestId('assistant-identity-card');
  await card.getByTestId('persona-option-mulhim').click();
  await page.getByTestId('intro-play').click();
  await expect(page.getByTestId('intro-player')).toHaveAttribute('data-state', 'playing');
  await card.getByTestId('persona-option-ilham').click();
  const player = page.getByTestId('intro-player');
  await expect(player).toHaveAttribute('data-persona', 'ilham');
  await expect(player).toHaveAttribute('data-state', 'idle'); // Al Mulhim's clip stopped
  await expect(page.getByTestId('assistant-status-bar')).not.toHaveAttribute('data-state', 'speaking');
  await page.getByTestId('intro-play').click();
  await expect(player).toHaveAttribute('data-state', 'playing');
  await player.getByTestId('intro-transcript-toggle').click();
  await expect(player.getByTestId('intro-transcript')).toContainText(SCRIPTS.ilham);
  await page.getByTestId('intro-stop').click();
  await card.getByTestId('persona-option-mulhim').click();
});

test('a clip that cannot be loaded says so and the page keeps working', async ({ page }) => {
  await serveClips(page, { missingFile: true });
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('intro-play').click();
  await expect(page.getByTestId('intro-error')).toContainText('could not be loaded');
  await expect(page.getByTestId('intro-player')).toHaveAttribute('data-state', 'load_failed');
  await expect(page.getByTestId('intro-play')).toBeVisible(); // can be tried again
  await page.getByTestId('assistant-input').fill('What is the latest electricity generation?');
  await expect(page.getByTestId('assistant-send')).toBeEnabled();
});
