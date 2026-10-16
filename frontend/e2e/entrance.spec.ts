import { expect, test, type Page } from '@playwright/test';

// The first-visit introduction (the owner's design): Al Mulhim and Ilham arrive from the sides,
// the OSRIP sign is set down between them, then both names, the three resources and the three
// goals, with Explore and Skip. Shown on the home page only (a direct link opens its page at
// once), remembered in this browser only, replayable from Settings and the footer,
// keyboard-operable, and still (no movement) under reduced motion or on a low-power device.
// Each test starts from a clean browser (no "seen" flag).
test.use({ storageState: { cookies: [], origins: [] } });

/** A device that is not low-power, whatever machine runs the test. */
async function ordinaryDevice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  });
}

const loaded = (img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0);

test('first visit: both assistants, the sign, the names, three resources and three goals; Explore opens the overview', async ({ page }) => {
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
  // Explore and Skip work from the first moment; focus starts on Explore.
  await expect(page.getByTestId('entrance-explore')).toBeFocused();
  await expect(page.getByTestId('entrance-skip')).toBeEnabled();

  // The two portraits load (the persona images), with the sign between them.
  for (const code of ['mulhim', 'ilham']) {
    const img = page.getByTestId(`entrance-portrait-${code}`).locator('img');
    await expect(img).toHaveAttribute('src', new RegExp(`/images/assistant/${code}-figure-600\\.jpg$`));
    await expect.poll(() => img.evaluate(loaded)).toBeGreaterThan(0);
  }
  // Once the scene has finished: Al Mulhim, the sign (centred, slightly in front) and Ilham.
  await expect(page.getByTestId('entrance-goals')).toHaveCSS('opacity', '1');
  const centre = (b: { x: number; width: number } | null) => (b ? b.x + b.width / 2 : NaN);
  const stage = await page.getByTestId('entrance-stage').boundingBox();
  const sign = await page.getByTestId('entrance-sign').boundingBox();
  const man = await page.getByTestId('entrance-portrait-mulhim').boundingBox();
  const woman = await page.getByTestId('entrance-portrait-ilham').boundingBox();
  expect(Math.abs(centre(sign) - centre(stage))).toBeLessThan(3);
  expect(centre(man)).toBeLessThan((sign?.x ?? 0));
  expect(centre(woman)).toBeGreaterThan((sign?.x ?? 0) + (sign?.width ?? 0));
  await expect(page.getByTestId('entrance-sign-text')).toHaveText('OSRIP');

  await expect(page.getByTestId('entrance-name-en')).toHaveText('Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
  const sectors = page.getByTestId('entrance-sector');
  await expect(sectors).toHaveCount(3);
  await expect(sectors.first()).toContainText('Electricity and energy');
  for (const img of await sectors.locator('img').all()) await expect.poll(() => img.evaluate(loaded)).toBeGreaterThan(0);
  const goals = page.getByTestId('entrance-goals');
  for (const text of ['Understand Oman’s resources', 'افهم موارد عُمان', 'Analyse reliable data', 'حلّل البيانات الموثوقة',
    'Support informed decisions', 'ادعم القرار بالمعلومة']) {
    await expect(goals).toContainText(text);
  }
  await expect(goals).toHaveCSS('opacity', '1'); // revealed after the scene (about 2.3 s)
  await expect(entrance.locator('audio, video')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __audio: number }).__audio)).toBe(0);

  // Explore from the home page opens the overview, and the entrance is remembered.
  await page.getByTestId('entrance-explore').click();
  await expect(entrance).toBeHidden();
  await expect(page).toHaveURL(/\/overview/);
  await page.reload();
  await expect(page.getByTestId('workspace')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('the page behind loads its data while the entrance is open', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await expect(page.getByTestId('entrance')).toBeVisible();
  // The latest figures have finished loading (with mock data, the headline figures are unavailable).
  await expect(page.getByTestId('latest-card').first().locator('.tabular-nums, [data-state="data-unavailable"]')).toBeAttached();
});

test('Skip works at once on the home page, stays there and is remembered', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await page.getByTestId('entrance-skip').click(); // no waiting for the scene
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
  await page.reload();
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('a direct link opens its page without the entrance and keeps its address; Escape closes the replay', async ({ page }) => {
  await page.goto('/trade?mode=synthetic');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/trade\?mode=synthetic$/);
  // Not shown is not seen: the home page still introduces OSRIP later.
  expect(await page.evaluate(() => window.localStorage.getItem('osrip.entrance'))).toBeNull();

  const replay = page.getByTestId('replay-entrance');
  await expect(replay).toHaveText('Replay introduction');
  await replay.focus();
  await replay.press('Enter');
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
});

test('Explore in a replay away from the home page stays on that page', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.getByTestId('replay-entrance').click();
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
});

test('Settings has Replay introduction: the scene plays again from the start and focus returns', async ({ page }) => {
  await ordinaryDevice(page);
  await page.goto('/account');
  await expect(page.getByTestId('entrance')).toBeHidden(); // a direct link: no entrance
  const settings = page.getByTestId('settings');
  await expect(settings).toContainText('Introduction');
  const replay = settings.getByTestId('settings-replay-entrance');
  await expect(replay).toHaveText('Replay introduction');
  await replay.click();
  await expect(page.getByTestId('entrance')).toBeVisible();
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-mode', 'play');
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
});

test.describe('Arabic', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  });

  test('right to left: Arabic first, both languages on the buttons; the stage keeps its order', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('entrance-explore')).toHaveText('ابدأ الاستكشاف · Explore');
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
    await expect(page.getByTestId('entrance')).toBeHidden();
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
  await page.route(/\/images\/(assistant|editorial)\//, (route) => route.abort());
  await page.goto('/');
  await expect(page.getByTestId('entrance-portrait-mulhim').getByTestId('persona-image-fallback')).toBeVisible();
  await expect(page.getByTestId('entrance-portrait-ilham').getByTestId('persona-image-fallback')).toBeVisible();
  await expect(page.getByTestId('entrance-sector')).toHaveCount(3);
  await expect(page.getByTestId('entrance-sector').nth(1)).toContainText('Water resources');
  await expect(page.getByTestId('entrance-goals')).toContainText('Analyse reliable data');
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview/);
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
  await page.getByTestId('entrance-explore').scrollIntoViewIfNeeded();
  await expect(page.getByTestId('entrance-explore')).toBeVisible();
  await expect(page.getByTestId('entrance-skip')).toBeVisible();
});
