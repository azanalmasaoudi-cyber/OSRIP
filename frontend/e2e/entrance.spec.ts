import { expect, test, type Locator, type Page } from '@playwright/test';

// The first-visit entrance: the scene (an illustrated Omani man carries the OSRIP sign in,
// sets it down in the centre, lets go and steps aside), then both names, the three goals,
// Explore and Skip. Remembered in this browser only, replayable from Settings and the footer,
// keyboard-operable, and with still-frame fallbacks for reduced motion, low-power devices
// and a scene that cannot load. Each test starts from a clean browser (no "seen" flag).
//
// Timing tests run on Playwright's fake clock (it drives requestAnimationFrame), so each
// moment of the scene is checked deterministically.
test.use({ storageState: { cookies: [], origins: [] } });

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const b = await locator.boundingBox();
  if (!b) throw new Error('element has no box');
  return b;
}
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
const centreX = (b: Box) => b.x + b.width / 2;

/** A device that is not low-power, whatever machine runs the test. */
async function ordinaryDevice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  });
}

/** Freezes time: it moves only when a test calls page.clock.runFor. */
async function freezeTime(page: Page): Promise<void> {
  await page.clock.install({ time: new Date('2026-10-10T08:00:00Z') });
  await page.clock.pauseAt(new Date('2026-10-10T08:00:01Z'));
}

/** Opens a page and waits (stepping the frozen clock lightly) until the scene is playing. */
async function openWithScene(page: Page, url: string): Promise<Locator> {
  const loaded = page.waitForResponse(/EntranceScene/);
  await page.goto(url);
  await loaded;
  const scene = page.getByTestId('entrance-scene');
  for (let i = 0; i < 150 && (await scene.count()) === 0; i += 1) {
    await page.clock.runFor(8);
    await page.waitForTimeout(25);
  }
  await expect(scene).toHaveAttribute('data-mode', 'play');
  return scene;
}

async function parts(page: Page) {
  return {
    board: await box(page.getByTestId('entrance-sign-board')),
    torso: await box(page.locator('[data-part="torso"]')),
    stage: await box(page.getByTestId('entrance-stage')),
    nearHand: await box(page.getByTestId('entrance-hand-near')),
  };
}

