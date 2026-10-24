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

test('verified mode is the default and a sector shows nothing before a period is chosen', async ({ page }) => {
  await page.goto('/energy/electricity');
  await expect(page.getByTestId('data-mode-banner')).toHaveAttribute('data-mode', 'verified_source');
  // The offline prototype has no API: the sector says so and shows no figures and no chart.
  await expect(page.locator('[data-state="not_implemented"]')).toContainText('needs the OSRIP API');
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
  await expect(page.locator('svg[role="img"]')).toHaveCount(0);
  await expect(page.getByTestId('sector-nav').getByRole('link')).toHaveCount(4);
});

test('synthetic mode labels every indicator card in the analysis workspace', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic');
  const card = page.getByTestId('indicator-card').first();
  // .first(): the closed source-details dialog also holds a badge.
  await expect(card.getByTestId('data-mode-badge').first()).toHaveText('Synthetic demonstration data');
  // Reference data shown by the page itself is never drawn unasked.
  await expect(page.getByTestId('dataset-chart')).toHaveCount(0);
  const show = page.getByTestId('dataset-show-chart').first();
  if (await show.count()) {
    await show.click();
    await expect(page.getByTestId('dataset-chart').first()).toBeVisible();
    await page.getByTestId('dataset-hide-chart').first().click();
    await expect(page.getByTestId('dataset-chart')).toHaveCount(0);
  }
});

test('T08: switching to Arabic keeps mode, route and numbers; sets RTL', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic&section=water');
  const card = page.getByTestId('indicator-card').filter({ hasText: 'Water consumption' });
  await expect(card.getByTestId('indicator-value')).toHaveText('343');

  await page.getByRole('button', { name: 'العربية' }).click();

  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  await expect(page).toHaveURL(/\/workspace\?mode=synthetic&section=water$/);
  await expect(page.getByTestId('indicator-card').filter({ hasText: 'استهلاك المياه' }).getByTestId('indicator-value')).toHaveText('343');
  await expect(page.getByTestId('data-mode-banner')).toHaveAttribute('data-mode', 'synthetic');
});

test('T08: switching language preserves page filters and the filtered values', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic');
  await page.getByTestId('filter-domain').selectOption('trade');
  await expect(page).toHaveURL(/domain=trade/);
  const first = page.getByTestId('indicator-card').first();
  await expect(first).toHaveAttribute('data-indicator', /^TRADE_/);
  const indicator = await first.getAttribute('data-indicator');

  await page.getByRole('button', { name: 'العربية' }).click();

  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page).toHaveURL(/\/workspace\?mode=synthetic&domain=trade$/);
  await expect(page.getByTestId('filter-domain')).toHaveValue('trade');
  await expect(page.getByTestId('indicator-card').first()).toHaveAttribute('data-indicator', indicator ?? '');
});

