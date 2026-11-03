import { expect, test, type Page } from '@playwright/test';

// The sign-in screen in the owner's welcome design, through the real stack: a username and a
// password only; the real login, sessions and roles; "Back to introduction". Accounts are
// throwaway test accounts (the run's own random password, never stored).

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}-${test.info().project.name}.png`, fullPage: true });
}

function uniqueName(): string {
  return `wl${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`.slice(0, 32);
}

test('only a username and a password; Show reveals the password; Remember me is off', async ({ page }) => {
  await page.goto('/sign-in');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome back');
  await expect(page.getByTestId('sign-in-showcase')).toContainText('Data provides the picture.');
  const form = page.getByTestId('sign-in-form');
  // The only fields to type in: username and password (no e-mail, phone or code).
  await expect(form.locator('input:not([type="checkbox"])')).toHaveCount(2);
  await expect(form.getByLabel('Username')).toHaveAttribute('autocomplete', 'username');
  const password = form.getByLabel('Password');
  await expect(password).toHaveAttribute('type', 'password');
  await form.getByTestId('sign-in-reveal').click();
  await expect(password).toHaveAttribute('type', 'text');
  await expect(form.getByTestId('sign-in-reveal')).toHaveAttribute('aria-pressed', 'true');
  await form.getByTestId('sign-in-reveal').click();
  await expect(password).toHaveAttribute('type', 'password');
  await expect(form.getByTestId('sign-in-remember')).not.toBeChecked();
  await expect(page.getByTestId('sign-in-only-username')).toHaveText('Only a username and password — no phone number or email required.');
  await expect(form.getByRole('button', { name: 'Sign in' })).toBeDisabled(); // nothing typed yet
  await snap(page, 'sign-in-light-en');
});

test('a new account signs in with its username and password; a wrong password is refused', async ({ page }) => {
  const username = uniqueName();
  // Registration needs only a username and a password too (recovery code shown once).
  await page.goto('/register');
  const register = page.getByTestId('register-form');
  await register.getByTestId('register-username').fill(username);
  await register.getByTestId('register-password').fill(PASSWORD);
  await register.getByTestId('register-confirm').fill(PASSWORD);
  await register.getByTestId('register-submit').click();
  await expect(page.getByTestId('register-done')).toBeVisible();
  await page.getByTestId('recovery-saved').check();
  await page.getByTestId('recovery-continue').click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  await page.context().clearCookies(); // signed out: the session lives in the cookies

  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username').fill(username);
  await form.getByLabel('Password').fill(`${PASSWORD}-wrong`);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText(/username or password/i);
  await expect(page.getByTestId('signed-in-as')).toHaveCount(0);

  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/account/);
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  // An ordinary account: no administration.
  await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Users and Roles' })).toHaveCount(0);
});

test('the administrator signs in on the same screen and keeps administration', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username').fill('admin@e2e.invalid');
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Users and Roles' })).toBeVisible();
  // The API still enforces it: an ordinary visitor is refused the same request.
  const other = await page.context().browser()!.newContext({ baseURL: test.info().project.use.baseURL });
  const refused = await other.request.get('/api/v1/admin/users');
  expect([401, 403]).toContain(refused.status());
  await other.close();
});

test('Back to introduction opens the welcome on the home page, once', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-back').click();
  await expect(page).toHaveURL(/\/(\?.*)?$/);
  await expect(page.getByTestId('entrance')).toBeVisible();
  await page.getByTestId('entrance-skip').click();
  await expect(page.getByTestId('entrance')).toBeHidden();
  await page.reload();
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

  test('right to left, with the form at the left and the showcase at the right', async ({ page }) => {
    await page.goto('/sign-in');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('مرحبًا بعودتك');
    await expect(page.getByTestId('sign-in-form').getByLabel('اسم المستخدم')).toBeVisible();
    await expect(page.getByTestId('sign-in-form').getByRole('button', { name: 'تسجيل الدخول' })).toBeVisible();
    const card = await page.getByTestId('sign-in-card').boundingBox();
    const showcase = await page.getByTestId('sign-in-showcase').boundingBox();
    expect(showcase!.x).toBeGreaterThan(card!.x);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await snap(page, 'sign-in-dark-ar');
  });

  test('@mobile on a phone: the showcase above the form, nothing sideways', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/sign-in');
    const card = await page.getByTestId('sign-in-card').boundingBox();
    const showcase = await page.getByTestId('sign-in-showcase').boundingBox();
    expect(card!.y).toBeGreaterThan(showcase!.y);
    expect(card!.x).toBeGreaterThanOrEqual(0);
    expect(card!.x + card!.width).toBeLessThanOrEqual(390.5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await snap(page, 'sign-in-phone-ar');
  });
});