test('first visit: he carries the sign in, sets it down in the centre, lets go and steps aside; then the text', async ({ page }) => {
  test.setTimeout(90_000); // steps through the scene a tenth of a second at a time
  await ordinaryDevice(page);
  await freezeTime(page);
  await page.addInitScript(() => {
    // No sound: count any attempt to create audio.
    const w = window as unknown as { __audio: number; AudioContext: typeof AudioContext };
    w.__audio = 0;
    const Original = w.AudioContext;
    w.AudioContext = class extends Original { constructor() { super(); w.__audio += 1; } };
  });
  const scene = await openWithScene(page, '/');
  const entrance = page.getByTestId('entrance');
  await expect(entrance).toBeVisible();
  // Skip and Explore work from the first moment; focus starts on Explore.
  await expect(page.getByTestId('entrance-skip')).toBeEnabled();
  await expect(page.getByTestId('entrance-explore')).toBeFocused();
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-revealed', 'false');

  // Carrying: both hands round the sign's edges, the sign off the floor, beside him.
  await page.clock.runFor(1500);
  await expect(scene).toHaveAttribute('data-phase', 'enter');
  await expect(page.getByTestId('entrance-grip-near')).toBeVisible();
  await expect(page.getByTestId('entrance-grip-far')).toBeVisible();
  const carried = await parts(page);
  expect(overlaps(carried.nearHand, await box(page.getByTestId('entrance-grip-near')))).toBe(true);
  expect(overlaps(carried.torso, carried.board)).toBe(true);

  // The sequence, frame by frame, in order, within about 4 to 6 seconds.
  const seen: Array<[string, number]> = [['enter', 0]];
  let elapsed = 1.5;
  while (elapsed < 8) {
    await page.clock.runFor(100);
    elapsed += 0.1;
    const phase = (await scene.getAttribute('data-phase')) ?? '';
    if (phase !== seen.at(-1)?.[0]) seen.push([phase, elapsed]);
    if (phase === 'settled') break;
  }
  expect(seen.map(([phase]) => phase)).toEqual(['enter', 'lower', 'release', 'rise', 'aside', 'turn', 'present', 'settled']);
  const total = seen.at(-1)?.[1] ?? 0;
  expect(total).toBeGreaterThanOrEqual(4);
  expect(total).toBeLessThanOrEqual(6.2);
  await expect(scene).toHaveAttribute('data-mode', 'done');

  // Placed: on the floor (lower than while carried), in the centre; let go; he stands aside.
  const placed = await parts(page);
  expect(placed.board.y - carried.board.y).toBeGreaterThan(10);
  expect(Math.abs(centreX(placed.board) - centreX(placed.stage))).toBeLessThan(3);
  await expect(page.getByTestId('entrance-grip-near')).toBeHidden();
  await expect(page.getByTestId('entrance-grip-far')).toBeHidden();
  expect(overlaps(placed.nearHand, placed.board)).toBe(false);
  expect(placed.torso.x).toBeGreaterThan(placed.board.x + placed.board.width);
  expect(await page.getByTestId('entrance-sign-text').textContent()).toBe('OSRIP');

  // The names and goals are revealed.
  await page.clock.runFor(1000);
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-revealed', 'true');
  await expect(entrance.getByRole('heading', { name: 'OSRIP' })).toBeAttached();
  await expect(page.getByTestId('entrance-name-en')).toHaveText('Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('entrance-name-ar')).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
  const goals = page.getByTestId('entrance-goals');
  for (const text of ['Understand Oman’s resources', 'فهم موارد عُمان', 'Analyse reliable data', 'تحليل البيانات الموثوقة',
    'Support informed decisions', 'دعم القرارات المبنية على البيانات']) {
    await expect(goals).toContainText(text);
  }
  await expect(goals.locator('li').last()).toHaveCSS('opacity', '1');
  await expect(entrance.locator('audio, video')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __audio: number }).__audio)).toBe(0);

  // Explore from the home page opens the overview, and the entrance is remembered.
  await page.getByTestId('entrance-explore').click();
  await page.clock.runFor(500);
  await expect(entrance).toBeHidden();
  await expect(page).toHaveURL(/\/overview/);
  await page.reload();
  await page.clock.runFor(500);
  await expect(page.getByTestId('entrance')).toBeHidden();
});

test('the page behind loads its data while the entrance plays', async ({ page }) => {
  await ordinaryDevice(page);
  await freezeTime(page);
  await openWithScene(page, '/overview?mode=synthetic');
  await page.clock.runFor(300);
  await expect(page.getByTestId('entrance-scene')).toHaveAttribute('data-phase', 'enter');
  await expect(page.getByTestId('indicator-card').first()).toBeAttached();
});

test('Skip works at once, a direct link keeps its address, Escape closes, and the footer replays it', async ({ page }) => {
  await page.goto('/trade?mode=synthetic');
  await page.getByTestId('entrance-skip').click(); // no waiting for the scene
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/trade\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
  await page.reload();
  await expect(page.getByTestId('entrance')).toBeHidden();

  const replay = page.getByTestId('replay-entrance');
  await expect(replay).toHaveText('Replay introduction');
  await replay.focus();
  await replay.press('Enter');
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
});

test('Explore on a direct link stays on that page and moves focus to its content', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  await expect(page.locator('#main')).toBeFocused();
});

test('Settings has Replay introduction: the scene plays again from the start and focus returns', async ({ page }) => {
  await ordinaryDevice(page);
  await page.goto('/account');
  await page.getByTestId('entrance-skip').click();
  const settings = page.getByTestId('settings');
  await expect(settings).toContainText('Introduction');
  const replay = settings.getByTestId('settings-replay-entrance');
  await expect(replay).toHaveText('Replay introduction');
  await replay.click();
  await expect(page.getByTestId('entrance')).toBeVisible();
  await expect(page.getByTestId('entrance-scene')).toHaveAttribute('data-mode', /play|done/);
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(replay).toBeFocused();
});

