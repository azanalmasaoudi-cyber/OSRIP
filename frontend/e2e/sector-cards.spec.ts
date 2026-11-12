import { expect, test, type Locator, type Page } from '@playwright/test';

// The four sector cards on the dashboard and the image on each sector page (mock adapter).
// Water, food security and trade are the supplied artworks (PNG, served as WebP where the browser
// reads it). Electricity is a credited photograph of power lines in Oman (CC BY-SA 4.0), cropped
// to the same ratio, with the frame, name and a short credit laid over it.

const SECTORS = [
  { section: 'electricity', art: 'electricity', file: 'photos/electricity-pylons-oman', path: /\/energy\/electricity/ },
  { section: 'water', art: 'water', file: 'sectors/osrip_water', path: /\/energy\/water/ },
  { section: 'food_security', art: 'food', file: 'sectors/osrip_food_security', path: /\/food-security/ },
  { section: 'trade', art: 'trade', file: 'sectors/osrip_trade', path: /\/trade/ },
] as const;

/** The image has loaded, is the expected file and is drawn at its own ratio (not stretched): the
 * artworks whole (`contain`), the photograph cropped to the same box (`cover`). */
async function expectArtwork(art: Locator, file: string): Promise<void> {
  const img = art.locator('img');
  await img.scrollIntoViewIfNeeded();
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  const shown = await img.evaluate((el: HTMLImageElement) => ({
    src: el.currentSrc,
    natural: el.naturalWidth / el.naturalHeight,
    drawn: el.getBoundingClientRect().width / el.getBoundingClientRect().height,
    fit: getComputedStyle(el).objectFit,
  }));
  expect(shown.src).toContain(`/images/${file}`);
  expect(Math.abs(shown.natural - 1672 / 941)).toBeLessThan(0.01);
  expect(Math.abs(shown.drawn - 1672 / 941)).toBeLessThan(0.02);
  expect(shown.fit).toBe(file.startsWith('photos/') ? 'cover' : 'contain');
}

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string, target?: Locator): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (!dir) return;
  const path = `${dir}/${name}-${test.info().project.name}.png`;
  await (target ? target.screenshot({ path }) : page.screenshot({ path }));
}

