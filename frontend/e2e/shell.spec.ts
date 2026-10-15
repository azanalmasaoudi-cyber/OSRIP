import { expect, test } from '@playwright/test';

// Runs against the mock adapter (synthetic booklet fixtures only).

test('landing page explains the project and credits every photograph', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('home-page')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByTestId('photo')).toHaveCount(5); // plus the hero background image
  const credits = page.getByTestId('photo-credit');
  await expect(credits).toHaveCount(6);
  for (const credit of await credits.all()) {
    await expect(credit).toContainText('Wikimedia Commons');
  }
});

test('verified mode is the default and never substitutes synthetic values', async ({ page }) => {
  await page.goto('/energy/electricity');
  await expect(page.getByTestId('data-mode-banner')).toHaveAttribute('data-mode', 'verified_source');
  await expect(page.locator('[data-state="no_verified_data"]')).toBeVisible();
  await expect(page.getByTestId('series-card')).toHaveCount(0);
});

test('synthetic mode labels every series card', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const card = page.getByTestId('series-card').first();
  // .first(): the closed source-details dialog also holds a badge.
  await expect(card.getByTestId('data-mode-badge').first()).toHaveText('Synthetic demonstration data');
  await expect(card.getByTestId('observation-value')).toHaveText(['48,000', '50,100']);
  await expect(card.getByTestId('column-chart')).toBeVisible();
});

test('T08: switching to Arabic keeps mode, route and numbers; sets RTL', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  const values = page.getByTestId('observation-value');
  await expect(values).toHaveText(['330', '343']);

  await page.getByRole('button', { name: 'العربية' }).click();

  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  await expect(values).toHaveText(['330', '343']);
  await expect(page.getByTestId('data-mode-banner')).toHaveAttribute('data-mode', 'synthetic');
});

test('T08: switching language preserves page filters and the filtered values', async ({ page }) => {
  await page.goto('/trade?mode=synthetic');
  await page.getByTestId('filter-flow').selectOption('import');
  await page.getByTestId('filter-partner').selectOption('total');
  await page.getByTestId('filter-display').selectOption('table');
  await expect(page).toHaveURL(/flow=import/);
  const values = page.getByTestId('observation-value');
  await expect(values).toHaveText(['80,000', '40,000,000']);

  await page.getByRole('button', { name: 'العربية' }).click();

  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page).toHaveURL(/\/trade\?mode=synthetic&flow=import&partner=total&view=table$/);
  await expect(page.getByTestId('filter-flow')).toHaveValue('import');
  await expect(page.getByTestId('filter-partner')).toHaveValue('total');
  await expect(values).toHaveText(['80,000', '40,000,000']);
});

test('a filter with no matches shows the empty state and can be reset', async ({ page }) => {
  await page.goto('/food-security?mode=synthetic&commodity=WHEAT');
  const empty = page.locator('[data-state="empty"]');
  await expect(empty).toBeVisible();
  await empty.getByRole('button', { name: 'Reset filters' }).click();
  await expect(page).toHaveURL(/\/food-security\?mode=synthetic$/);
  await expect(page.getByTestId('series-card').first()).toBeVisible();
});

test('navigation preserves the data mode but not page filters', async ({ page }) => {
  await page.goto('/trade?mode=synthetic&flow=import');
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Overview' }).click();
  await expect(page).toHaveURL(/\/overview\?mode=synthetic$/);
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Trade' }).click();
  await expect(page).toHaveURL(/\/trade\?mode=synthetic$/);
  await expect(page.getByTestId('commodity-registry')).toContainText('Synthetic demonstration commodity');
});

test('opening the energy domain keeps the data mode through the redirect', async ({ page }) => {
  await page.goto('/energy?mode=synthetic');
  await expect(page).toHaveURL(/\/energy\/electricity\?mode=synthetic$/);
});

test('overview shows indicator cards with provenance in synthetic mode', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  await expect(page.getByTestId('indicator-card').first()).toBeVisible();
  await page.getByTestId('filter-domain').selectOption('trade');
  await expect(page).toHaveURL(/domain=trade/);
  await expect(page.getByTestId('domain-card-trade')).toBeVisible();
  await expect(page.getByTestId('domain-card-food_security')).toHaveCount(0);
});

test('source details dialog opens, traps focus and closes with Escape', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  const trigger = page.getByTestId('source-details-button').first();
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Water consumption' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('source-details')).toContainText('None (synthetic data has no publisher)');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('keyboard: skip link moves focus to the main content', async ({ page }) => {
  await page.goto('/overview');
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to main content' });
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
});

test('data management is restricted to authorized users', async ({ page }) => {
  await page.goto('/data-management');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
});

test('old /methodology links redirect to Sources and Methodology', async ({ page }) => {
  await page.goto('/methodology?mode=synthetic');
  await expect(page).toHaveURL(/\/sources\?mode=synthetic$/);
  await expect(page.getByTestId('image-credits').locator('li')).toHaveCount(6);
});

test('@mobile menu opens as a drawer and navigates', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only');
  await page.goto('/?mode=synthetic');
  await page.getByTestId('open-menu').click();
  const menu = page.getByRole('dialog', { name: 'Menu' });
  await expect(menu).toBeVisible();
  await menu.getByRole('link', { name: 'Water' }).click();
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  await expect(page.getByTestId('observation-value')).toHaveText(['330', '343']);
});

test('@mobile filters collapse behind a toggle and nothing scrolls sideways', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only');
  await page.goto('/trade?mode=synthetic&flow=import');
  const toggle = page.getByTestId('filters-toggle');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toContainText('1');
  await toggle.click();
  await expect(page.getByTestId('filter-flow')).toBeVisible();
  const overflow = await page.evaluate<number>('document.documentElement.scrollWidth - window.innerWidth');
  expect(overflow).toBeLessThanOrEqual(0);
});
