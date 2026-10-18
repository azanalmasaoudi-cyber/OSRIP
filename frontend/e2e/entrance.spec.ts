import { expect, test, type Page } from '@playwright/test';

// The opening introduction (the owner's design, with the images embedded in it): Al Mulhim and
// Ilham arrive from the sides, the OSRIP sign is set down between them, then both names, the
// three resources and the three goals. Shown once per browser session on the home page only (a
// direct link opens its page at once); Explore and Skip enter the dashboard; Escape closes;
// replayable from Settings and the footer; switchable off in Settings; keyboard-operable; still
// under reduced motion or on a low-power device. Each test starts from a clean browser.
test.use({ storageState: { cookies: [], origins: [] } });

/** A device that is not low-power, whatever machine runs the test. */
async function ordinaryDevice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  });
}

const loaded = (img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0);
const centre = (b: { x: number; width: number } | null) => (b ? b.x + b.width / 2 : NaN);

test('first visit: the owner’s images, the sign, the names, three resources and three goals; Explore enters the dashboard once', async ({ page }) => {
  await ordinaryDevice(page);
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
  await expect(page.getByTestId('entrance-explore')).toBeFocused();

  // The portraits and the three illustrations are the introduction's own images, all loaded.
  for (const [id, file] of [['entrance-portrait-mulhim', 'mulhim'], ['entrance-portrait-ilham', 'ilham']]) {
    const img = page.getByTestId(id).locator('img');
    await expect(img).toHaveAttribute('src', `/images/intro/${file}.jpg`);
    await expect.poll(() => img.evaluate(loaded)).toBe(600);
    await expect(img).toHaveCSS('object-fit', 'cover'); // the approved framing: from the top centre
    await expect(img).toHaveCSS('object-position', '50% 0%');
  }
  const sectors = page.getByTestId('entrance-sector');
  await expect(sectors).toHaveCount(3);
  await expect(sectors.first()).toContainText('Electricity and energy');
  const heights: number[] = [];
  for (const [i, file] of ['electricity', 'water', 'trade'].entries()) {
    const img = sectors.nth(i).locator('img');
    await expect(img).toHaveAttribute('src', `/images/intro/${file}.jpg`);
    await expect.poll(() => img.evaluate(loaded)).toBe(600);
    await expect(img).toHaveCSS('object-fit', 'contain'); // complete, never cropped or stretched
    heights.push((await img.boundingBox())?.height ?? 0);
  }
  expect(new Set(heights).size).toBe(1); // one height for all three

  // Once the scene has finished: Al Mulhim, the sign (centred, slightly in front) and Ilham.
  const goals = page.getByTestId('entrance-goals');
  await expect(goals).toHaveCSS('opacity', '1');
  const stage = await page.getByTestId('entrance-stage').boundingBox();
  const sign = await page.getByTestId('entrance-sign').boundingBox();
  expect(Math.abs(centre(sign) - centre(stage))).toBeLessThan(3);
  expect(centre(await page.getByTestId('entrance-portrait-mulhim').boundingBox())).toBeLessThan(sign?.x ?? 0);
  expect(centre(await page.getByTestId('entrance-portrait-ilham').boundingBox())).toBeGreaterThan((sign?.x ?? 0) + (sign?.width ?? 0));
  await expect(page.getByTestId('entrance-sign-text')).toHaveText('OSRIP');
  await expect(page.getByTestId('entrance-name-en')).toHaveText('Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
  for (const text of ['Understand Oman’s resources', 'افهم موارد عُمان', 'Analyse reliable data', 'حلّل البيانات الموثوقة',
    'Support informed decisions', 'ادعم القرار بالمعلومة']) {
    await expect(goals).toContainText(text);
  }
  await expect(entrance.locator('audio, video')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __audio: number }).__audio)).toBe(0);

  // Explore enters the dashboard; the home page does not show it again in this session.
  await page.getByTestId('entrance-explore').click();
  await expect(entrance).toBeHidden();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId('workspace')).toBeVisible();
  await page.goto('/');
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.reload();
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('once per browser session: a new session shows it again, a reload in the same session does not', async ({ browser, baseURL }) => {
  test.setTimeout(90_000); // two full browser sessions
  for (let session = 0; session < 2; session += 1) {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();
    await page.goto('/');
    await expect(page.getByTestId('entrance')).toBeVisible();
    await page.reload(); // shown as soon as it opened: no loop on reload
    await expect(page.getByTestId('home-page')).toBeVisible();
    await expect(page.getByTestId('entrance')).toBeHidden();
    await context.close();
  }
});

test('the page behind loads its data while the introduction is open', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await expect(page.getByTestId('entrance')).toBeVisible();
  // The latest figures have finished loading (with mock data, the headline figures are unavailable).
  await expect(page.getByTestId('latest-card').first().locator('.tabular-nums, [data-state="data-unavailable"]')).toBeAttached();
});

test('Skip works at once and enters the dashboard, keeping the data mode', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await page.getByTestId('entrance-skip').click(); // no waiting for the scene
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
  // Back to the home page in the same session: no second showing.
  await page.goBack();
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('direct links are never interrupted (sign-in included); reaching the home page later shows it once', async ({ page }) => {
  await page.goto('/sign-in'); // without the API: the page says sign-in needs it (e2e-api signs in)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.goto('/trade?mode=synthetic');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  expect(await page.evaluate(() => window.sessionStorage.getItem('osrip.entrance'))).toBeNull();
  // The brand link leads home: the introduction opens there, once.
  await page.getByRole('link', { name: 'OSRIP' }).filter({ visible: true }).first().click();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape'); // Escape only closes
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
});

test('the footer replays it; Escape closes and returns focus; Explore from another page enters the dashboard', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  const replay = page.getByTestId('replay-entrance');
  await expect(replay).toHaveText('Replay introduction');
  await replay.focus();
  await replay.press('Enter');
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  await replay.click();
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview\?mode=synthetic$/);
});