test('the overview introduces the project with sector cards and draws no statistics', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  await expect(page.getByTestId('overview-intro')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('OSRIP: Oman Smart Resource Intelligence Platform');
  await expect(page.getByTestId('overview-status')).toContainText('not an official government service');
  await expect(page.getByTestId('overview-sector')).toHaveCount(4);
  await expect(page.getByTestId('overview-steps').locator('li')).toHaveCount(4);
  await expect(page.locator('svg[role="img"]')).toHaveCount(0);
  await expect(page.getByTestId('indicator-card')).toHaveCount(0);
  await page.getByTestId('overview-sector').filter({ hasText: 'Water' }).getByTestId('overview-sector-link').click();
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
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

test('the analysis workspace shows the four resources and indicator cards with provenance in synthetic mode', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic');
  const resources = page.getByTestId('resource-kpi');
  await expect(resources).toHaveCount(4);
  await expect(resources.nth(0)).toHaveAttribute('data-section', 'electricity');
  await expect(resources.nth(3)).toHaveAttribute('data-section', 'trade');
  await expect(page.getByTestId('indicator-card').first()).toBeVisible();
  await page.getByTestId('filter-domain').selectOption('trade');
  await expect(page).toHaveURL(/domain=trade/);
  await expect(page.getByTestId('indicator-card').first()).toHaveAttribute('data-indicator', /^TRADE_/);
  await expect(resources.nth(3).getByRole('button', { name: /Analyse/ })).toHaveAttribute('aria-pressed', 'true');
});

test('theme: Dark by default, Light and System from the top bar, remembered after a reload', async ({ page, isMobile }) => {
  test.skip(isMobile, 'the phone menu holds the theme choice');
  await page.goto('/overview?mode=synthetic');
  const html = page.locator('html');
  await expect(html).toHaveAttribute('data-theme', 'dark');
  const theme = page.getByTestId('theme-selector');
  await theme.getByRole('radio', { name: 'Light' }).click();
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(245, 245, 246)');
  await page.reload();
  await expect(html).toHaveAttribute('data-theme', 'light');
  // System follows the device: arrows move the choice.
  await theme.getByRole('radio', { name: 'Light' }).focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(theme.getByRole('radio', { name: 'System' })).toHaveAttribute('aria-checked', 'true');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(html).toHaveAttribute('data-theme', 'light');
});

test('search finds pages in either language and drafts a question for the assistant without sending it', async ({ page, isMobile }) => {
  test.skip(isMobile, 'the phone search opens in a dialog (see the @mobile test)');
  await page.goto('/overview?mode=synthetic');
  const input = page.getByRole('combobox', { name: 'Search OSRIP' });
  await page.keyboard.press('Control+k');
  await expect(input).toBeFocused();
  await input.fill('المياه'); // the Arabic name finds Water in the English interface
  await expect(page.getByTestId('search-result-page')).toHaveText(['Water']);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/energy\/water\?mode=synthetic$/);
  // The address changes before the new page renders and takes focus; type after that, as a reader would.
  await expect(page.locator('main#main')).toBeFocused();
  await input.fill('electricity growth since 2022');
  await expect(page.getByTestId('search-result-page')).toHaveCount(0); // no page has that name
  await page.keyboard.press('ArrowDown'); // the one option: ask the assistant
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/assistant\?mode=synthetic&q=electricity\+growth\+since\+2022$/);
});

test('@mobile the phone menu holds the theme and data mode; search opens in a dialog', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only');
  await page.goto('/overview?mode=synthetic');
  await page.getByTestId('open-menu').click();
  const menu = page.getByRole('dialog', { name: 'Menu' });
  await menu.getByTestId('theme-options').getByRole('radio', { name: 'Light' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(menu.getByTestId('data-mode-select')).toHaveValue('synthetic');
  await page.keyboard.press('Escape');
  await page.getByTestId('open-search').click();
  const search = page.getByRole('dialog', { name: 'Search OSRIP' });
  await search.getByRole('combobox').fill('trade');
  await search.getByTestId('search-result-page').first().click();
  await expect(page).toHaveURL(/\/trade\?mode=synthetic$/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('source details dialog opens, traps focus and closes with Escape', async ({ page }) => {
  await page.goto('/workspace?mode=synthetic&section=water');
  const trigger = page.getByTestId('indicator-card').filter({ hasText: 'Water consumption' }).getByTestId('source-details-button');
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
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Water');
  // The four sectors are one row of links that scrolls sideways, not the page.
  await expect(page.getByTestId('sector-nav').getByRole('link')).toHaveCount(4);
  const overflow = await page.evaluate<number>('document.documentElement.scrollWidth - window.innerWidth');
  expect(overflow).toBeLessThanOrEqual(0);
});

test('@mobile filters collapse behind a toggle and nothing scrolls sideways', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only');
  await page.goto('/workspace?mode=synthetic&domain=trade');
  const toggle = page.getByTestId('filters-toggle');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toContainText('1');
  await toggle.click();
  await expect(page.getByTestId('filter-domain')).toBeVisible();
  const overflow = await page.evaluate<number>('document.documentElement.scrollWidth - window.innerWidth');
  expect(overflow).toBeLessThanOrEqual(0);
});
