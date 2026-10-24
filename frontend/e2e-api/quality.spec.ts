import { expect, test, type Page } from '@playwright/test';

import { chooseSelection, openCalculations, showResults } from './sector';

// Interface quality checks against the real API: images, keyboard access and focus,
// failed requests, negative numbers and units in both languages, empty states, and
// long Arabic labels at the current viewport (run on the desktop and mobile projects).

const ROUTES = [
  '/', '/overview', '/workspace', '/energy/electricity', '/energy/water', '/food-security', '/trade',
  '/geography', '/reports', '/forecasts', '/assistant', '/sources', '/data-management', '/sign-in',
  '/register', '/register?method=phone', '/sign-in?method=phone', '/forgot-password', '/account', '/admin/users', '/admin/health', '/dev/mail',
];

async function toArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('lang')) === 'ar') return;
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
}

test('no page scrolls sideways, in English or Arabic', async ({ page }) => {
  test.setTimeout(360_000);
  for (const language of ['en', 'ar'] as const) {
    for (const route of ROUTES) {
      await page.goto(`${route}${route.includes('?') ? '&' : '?'}mode=synthetic`);
      await expect(page.locator('main')).toBeVisible();
      if (language === 'ar') await toArabic(page);
      await page.waitForLoadState('networkidle');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${language} ${route} overflows by ${overflow}px`).toBeLessThanOrEqual(0);
    }
  }
});

test('every image loads (landing page and credits)', async ({ page }) => {
  for (const route of ['/', '/sources']) {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    const broken = await page.evaluate(async () => {
      const images = [...document.images];
      for (const img of images) img.loading = 'eager';
      await Promise.all(images.map((img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = r; }))));
      return images.filter((img) => img.naturalWidth === 0).map((img) => img.currentSrc || img.src);
    });
    expect(broken, `broken images on ${route}`).toEqual([]);
  }
});

test('keyboard: skip link, visible focus on navigation, and a keyboard-only selection', async ({ page, isMobile }) => {
  await page.goto('/geography?mode=synthetic');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();

  if (!isMobile) {
    // Focus on a navigation link draws a visible indicator (outline or ring).
    const link = page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Trade' });
    await link.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(link).toBeFocused();
    const indicator = await link.evaluate((el) => {
      const s = getComputedStyle(el);
      return { outline: s.outlineStyle !== 'none' && s.outlineWidth !== '0px', ring: s.boxShadow !== 'none' };
    });
    expect(indicator.outline || indicator.ring).toBe(true);
  }

  // Select an area with the keyboard only; focus moves to the details.
  const button = page.locator('[data-testid="area-table"] tr[data-code="OM-ZU"] button');
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('selected-area')).toHaveAttribute('data-area', 'OM-ZU');
  await expect(page).toHaveURL(/area=OM-ZU/);
});

test('failed requests show an explained error with retry, and the rest of the page keeps working', async ({ page }) => {
  await page.route('**/api/v1/analysis/**', (route) =>
    route.fulfill({ status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'database_unavailable', message: 'The data store is not available.' } }) }));
  await page.goto('/energy/electricity?mode=synthetic');
  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  await openCalculations(page);
  const error = page.locator('[data-state="error"]').first();
  await expect(error).toBeVisible();
  await expect(error).toContainText('The data store is not available.');
  await expect(error.getByRole('button', { name: 'Try again' })).toBeVisible();
  // The table comes from another request and is still shown.
  await expect(page.getByTestId('series-row').first().locator('td').first()).toHaveText('48,000');

  // Without the list of published periods nothing can be chosen, and the page says why.
  await page.unroute('**/api/v1/analysis/**');
  await page.route('**/api/v1/series/availability**', (route) => route.abort('connectionrefused'));
  await page.goto('/energy/water?mode=synthetic');
  await expect(page.locator('[data-state="error"]').first()).toContainText('list of published periods could not be loaded');
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
});

test('negative values and units keep their sign and unit in English and Arabic', async ({ page }) => {
  await page.goto('/trade?mode=synthetic');
  await showResults(page, { indicator: 'TRADE_VALUE', breakdown: 'SYNTH_COMMODITY||import', view: 'annual', from: '2002-01-01', to: '2002-01-01' });
  await openCalculations(page);
  const balance = page.locator('[data-testid="calculation"][data-kind="trade_balance"] [data-testid="calc-value"]');
  await expect(balance).toHaveText(/^[−-]28,000,000 Omani rial \(nominal\)$/);
  await toArabic(page);
  const arabic = (await balance.textContent()) ?? '';
  expect(arabic).toMatch(/[−-]\s?28,000,000/);
  expect(arabic).toContain('ريال');
  // The number is laid out left-to-right so the minus sign stays in front of the digits.
  expect(await balance.evaluate((el) => getComputedStyle(el.querySelector('[dir="ltr"]') ?? el).direction)).toBe('ltr');

  await page.goto('/energy/electricity?mode=synthetic');
  await page.getByRole('button', { name: 'English' }).first().click();
  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  await openCalculations(page);
  await expect(page.locator('[data-testid="calculation"][data-kind="absolute_change"]').filter({ hasText: 'Electricity generation' })
    .getByTestId('calc-value')).toContainText('2,100 gigawatt-hour');
});

test('empty states are explained, never blank', async ({ page }) => {
  await page.goto('/trade');
  await expect(page.locator('[data-state="no_verified_data"]').first()).toBeVisible();
  await page.goto('/trade?mode=synthetic');
  await page.getByTestId('sector-show-results').click(); // no period chosen yet
  await expect(page.getByTestId('sector-error')).toContainText('Choose both a start period and an end period.');
  await chooseSelection(page, { indicator: 'TRADE_VALUE', breakdown: 'SYNTH_COMMODITY||import', view: 'annual', from: '2002-01-01', to: '2002-01-01' });
  await page.getByTestId('sector-show-results').click();
  await expect(page.getByTestId('sector-error')).toHaveCount(0);
  await page.goto('/geography');
  await expect(page.locator('[data-testid="area-table"] [data-coverage="none"]').first()).toContainText('No data');
});