async function noSidewaysScroll(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

test('the dashboard shows the four sector cards, each opening its own sector page', async ({ page }) => {
  await page.goto('/');
  const cards = page.getByTestId('home-sector');
  await expect(cards).toHaveCount(4);
  for (const s of SECTORS) await expectArtwork(cards.locator(`[data-sector="${s.art}"]`), s.file);
  await snap(page, 'dashboard-sector-cards-light-en', page.locator('section[aria-labelledby="domains-heading"]'));
  for (const s of SECTORS) {
    const card = page.locator(`[data-testid="home-sector"][data-section="${s.section}"]`);
    const art = card.getByTestId('sector-art');
    await expect(art).toHaveAttribute('data-sector', s.art);
    await expectArtwork(art, s.file);
    await expect(art.locator('img')).toHaveAttribute('loading', 'lazy'); // below the hero
    await card.click();
    await expect(page).toHaveURL(s.path);
    // The sector page shows the same artwork at the top, loaded at once.
    const banner = page.getByTestId('sector-page').getByTestId('sector-art');
    await expect(banner).toHaveAttribute('data-sector', s.art);
    await expect(banner.locator('img')).toHaveAttribute('loading', 'eager');
    await expectArtwork(banner, s.file);
    if (s.section === 'electricity') await snap(page, 'sector-page-electricity-light-en', page.getByTestId('sector-page').locator('header'));
    await page.goBack();
  }
  await noSidewaysScroll(page);
});

test('electricity is a credited photograph of Oman, not an illustration; its title and button stay', async ({ page }) => {
  await page.goto('/');
  const card = page.locator('[data-testid="home-sector"][data-section="electricity"]');
  const art = card.getByTestId('sector-art');
  await expect(art).toHaveAttribute('data-kind', 'photo');
  await expect(card).not.toContainText('Illustration');
  await expect(card.locator('img')).toHaveAttribute('alt', /^Electricity \(الكهرباء\)\. Photograph: .*pylons.*Oman/);
  // The name in both languages over the photograph, as on the other three artworks.
  await expect(art.getByTestId('sector-art-title')).toContainText('الكهرباء');
  await expect(art.getByTestId('sector-art-title')).toContainText('Electricity');
  await expect(art.getByTestId('sector-art-credit')).toHaveText('Photo: kaartcam · CC BY-SA 4.0');
  await expect(card).toContainText('Explore Electricity');
  await expect(card).toHaveAccessibleName(/^Electricity .*Photograph.*kaartcam.*Explore Electricity/);
  // The full credit: creator, licence and file links, and what was changed.
  await page.goto('/sources#image-credits');
  const entry = page.getByTestId('image-credits').locator('li').filter({ hasText: 'kaartcam' });
  await expect(entry).toHaveCount(1);
  await expect(entry.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/');
  await expect(entry.getByRole('link', { name: 'Wikimedia Commons' }))
    .toHaveAttribute('href', 'https://commons.wikimedia.org/wiki/File:Electricity_pylons_in_Oman.png');
  await expect(entry.getByTestId('image-changes')).toContainText('Cropped to 16:9');
  await expect(entry.getByTestId('image-changes')).toContainText('same licence, CC BY-SA 4.0');
  // The Overview card uses the same photograph with its full caption, and no "Illustration" label.
  await page.goto('/overview');
  const overview = page.locator('[data-testid="overview-sector"][data-sector="electricity"]');
  await expect(overview.getByTestId('photo')).toHaveAttribute('data-kind', 'photo');
  await expect(overview.getByTestId('photo-credit')).toContainText('kaartcam · CC BY-SA 4.0 · Wikimedia Commons');
  await expect(overview).not.toContainText('Illustration');
});

test('a card opens with the keyboard and is named for screen readers', async ({ page }) => {
  await page.goto('/');
  const card = page.locator('[data-testid="home-sector"][data-section="water"]');
  await expect(card).toHaveAccessibleName(/Water.*dam/);
  await card.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/energy\/water/);
});

test('Arabic and the dark theme: Arabic names, the same images, nothing distorted', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('osrip.language', 'ar');
    localStorage.setItem('osrip.theme', 'dark');
  });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const trade = page.locator('[data-testid="home-sector"][data-section="trade"]');
  await expect(trade.locator('img')).toHaveAttribute('alt', /^التجارة/);
  const electricity = page.locator('[data-testid="home-sector"][data-section="electricity"]');
  await expect(electricity.locator('img')).toHaveAttribute('alt', /^الكهرباء \(Electricity\)\. صورة فوتوغرافية/);
  await expect(electricity.getByTestId('sector-art-credit')).toHaveText('تصوير: kaartcam · CC BY-SA 4.0');
  await expect(electricity).not.toContainText('رسم توضيحي');
  await expect(trade).toContainText('استكشف');
  for (const s of SECTORS) {
    await expectArtwork(page.locator(`[data-testid="home-sector"][data-section="${s.section}"]`).getByTestId('sector-art'), s.file);
  }
  await snap(page, 'dashboard-sector-cards-dark-ar', page.locator('section[aria-labelledby="domains-heading"]'));
  await noSidewaysScroll(page);
  await trade.click();
  await expect(page).toHaveURL(/\/trade/);
  await expectArtwork(page.getByTestId('sector-page').getByTestId('sector-art'), 'sectors/osrip_trade');
  await snap(page, 'sector-page-trade-dark-ar', page.getByTestId('sector-page').locator('header'));
});

test('phone width: one card per row, whole images, the sector page shows its artwork @mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const cards = page.getByTestId('home-sector');
  await expect(cards).toHaveCount(4);
  const [a, b] = [await cards.nth(0).boundingBox(), await cards.nth(1).boundingBox()];
  expect(b!.y).toBeGreaterThan(a!.y + a!.height - 1); // stacked
  await expectArtwork(cards.nth(3).getByTestId('sector-art'), 'sectors/osrip_trade');
  await expectArtwork(cards.nth(0).getByTestId('sector-art'), 'photos/electricity-pylons-oman');
  // The short credit stays on one line inside the photograph.
  const credit = cards.nth(0).getByTestId('sector-art-credit');
  const [box, frame] = [await credit.boundingBox(), await cards.nth(0).getByTestId('sector-art').boundingBox()];
  expect(box!.height).toBeLessThan(20);
  expect(box!.x + box!.width).toBeLessThanOrEqual(frame!.x + frame!.width);
  await noSidewaysScroll(page);
  await snap(page, 'dashboard-sector-cards-phone', cards.nth(0));
  await cards.nth(2).click();
  await expect(page).toHaveURL(/\/food-security/);
  await expectArtwork(page.getByTestId('sector-page').getByTestId('sector-art'), 'sectors/osrip_food_security');
  await snap(page, 'sector-page-food-phone');
  await noSidewaysScroll(page);
});
