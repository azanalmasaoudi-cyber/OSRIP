import { expect, test, type Page } from '@playwright/test';

// The opening: about three seconds of the project name (OSRIP, then the full name in English and
// Arabic) on a navy and emerald field, then the application. No portraits, no images, no sound.
// Shown once per browser session on the home page only (a direct link opens its page at once);
// Skip works at once and Escape closes; it ends on the page it opened on (never a redirect);
// replayable from Settings and the footer; switchable off in Settings; a plain fade under reduced
// motion or on a low-power device. Each test starts from a clean browser.
test.use({ storageState: { cookies: [], origins: [] } });

/** A device that is not low-power, whatever machine runs the test. */
async function ordinaryDevice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  });
}

/**
 * Holds the opening's own timer (OPENING_MS, OPENING_STILL_MS) until the test releases it, so a
 * busy test machine cannot let it end before the checks run. The delays asked for are recorded.
 * Test-side only: the application is unchanged.
 */
async function holdOpening(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as {
      __held: Array<() => void>; __delays: number[]; __finishOpening: () => void;
      setTimeout: typeof window.setTimeout;
    };
    const original = window.setTimeout.bind(window);
    w.__held = [];
    w.__delays = [];
    w.__finishOpening = () => w.__held.splice(0).forEach((fn) => fn());
    w.setTimeout = ((fn: TimerHandler, delay?: number, ...args: unknown[]) => {
      if (delay === 3000 || delay === 2200) {
        w.__delays.push(delay);
        w.__held.push(() => (typeof fn === 'function' ? fn(...args) : undefined));
        return 0;
      }
      return original(fn, delay, ...args);
    }) as typeof window.setTimeout;
  });
}

async function finishOpening(page: Page): Promise<void> {
  await page.evaluate(() => (window as unknown as { __finishOpening: () => void }).__finishOpening());
}

test('it ends by itself about three seconds after it starts', async ({ page }) => {
  // The page records when the opening dialog opens and closes, so a slow first load of the
  // development server cannot hide it from the test.
  await page.addInitScript(() => {
    const w = window as unknown as { __opening: { opened?: number; closed?: number } };
    w.__opening = {};
    const { showModal, close } = HTMLDialogElement.prototype;
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      if (this.dataset.testid === 'entrance') w.__opening.opened = performance.now();
      return showModal.call(this);
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement, value?: string) {
      if (this.dataset.testid === 'entrance') w.__opening.closed = performance.now();
      return close.call(this, value);
    };
  });
  await page.goto('/');
  await expect(page.getByTestId('entrance')).toBeHidden({ timeout: 10_000 });
  const times = await page.evaluate(() => (window as unknown as { __opening: { opened?: number; closed?: number } }).__opening);
  expect(times.opened).toBeDefined();
  const lasted = (times.closed ?? 0) - (times.opened ?? 0);
  expect(lasted).toBeGreaterThan(2_500);
  expect(lasted).toBeLessThan(4_500);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId('home-page')).toBeVisible();
});

test('first visit: the name in both languages, then the application', async ({ page }) => {
  await ordinaryDevice(page);
  await holdOpening(page);
  await page.addInitScript(() => {
    // No sound: count any attempt to create audio.
    const w = window as unknown as { __audio: number; AudioContext: typeof AudioContext };
    w.__audio = 0;
    const Original = w.AudioContext;
    w.AudioContext = class extends Original { constructor() { super(); w.__audio += 1; } };
  });
  await page.goto('/');
  const entrance = page.getByTestId('entrance');
  await expect(entrance).toBeVisible();
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  await expect(page.getByTestId('entrance-skip')).toBeFocused(); // Skip from the first moment
  await expect(page.getByTestId('entrance-title')).toHaveAccessibleName('OSRIP');
  await expect(page.getByTestId('entrance-title')).toHaveText('OSRIP');
  await expect(page.getByTestId('entrance-name-en')).toHaveText('Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لذكاء الموارد');
  await expect(page.getByTestId('entrance-name-ar')).toHaveAttribute('dir', 'rtl');
  // Only the name: no portraits, images, video or sound.
  await expect(entrance.locator('img, video, audio, figure')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __audio: number }).__audio)).toBe(0);

  // The whole sequence is 3 s; when it ends, the visitor stays on the page it opened on.
  expect(await page.evaluate(() => (window as unknown as { __delays: number[] }).__delays).then((d) => [...new Set(d)])).toEqual([3000]);
  await finishOpening(page);
  await expect(entrance).toBeHidden();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.locator('#main')).toBeFocused();
  await page.reload();
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('once per browser session: a new session shows it again, a reload in the same session does not', async ({ browser, baseURL }) => {
  test.setTimeout(90_000); // two full browser sessions
  for (let session = 0; session < 2; session += 1) {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();
    await holdOpening(page);
    await page.goto('/');
    await expect(page.getByTestId('entrance')).toBeVisible();
    await page.reload(); // shown as soon as it opened: no loop on reload
    await expect(page.getByTestId('home-page')).toBeVisible();
    await expect(page.getByTestId('entrance')).toBeHidden();
    await context.close();
  }
});