test('keyboard: focus starts on Explore, Shift+Tab reaches Skip, and focus stays in the introduction', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('entrance-explore')).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByTestId('entrance-skip')).toBeFocused();
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => {
      const el = document.activeElement;
      return !el || el === document.body || Boolean(el.closest('[data-testid="entrance"]'));
    })).toBe(true);
  }
  await page.getByTestId('entrance-skip').focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/overview$/);
});

test('Settings: replay, Skip enters the dashboard; the automatic showing can be switched off', async ({ page }) => {
  await ordinaryDevice(page);
  await page.goto('/account');
  await expect(page.getByTestId('entrance')).toBeHidden(); // a direct link: no introduction
  const settings = page.getByTestId('settings');
  await expect(settings).toContainText('Introduction');
  await settings.getByTestId('settings-replay-entrance').click();
  await expect(page.getByTestId('entrance')).toBeVisible();
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  await page.getByTestId('entrance-skip').click();
  await expect(page).toHaveURL(/\/overview$/);

  await page.goto('/account');
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

  test('right to left: Arabic first, both languages on the buttons; the stage keeps its order', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('entrance-explore')).toHaveText('استكشف · Explore');
    await expect(page.getByTestId('entrance-skip')).toHaveText('تخطّي · Skip');
    await expect(page.getByTestId('entrance-names').locator('p').nth(1)).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
    const man = await page.getByTestId('entrance-portrait-mulhim').boundingBox();
    const woman = await page.getByTestId('entrance-portrait-ilham').boundingBox();
    expect(man?.x ?? 0).toBeLessThan(woman?.x ?? 0);
    expect(await page.getByTestId('entrance-sign-text').evaluate((el) => getComputedStyle(el).direction)).toBe('ltr');
  });

  test('Settings in Arabic offers إعادة عرض المقدمة', async ({ page }) => {
    await page.goto('/account');
    await expect(page.getByTestId('settings-replay-entrance')).toHaveText('إعادة عرض المقدمة');
  });
});

test('the light theme gives the introduction its light palette', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.theme', 'light'));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByTestId('entrance')).toHaveCSS('background-color', 'rgb(247, 243, 234)');
  await expect(page.getByTestId('entrance')).toHaveCSS('color', 'rgb(22, 61, 54)');
  await expect(page.getByTestId('entrance-explore')).toHaveCSS('background-color', 'rgb(22, 61, 54)');
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });
  test('the final frame appears at once, without movement, and works the same', async ({ page }) => {
    await page.goto('/');
    const body = page.getByTestId('entrance-body');
    await expect(body).toHaveAttribute('data-mode', 'static');
    await expect(body).toHaveAttribute('data-fallback', 'reduced-motion');
    await expect(page.getByTestId('entrance-sign')).toHaveCSS('animation-name', 'none');
    await expect(page.getByTestId('entrance-goals')).toHaveCSS('opacity', '1');
    await page.getByTestId('entrance-skip').click();
    await expect(page).toHaveURL(/\/overview$/);
  });
});

test('a low-power device gets the final frame instead of the animation', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 }));
  await page.goto('/');
  const body = page.getByTestId('entrance-body');
  await expect(body).toHaveAttribute('data-mode', 'static');
  await expect(body).toHaveAttribute('data-fallback', 'low-power');
  await expect(page.getByTestId('entrance-sign')).toHaveCSS('animation-name', 'none');
});

test('if the images cannot load, neutral badges stand in and everything else works', async ({ page }) => {
  await page.route(/\/images\/intro\//, (route) => route.abort());
  await page.goto('/');
  await expect(page.getByTestId('entrance-portrait-mulhim').getByTestId('persona-image-fallback')).toBeVisible();
  await expect(page.getByTestId('entrance-portrait-ilham').getByTestId('persona-image-fallback')).toBeVisible();
  await expect(page.getByTestId('entrance-sector')).toHaveCount(3);
  await expect(page.getByTestId('entrance-sector').nth(1)).toContainText('Water resources');
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview$/);
});

test('@mobile on a phone the whole scene fits the screen and starts at the top', async ({ page }) => {
  await ordinaryDevice(page);
  await page.goto('/');
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  const viewport = page.viewportSize();
  await expect(page.getByTestId('entrance-goals')).toHaveCSS('opacity', '1');
  for (const id of ['entrance-portrait-mulhim', 'entrance-sign', 'entrance-portrait-ilham', 'entrance-skip']) {
    const b = await page.getByTestId(id).boundingBox();
    expect(b?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((b?.x ?? 0) + (b?.width ?? 0)).toBeLessThanOrEqual(viewport?.width ?? 0);
  }
  expect(await page.getByTestId('entrance').evaluate((el) => el.scrollTop)).toBe(0);
  const overflow = await page.getByTestId('entrance').evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const sectorHeights = await page.getByTestId('entrance-sector').locator('img').evaluateAll((imgs) => imgs.map((i) => i.getBoundingClientRect().height));
  expect(new Set(sectorHeights).size).toBe(1);
  await page.getByTestId('entrance-explore').scrollIntoViewIfNeeded();
  await page.getByTestId('entrance-explore').click();
  await expect(page).toHaveURL(/\/overview$/);
});
