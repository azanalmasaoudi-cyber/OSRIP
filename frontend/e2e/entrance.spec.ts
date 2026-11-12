import { expect, test, type Page } from '@playwright/test';

// The welcome (the owner's design): the platform's name in both languages, Enter platform, Skip
// introduction, and the four sectors as image cards that open their pages. It stays until the
// visitor chooses. Shown once per browser session on the home page only (a direct link opens its
// page at once); Escape closes; it ends on the page it opened on unless a sector is chosen;
// shown again from Settings, the footer and the sign-in page; switchable off in Settings; no
// movement under reduced motion. Each test starts from a clean browser.
test.use({ storageState: { cookies: [], origins: [] } });

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.getByTestId('entrance').screenshot({ path: `${dir}/${name}-${test.info().project.name}.png` });
}

async function imagesLoaded(page: Page): Promise<boolean[]> {
  return page.getByTestId('welcome-sector').locator('img').evaluateAll((imgs) =>
    (imgs as HTMLImageElement[]).map((i) => i.complete && i.naturalWidth > 0 && i.currentSrc.includes('/images/sectors/')));
}

test('first visit: the welcome in the visitor\'s language; it waits; Enter platform opens the dashboard', async ({ page }) => {
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
  await expect(page.getByTestId('entrance-enter')).toBeFocused();
  await expect(page.getByTestId('entrance-title')).toHaveText('OSRIP');
  await expect(entrance).toHaveAccessibleName('OSRIP');
  await expect(page.getByTestId('entrance-name')).toHaveText('Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('entrance-name-other')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
  await expect(page.getByTestId('entrance-name-other')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('entrance-skip')).toHaveText('Skip introduction');
  // The four sector images, whole, each a link to its page.
  await expect(page.getByTestId('welcome-sector')).toHaveCount(4);
  await expect.poll(() => imagesLoaded(page)).toEqual([true, true, true, true]);
  await expect(entrance.locator('video, audio')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __audio: number }).__audio)).toBe(0);
  await snap(page, 'welcome-light-en');
  // Nothing closes it on a timer.
  await page.waitForTimeout(4_000);
  await expect(entrance).toBeVisible();
  await page.getByTestId('entrance-enter').click();
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
    await page.goto('/');
    await expect(page.getByTestId('entrance')).toBeVisible();
    await page.reload(); // counted as shown as soon as it opened: no loop on reload
    await expect(page.getByTestId('home-page')).toBeVisible();
    await expect(page.getByTestId('entrance')).toBeHidden();
    await context.close();
  }
});

test('the page behind loads its data while the welcome is open', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await expect(page.getByTestId('entrance')).toBeVisible();
  // The latest figures have finished loading (with mock data, the headline figures are unavailable).
  await expect(page.getByTestId('latest-card').first().locator('[data-testid="kpi-value"], [data-state="data-unavailable"]')).toBeAttached();
});

test('Skip introduction keeps the page and the data mode', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
});

test('a sector card opens its sector page; Explore opens the overview', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  const water = page.locator('[data-testid="welcome-sector"][data-sector="water"]');
  await expect(water).toHaveAccessibleName(/Water/);
  await water.click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  await expect(page.getByTestId('sector-page')).toHaveAttribute('data-sector', 'water');
  await page.getByTestId('replay-entrance').click();
  await page.getByTestId('welcome-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview\?mode=synthetic$/);
});

test('the one AI assistant, Al Mulhim, is offered on the welcome and opens the conversation', async ({ page }) => {
  await page.goto('/?mode=synthetic');
  const entrance = page.getByTestId('entrance');
  const assistant = page.getByTestId('welcome-assistant');
  await expect(assistant).toHaveText(/Ask Al Mulhim/);
  await expect(assistant).toHaveAttribute('data-persona', 'mulhim');
  await expect(assistant.locator('img')).toHaveAttribute('src', /mulhim-portrait/);
  await expect(entrance).not.toContainText(/Ilham|إلهام/);
  await expect(page.getByTestId('welcome-sector')).toHaveCount(4); // the four sector images stay
  await assistant.click();
  await expect(entrance).toBeHidden();
  await expect(page).toHaveURL(/\/assistant\?mode=synthetic$/);
  // In Arabic, with the other theme.
  await page.getByTestId('replay-entrance').click();
  await page.getByTestId('welcome-language').click();
  await page.getByTestId('welcome-theme').click();
  await expect(page.getByTestId('welcome-assistant')).toHaveText(/اسأل المُلْهِم/);
  await expect(page.getByTestId('welcome-assistant')).toBeVisible();
});