test('the page behind loads its data while the opening plays', async ({ page }) => {
  await holdOpening(page);
  await page.goto('/?mode=synthetic');
  await expect(page.getByTestId('entrance')).toBeVisible();
  // The latest figures have finished loading (with mock data, the headline figures are unavailable).
  await expect(page.getByTestId('latest-card').first().locator('.tabular-nums, [data-state="data-unavailable"]')).toBeAttached();
});

test('Skip works at once, keeps the page and the data mode', async ({ page }) => {
  await holdOpening(page);
  await page.goto('/?mode=synthetic');
  await page.getByTestId('entrance-skip').click(); // no waiting
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
});

test('direct links are never interrupted (sign-in included); reaching the home page later shows it once', async ({ page }) => {
  await holdOpening(page);
  await page.goto('/sign-in'); // without the API: the page says sign-in needs it (e2e-api signs in)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.goto('/trade?mode=synthetic');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  expect(await page.evaluate(() => window.sessionStorage.getItem('osrip.entrance'))).toBeNull();
  // The brand link leads home: the opening plays there, once.
  await page.getByRole('link', { name: 'OSRIP' }).filter({ visible: true }).first().click();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape'); // Escape closes
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
});

test('the footer replays it; Escape closes and returns focus to the button', async ({ page }) => {
  await holdOpening(page);
  await page.goto('/energy/water?mode=synthetic');
  const replay = page.getByTestId('replay-entrance');
  await expect(replay).toHaveText('Replay opening');
  await replay.focus();
  await replay.press('Enter');
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
});

test('keyboard: focus stays in the opening while it plays; Enter on Skip closes it', async ({ page }) => {
  await holdOpening(page);
  await page.goto('/');
  await expect(page.getByTestId('entrance-skip')).toBeFocused();
  for (let i = 0; i < 3; i += 1) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => {
      const el = document.activeElement;
      return !el || el === document.body || Boolean(el.closest('[data-testid="entrance"]'));
    })).toBe(true);
  }
  await page.getByTestId('entrance-skip').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/$/);
});

test('Settings: Replay plays it; the automatic showing can be switched off', async ({ page }) => {
  await ordinaryDevice(page);
  await holdOpening(page);
  await page.goto('/account');
  await expect(page.getByTestId('entrance')).toBeHidden(); // a direct link: no opening
  const settings = page.getByTestId('settings');
  await expect(settings).toContainText('Opening');
  await settings.getByTestId('settings-replay-entrance').click();
  await expect(page.getByTestId('entrance')).toBeVisible();
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/account$/);

  const autoplay = page.getByTestId('settings-intro-autoplay');
  await expect(autoplay).toBeChecked();
  await autoplay.uncheck();
  await page.evaluate(() => window.sessionStorage.clear()); // as a new session would be
  await page.goto('/');
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test.describe('Arabic', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  });

  test('right to left: Skip in both languages; OSRIP stays left to right', async ({ page }) => {
    await holdOpening(page);
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('entrance-skip')).toHaveText('تخطّي · Skip');
    await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لذكاء الموارد');
    expect(await page.getByTestId('entrance-title').evaluate((el) => getComputedStyle(el).direction)).toBe('ltr');
  });

  test('Settings in Arabic offers إعادة عرض الافتتاحية', async ({ page }) => {
    await page.goto('/account');
    await expect(page.getByTestId('settings-replay-entrance')).toHaveText('إعادة عرض الافتتاحية');
  });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });
  test('a plain fade: no letter movement or light sweep, and it still ends by itself', async ({ page }) => {
    await holdOpening(page);
    await page.goto('/');
    const body = page.getByTestId('entrance-body');
    await expect(body).toHaveAttribute('data-mode', 'static');
    await expect(body).toHaveAttribute('data-fallback', 'reduced-motion');
    await expect(body).toHaveCSS('animation-name', 'opening-fade');
    await expect(page.locator('.opening-letter').first()).toHaveCSS('animation-name', 'none');
    await expect(page.locator('.opening-sweep')).toHaveCSS('animation-name', 'none');
    expect(await page.evaluate(() => (window as unknown as { __delays: number[] }).__delays).then((d) => [...new Set(d)])).toEqual([2200]);
    await finishOpening(page);
    await expect(page.getByTestId('entrance')).toBeHidden();
    await expect(page).toHaveURL(/\/$/);
  });
});

test('a low-power device gets the plain fade instead of the animation', async ({ page }) => {
  await holdOpening(page);
  await page.addInitScript(() => Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 }));
  await page.goto('/');
  const body = page.getByTestId('entrance-body');
  await expect(body).toHaveAttribute('data-mode', 'static');
  await expect(body).toHaveAttribute('data-fallback', 'low-power');
  await expect(page.locator('.opening-letter').first()).toHaveCSS('animation-name', 'none');
});

test('@mobile on a phone the name fits the screen and Skip is reachable', async ({ page }) => {
  await ordinaryDevice(page);
  await holdOpening(page);
  await page.goto('/');
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  const viewport = page.viewportSize();
  for (const id of ['entrance-title', 'entrance-name-en', 'entrance-name-ar', 'entrance-skip']) {
    const b = await page.getByTestId(id).boundingBox();
    expect(b?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((b?.x ?? 0) + (b?.width ?? 0)).toBeLessThanOrEqual(viewport?.width ?? 0);
  }
  const overflow = await page.getByTestId('entrance').evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
});