test.describe('Arabic', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  });

  test('right to left: he enters from the right and steps aside to the left; the lettering is not mirrored', async ({ page }) => {
    await ordinaryDevice(page);
    await freezeTime(page);
    const scene = await openWithScene(page, '/');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(scene).toHaveAttribute('data-mirror', 'true');
    await page.clock.runFor(1200);
    const entering = await parts(page);
    expect(centreX(entering.torso)).toBeGreaterThan(centreX(entering.stage));
    await page.clock.runFor(6000);
    await expect(scene).toHaveAttribute('data-phase', 'settled');
    const placed = await parts(page);
    expect(placed.torso.x + placed.torso.width).toBeLessThan(placed.board.x);
    expect(Math.abs(centreX(placed.board) - centreX(placed.stage))).toBeLessThan(3);
    // The sign's face is drawn unmirrored on screen (positive horizontal scale).
    expect(await page.getByTestId('entrance-sign-text').evaluate((el) => (el as SVGGraphicsElement).getScreenCTM()?.a ?? 0)).toBeGreaterThan(0);
    await expect(page.getByTestId('entrance-explore')).toHaveText('ابدأ');
    await expect(page.getByTestId('entrance-skip')).toHaveText('تخطي');
    await expect(page.getByTestId('entrance-names').locator('p').first()).toHaveText('منصة عُمان الذكية لمعلومات الموارد');
  });

  test('Settings in Arabic offers إعادة عرض المقدمة', async ({ page }) => {
    await page.goto('/account');
    await page.getByTestId('entrance-skip').click();
    await expect(page.getByTestId('settings-replay-entrance')).toHaveText('إعادة عرض المقدمة');
  });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });
  test('the final frame appears at once, without movement, and works the same', async ({ page }) => {
    await page.goto('/');
    const scene = page.getByTestId('entrance-scene');
    await expect(scene).toHaveAttribute('data-mode', 'static');
    await expect(scene).toHaveAttribute('data-fallback', 'reduced-motion');
    await expect(scene).toHaveAttribute('data-phase', 'settled');
    await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-revealed', 'true');
    await expect(page.getByTestId('entrance-goals').locator('li').first()).toHaveCSS('opacity', '1');
    await expect(page.getByTestId('entrance-grip-near')).toBeHidden();
    await page.getByTestId('entrance-skip').click();
    await expect(page.getByTestId('entrance')).toBeHidden();
  });
});

test('a low-power device gets the final frame instead of the animation', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 }));
  await page.goto('/');
  const scene = page.getByTestId('entrance-scene');
  await expect(scene).toHaveAttribute('data-mode', 'static');
  await expect(scene).toHaveAttribute('data-fallback', 'low-power');
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-revealed', 'true');
});

test('if the scene cannot load, a plain sign stands in and everything else works', async ({ page }) => {
  await page.route(/EntranceScene/, (route) => route.abort());
  await page.goto('/');
  await expect(page.getByTestId('entrance-scene-fallback')).toContainText('OSRIP');
  await expect(page.getByTestId('entrance-scene')).toHaveCount(0);
  await expect(page.getByTestId('entrance-body')).toHaveAttribute('data-revealed', 'true');
  await expect(page.getByTestId('entrance-goals')).toContainText('Analyse reliable data');
  await page.getByTestId('entrance-explore').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await expect(page).toHaveURL(/\/overview/);
});

test('@mobile on a phone the whole scene fits the screen and plays to the end', async ({ page }) => {
  await ordinaryDevice(page);
  await freezeTime(page);
  const scene = await openWithScene(page, '/');
  await page.clock.runFor(1200);
  await expect(page.getByTestId('entrance-grip-far')).toBeVisible();
  await page.clock.runFor(6000);
  await expect(scene).toHaveAttribute('data-phase', 'settled');
  const viewport = page.viewportSize();
  const placed = await parts(page);
  for (const b of [placed.board, placed.torso, placed.stage]) {
    expect(b.x).toBeGreaterThanOrEqual(0);
    expect(b.x + b.width).toBeLessThanOrEqual(viewport?.width ?? 0);
  }
  expect(placed.torso.x).toBeGreaterThan(placed.board.x + placed.board.width);
  const overflow = await page.getByTestId('entrance').evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(page.getByTestId('entrance-explore')).toBeVisible();
  await expect(page.getByTestId('entrance-skip')).toBeVisible();
});
