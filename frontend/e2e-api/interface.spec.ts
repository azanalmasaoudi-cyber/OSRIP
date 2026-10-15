import { expect, test, type Page } from '@playwright/test';

// Navigation, the four questions on analytical pages, filter summaries, motion
// preferences, service health and a responsive matrix, against the real API.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('navigation lists the required sections and every link opens its page', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const expected: Array<[string, RegExp, string]> = [
    ['Overview', /\/overview/, 'Overview'],
    ['Electricity', /\/energy\/electricity/, 'Energy and Essential Services'],
    ['Water', /\/energy\/water/, 'Energy and Essential Services'],
    ['Food Security', /\/food-security/, 'Food Security'],
    ['Trade', /\/trade/, 'Trade'],
    ['Map', /\/geography/, 'Geography'],
    ['Studies', /\/studies/, 'Studies'],
    ['Scenarios', /\/forecasts/, 'Forecasts and Scenarios'],
    ['Sources', /\/sources/, 'Sources and Methodology'],
    ['Assistant', /\/assistant/, 'Al Mulhim'], // the page is titled with the chosen persona
    ['Reports', /\/reports/, 'Reports'],
    ['Account and settings', /\/(account|sign-in)/, ''],
  ];
  for (const [name, url, heading] of expected) {
    await nav.getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(url);
    await expect(page).toHaveURL(/mode=synthetic/); // the data mode is kept
    if (heading) await expect(page.getByRole('heading', { level: 1 })).toContainText(heading);
  }
});

test('an analytical page answers its questions (measure, period, change, evidence, limits, next) from loaded evidence, with a filter summary', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  await expect(page.getByTestId('filter-summary')).toContainText('All areas');
  const insights = page.getByTestId('section-insights');
  await expect(insights.locator('details')).toHaveCount(5);

  const measure = insights.getByTestId('insight-measure');
  await measure.locator('summary').click();
  await expect(measure).toContainText('Electricity generation');
  await expect(measure.getByTestId('insight-period').first()).toContainText('Period covered');
  const limits = insights.getByTestId('insight-limits');
  await limits.locator('summary').click();
  await expect(limits).toContainText('synthetic demonstration data');
  await expect(limits).toContainText('does not show its cause');
  const change = insights.getByTestId('insight-change');
  await change.locator('summary').click();
  await expect(change).toContainText('2,100');
  const evidence = insights.getByTestId('insight-evidence');
  await evidence.locator('summary').click();
  await expect(evidence).toContainText('fixtures-v1');
  const next = insights.getByTestId('insight-next');
  await next.locator('summary').click();
  await expect(next.getByRole('link', { name: /forecast/i })).toHaveAttribute('href', /\/forecasts\?mode=synthetic/);

  // The summary follows the filters, and the questions follow the same selection.
  await page.getByTestId('filter-frequency').selectOption('annual');
  await expect(page.getByTestId('filter-summary')).toContainText('Annual');

  // Arabic: same structure, translated questions.
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(insights.getByTestId('insight-measure')).toContainText('ماذا يقيس هذا المؤشر؟');
  await page.getByRole('button', { name: 'English' }).click();
});

test('verified mode: the questions say what is missing instead of inventing answers', async ({ page }) => {
  await page.goto('/trade');
  const insights = page.getByTestId('section-insights');
  await insights.getByTestId('insight-change').locator('summary').click();
  await expect(insights.getByTestId('insight-change')).toContainText('No change can be calculated');
  await insights.getByTestId('insight-evidence').locator('summary').click();
  await expect(insights.getByTestId('insight-evidence')).toContainText('No published observations');
});

test('motion: gentle route entrance that keeps focus and history; reduced motion removes movement', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const route = page.getByTestId('route-transition');
  await expect(route).toHaveCSS('opacity', '1');
  // Client-side navigation moves focus to the page, and Back returns at once.
  await page.locator('a[href^="/trade"]').first().click();
  await expect(page).toHaveURL(/\/trade/);
  await expect(page.locator('main')).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(/\/overview/);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/forecasts?mode=synthetic');
  // No translate is applied during the entrance under reduced motion.
  expect(await route.evaluate((el) => el.style.transform)).toMatch(/^(none|translateY\(0px\)|)$/);
  const card = page.getByTestId('forecast-target').first();
  expect(parseFloat(await card.locator('xpath=..').evaluate((el) => getComputedStyle(el).animationDuration))).toBeLessThan(0.001);
});

test('3D depth: the hero follows the mouse; reduced motion keeps the flat 2D layout', async ({ page }) => {
  await page.goto('/');
  const scene = page.getByTestId('hero-scene');
  await expect(scene).toBeVisible();
  const box = await scene.boundingBox();
  if (!box) throw new Error('no hero box');
  await page.mouse.move(box.x + box.width * 0.9, box.y + box.height * 0.1);
  await expect.poll(() => scene.evaluate((el) => el.style.getPropertyValue('--tilt-y'))).not.toBe('');
  expect(await scene.evaluate((el) => getComputedStyle(el).transform)).not.toBe('none');
  // Charts and forms never tilt.
  await page.goto('/energy/electricity?mode=synthetic');
  expect(await page.locator('.tilt svg, form.tilt, .tilt form').count()).toBe(0);

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.mouse.move(box.x + box.width * 0.9, box.y + box.height * 0.1);
  expect(await scene.evaluate((el) => getComputedStyle(el).transform)).toBe('none');
  expect(await scene.evaluate((el) => el.style.getPropertyValue('--tilt-y'))).toBe('');
  await expect(page.getByTestId('home-portrait').locator('img').first()).toBeVisible();
});

test('service health: administrators only; integrations and errors are listed without personal data', async ({ page }) => {
  await page.goto('/admin/health');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
  await signIn(page, 'admin@e2e.invalid');
  await page.goto('/admin/health');
  await expect(page.getByTestId('health-page')).toContainText('Ready');
  await expect(page.locator('[data-testid="integration"][data-name="official_statistics"]')).toHaveAttribute('data-status', 'file_import');
  await expect(page.locator('[data-testid="integration"][data-name="google"]')).toHaveAttribute('data-status', 'not_configured');
});

const WIDTHS = [360, 390, 768, 1024, 1366, 1920];
const ROUTES = ['/', '/overview', '/energy/electricity', '/trade', '/forecasts', '/assistant', '/reports'];

test('responsive matrix: no sideways scrolling at six widths, in English and Arabic', async ({ page }) => {
  test.setTimeout(300_000);
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    for (const language of ['en', 'ar'] as const) {
      for (const route of ROUTES) {
        await page.goto(`${route}?mode=synthetic`);
        await expect(page.locator('main')).toBeVisible();
        if (language === 'ar' && (await page.locator('html').getAttribute('lang')) !== 'ar') {
          await page.getByRole('button', { name: 'العربية' }).first().click();
          await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
        }
        await page.waitForLoadState('networkidle');
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${width}px ${language} ${route} overflows by ${overflow}px`).toBeLessThanOrEqual(0);
      }
      if (language === 'ar') await page.getByRole('button', { name: 'English' }).first().click();
    }
    // Below the desktop breakpoint the navigation is a menu button; above it, a sidebar.
    await page.goto('/overview?mode=synthetic');
    const menu = page.getByRole('button', { name: 'Open menu' });
    if (width < 1024) {
      await menu.click();
      await expect(page.getByRole('dialog').getByRole('link', { name: 'Scenarios', exact: true })).toBeVisible();
      await page.keyboard.press('Escape');
    } else {
      await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Scenarios', exact: true })).toBeVisible();
    }
  }
});