test('direct links are never interrupted (sign-in included); reaching the home page later shows it once', async ({ page }) => {
  await page.goto('/sign-in'); // without the API: the page says sign-in needs it (e2e-api signs in)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.goto('/trade?mode=synthetic');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('entrance')).toBeHidden();
  expect(await page.evaluate(() => window.sessionStorage.getItem('osrip.entrance'))).toBeNull();
  // The brand link leads home: the welcome opens there, once.
  await page.getByRole('link', { name: 'OSRIP' }).filter({ visible: true }).first().click();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape'); // Escape closes
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/\?mode=synthetic$/);
});

test('the footer shows it again; Escape closes and returns focus to the button', async ({ page }) => {
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

test('keyboard: focus stays in the welcome; every control is reachable; Enter on Skip closes it', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('entrance-enter')).toBeFocused();
  for (let i = 0; i < 12; i += 1) {
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

test('the language and theme chips change the application\'s language and theme', async ({ page }) => {
  await page.goto('/');
  const html = page.locator('html');
  const theme = await html.getAttribute('data-theme');
  await page.getByTestId('welcome-theme').click();
  await expect(html).not.toHaveAttribute('data-theme', theme ?? '');
  await page.getByTestId('welcome-language').click();
  await expect(html).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('entrance-enter')).toHaveText(/الدخول إلى المنصة/);
  await page.getByTestId('entrance-skip').click();
  // Kept for the whole application.
  await expect(html).toHaveAttribute('lang', 'ar');
  expect(await page.evaluate(() => [localStorage.getItem('osrip.language'), localStorage.getItem('osrip.theme')]))
    .toEqual(['ar', theme === 'dark' ? 'light' : 'dark']);
});

test('Settings: Replay shows it; the automatic showing can be switched off', async ({ page }) => {
  await page.goto('/account');
  await expect(page.getByTestId('entrance')).toBeHidden(); // a direct link: no welcome
  const settings = page.getByTestId('settings');
  await expect(settings).toContainText('Opening');
  await settings.getByTestId('settings-replay-entrance').click();
  await expect(page.getByTestId('entrance')).toBeVisible();
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

test.describe('Arabic and the dark theme', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('osrip.language', 'ar');
      window.localStorage.setItem('osrip.theme', 'dark');
    });
  });

  test('right to left: the Arabic name first, the English name below; OSRIP stays left to right', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('entrance-name')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
    await expect(page.getByTestId('entrance-name-other')).toHaveText('Oman Smart Resource Intelligence Platform');
    await expect(page.getByTestId('entrance-enter')).toHaveText(/الدخول إلى المنصة/);
    await expect(page.getByTestId('entrance-skip')).toHaveText('تجاوز المقدمة');
    expect(await page.getByTestId('entrance-title').evaluate((el) => getComputedStyle(el).direction)).toBe('ltr');
    // The hero text sits at the right (the start), the image panel at the left.
    const hero = await page.getByTestId('entrance-title').boundingBox();
    const panel = await page.getByTestId('welcome-panel').boundingBox();
    expect(hero!.x).toBeGreaterThan(panel!.x);
    await expect.poll(() => imagesLoaded(page)).toEqual([true, true, true, true]);
    await snap(page, 'welcome-dark-ar');
  });

  test('Settings in Arabic offers إعادة عرض الافتتاحية', async ({ page }) => {
    await page.goto('/account');
    await expect(page.getByTestId('settings-replay-entrance')).toHaveText('إعادة عرض الافتتاحية');
  });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });
  test('no movement: no transitions, no hover lift; it still waits for the visitor', async ({ page }) => {
    await page.goto('/');
    const enter = page.getByTestId('entrance-enter');
    await expect(enter).toHaveCSS('transition-duration', '0s');
    await enter.hover();
    await expect(enter).toHaveCSS('transform', 'none');
    await expect(page.locator('[data-testid="welcome-sector"]').first()).toHaveCSS('transition-duration', '0s');
    await page.waitForTimeout(2_500);
    await expect(page.getByTestId('entrance')).toBeVisible();
  });
});

test('@mobile on a phone: one column, everything fits, every button reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const dialog = page.getByTestId('entrance');
  await expect(dialog).toBeVisible();
  const overflow = await dialog.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  for (const id of ['entrance-title', 'entrance-name', 'entrance-enter', 'entrance-skip', 'welcome-panel']) {
    const b = await page.getByTestId(id).boundingBox();
    expect(b?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((b?.x ?? 0) + (b?.width ?? 0)).toBeLessThanOrEqual(390.5);
  }
  // The panel comes below the text on a phone.
  const title = await page.getByTestId('entrance-title').boundingBox();
  const panel = await page.getByTestId('welcome-panel').boundingBox();
  expect(panel!.y).toBeGreaterThan(title!.y);
  await snap(page, 'welcome-phone');
  await page.getByTestId('welcome-sector').last().scrollIntoViewIfNeeded();
  await expect.poll(() => imagesLoaded(page)).toEqual([true, true, true, true]);
  await page.getByTestId('entrance-skip').click();
  await expect(dialog).toBeHidden();
});
