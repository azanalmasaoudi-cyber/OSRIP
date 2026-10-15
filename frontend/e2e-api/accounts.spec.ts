import { expect, test, type Page } from '@playwright/test';

// Account journeys through the real stack. E-mails go to the development outbox
// (never sent); the tests open the links from the /dev/mail page like a user would
// from an inbox. Google and Microsoft are not configured in this environment.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const NEW_PASSWORD = `new-${PASSWORD}`;

function unique(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.invalid`;
}

async function openMail(page: Page, to: string, purpose: string): Promise<void> {
  await page.goto('/dev/mail');
  const message = page.locator(`[data-testid="dev-mail"] li[data-to="${to}"][data-purpose="${purpose}"]`).first();
  await expect(message).toBeVisible();
  await message.getByRole('link').first().click();
}

async function register(page: Page, email: string): Promise<void> {
  await page.goto('/register');
  const form = page.getByTestId('register-form');
  await form.getByLabel('Name').fill('E2E New User');
  await form.getByLabel('E-mail address').fill(email);
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Create an account' }).click();
  await expect(page.getByTestId('register-done')).toContainText('a message is on its way');
}

async function signIn(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('E-mail address').fill(email);
  await form.getByLabel('Password').fill(password);
  await form.getByRole('button', { name: 'Sign in' }).click();
}

test('register, confirm the e-mail, sign in with ordinary access only', async ({ page }) => {
  const email = unique('register');
  await register(page, email);

  // Unconfirmed: the right password is refused with an explanation and a resend option.
  await signIn(page, email);
  await expect(page.getByTestId('sign-in-form').getByRole('alert')).toContainText('Confirm your e-mail address first');
  await expect(page.getByRole('button', { name: 'Send a new confirmation e-mail' })).toBeVisible();

  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('Your e-mail address is confirmed');
  await expect(page).toHaveURL(/\/verify-email$/); // the token was removed from the address bar

  await signIn(page, email);
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-roles')).toHaveText('Viewer');
  await page.goto('/data-management');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
  await page.goto('/admin/users');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
});

test('a confirmation link works once', async ({ page }) => {
  const email = unique('once');
  await register(page, email);
  await page.goto('/dev/mail');
  const href = await page.locator(`[data-testid="dev-mail"] li[data-to="${email}"][data-purpose="verify_email"] a`).first().getAttribute('href');
  await page.goto(href ?? '');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');
  await page.goto(href ?? '');
  await expect(page.getByTestId('verify-result').getByRole('alert')).toContainText('already been used');
});

test('forgot password: reset link sets a new password once', async ({ page }) => {
  const email = unique('reset');
  await register(page, email);
  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');

  await page.goto('/forgot-password');
  await page.getByTestId('forgot-form').getByLabel('E-mail address').fill(email);
  await page.getByRole('button', { name: 'Send reset link' }).click();
  await expect(page.getByTestId('forgot-form')).toContainText('a message is on its way');

  await page.goto('/dev/mail');
  const href = await page.locator(`[data-testid="dev-mail"] li[data-to="${email}"][data-purpose="reset_password"] a`).first().getAttribute('href');
  await page.goto(href ?? '');
  await page.getByTestId('reset-form').getByLabel('New password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Set password' }).click();
  await expect(page.getByTestId('reset-done')).toContainText('Your password has been changed');

  await page.goto(href ?? '');
  await page.getByTestId('reset-form').getByLabel('New password').fill(`${NEW_PASSWORD}x`);
  await page.getByRole('button', { name: 'Set password' }).click();
  await expect(page.getByTestId('reset-form').getByRole('alert')).toContainText('already been used');

  await signIn(page, email, PASSWORD);
  await expect(page.getByTestId('sign-in-form').getByRole('alert')).toContainText('not correct');
  await signIn(page, email, NEW_PASSWORD);
  await expect(page.getByTestId('account-page')).toBeVisible();
});

test('magic link signs in once after pressing the button', async ({ page, browser }) => {
  const email = unique('magic');
  await register(page, email);
  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');

  await page.goto('/sign-in');
  await page.getByRole('radio', { name: 'E-mail link' }).click();
  await page.getByTestId('sign-in-form').getByLabel('E-mail address').fill(email);
  await page.getByRole('button', { name: 'Send sign-in link' }).click();
  await expect(page.getByTestId('sign-in-form')).toContainText('a message is on its way');

  await page.goto('/dev/mail');
  const href = await page.locator(`[data-testid="dev-mail"] li[data-to="${email}"][data-purpose="magic_link"] a`).first().getAttribute('href');
  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto(href ?? '');
  await expect(fresh.getByTestId('signed-in-as')).toHaveCount(0); // opening the link alone does not sign in
  await fresh.getByTestId('magic-sign-in').click();
  await expect(fresh.getByTestId('account-page')).toBeVisible();
  await expect(fresh.getByTestId('signed-in-as')).toContainText('E2E New User');

  const again = await (await browser.newContext()).newPage();
  await again.goto(href ?? '');
  await again.getByTestId('magic-sign-in').click();
  await expect(again.getByRole('alert')).toContainText('already been used');
});

test('unconfigured Google and Microsoft are labelled, not offered', async ({ page }) => {
  await page.goto('/sign-in');
  await expect(page.getByTestId('oidc-google-unconfigured')).toHaveText('Google sign-in is not configured on this server.');
  await expect(page.getByTestId('oidc-microsoft-unconfigured')).toBeVisible();
  await expect(page.getByTestId('oidc-google')).toHaveCount(0);
  await page.goto('/sign-in?error=identity_in_use');
  await expect(page.getByTestId('oidc-error')).toContainText('already linked to another OSRIP account');
});

test('an administrator grants a role explicitly; the user gains it on the next request', async ({ page, browser }) => {
  const email = unique('grant');
  await register(page, email);
  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, 'admin@e2e.invalid');
  await expect(admin.getByTestId('account-page')).toBeVisible();
  await admin.goto('/admin/users');
  const row = admin.locator(`[data-testid="admin-users"] tr[data-email="${email}"]`);
  await expect(row.getByTestId('role-viewer')).toBeChecked();
  await expect(row.getByTestId('role-analyst')).not.toBeChecked();
  await row.getByTestId('role-analyst').check();
  await expect(row.getByTestId('role-analyst')).toBeChecked();

  await signIn(page, email);
  await expect(page.getByTestId('account-roles')).toContainText('Analyst');
});

test('Arabic sign-in page is right-to-left with the same controls', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('oidc-google-unconfigured')).toContainText('غير مُعدّ');
  await expect(page.getByRole('radio', { name: 'رابط بالبريد' })).toBeVisible();
  await page.getByRole('button', { name: 'English' }).first().click();
});
