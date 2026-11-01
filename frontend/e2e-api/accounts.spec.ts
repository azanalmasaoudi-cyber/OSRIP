import { expect, test, type Page } from '@playwright/test';

// Account journeys through the real stack. Ordinary registration needs only a username and a
// password; the recovery code is shown once. Older accounts made with an e-mail address still
// sign in (the address goes in the username field) and keep their e-mail link and reset on
// "Other ways to sign in". E-mails go to the development outbox (never sent); the tests open
// the links from the /dev/mail page like a user would from an inbox. Google and Microsoft are
// not configured in this environment.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const NEW_PASSWORD = `new-${PASSWORD}`;

function unique(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.invalid`;
}

function uniqueName(prefix = 'user'): string {
  return `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`.slice(0, 32);
}

async function openMail(page: Page, to: string, purpose: string): Promise<void> {
  await page.goto('/dev/mail');
  const message = page.locator(`[data-testid="dev-mail"] li[data-to="${to}"][data-purpose="${purpose}"]`).first();
  await expect(message).toBeVisible();
  await message.getByRole('link').first().click();
}

/** An older-style account with an e-mail address (the API still accepts it; the screens do not offer it). */
async function registerByEmail(page: Page, email: string): Promise<void> {
  const r = await page.request.post('/api/v1/auth/register', {
    data: { email, display_name: 'E2E New User', password: PASSWORD },
  });
  expect(r.status()).toBe(202);
}

async function signIn(page: Page, username: string, password = PASSWORD): Promise<void> {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username').fill(username);
  await form.getByLabel('Password').fill(password);
  await form.getByRole('button', { name: 'Sign in' }).click();
}

/** Registration on the screen; returns the recovery code shown once. */
async function registerUsername(page: Page, username: string, password = PASSWORD): Promise<string> {
  await page.goto('/register');
  const form = page.getByTestId('register-form');
  await form.getByTestId('register-username').fill(username);
  await form.getByTestId('register-password').fill(password);
  await form.getByTestId('register-confirm').fill(password);
  await form.getByTestId('register-submit').click();
  await expect(page.getByTestId('register-done')).toBeVisible();
  return (await page.getByTestId('recovery-code').textContent()) ?? '';
}

test.describe('with the opening switched on', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('the opening never blocks signing in, and does not come back in the session', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('entrance')).toBeVisible();
    await page.getByTestId('entrance-skip').click();
    await expect(page.getByTestId('entrance')).toBeHidden();
    await expect(page).toHaveURL(/\/$/); // it ends where it started: no redirect
    await page.goto('/sign-in'); // a direct link: no opening
    await expect(page.getByTestId('entrance')).toBeHidden();
    const form = page.getByTestId('sign-in-form');
    await form.getByLabel('Username').fill('viewer@e2e.invalid');
    await form.getByLabel('Password').fill(PASSWORD);
    await form.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByTestId('signed-in-as')).toBeVisible();
    await page.goto('/');
    await expect(page.getByTestId('home-page')).toBeVisible();
    await expect(page.getByTestId('entrance')).toBeHidden();
  });
});

test('registration needs only a username and a password; the recovery code is shown once', async ({ page }) => {
  await page.goto('/register');
  const form = page.getByTestId('register-form');
  await expect(form.locator('input[type="email"], input[type="tel"]')).toHaveCount(0); // no e-mail, no phone
  const username = uniqueName('Salim');
  await form.getByTestId('register-username').fill('9bad name');
  await expect(page.getByTestId('register-username-problem')).toBeVisible();
  await form.getByTestId('register-username').fill(username);
  await form.getByTestId('register-password').fill(PASSWORD);
  await form.getByTestId('register-confirm').fill(`${PASSWORD}x`);
  await expect(page.getByTestId('register-mismatch')).toBeVisible();
  await expect(form.getByTestId('register-submit')).toBeDisabled();
  await form.getByTestId('register-confirm').fill(PASSWORD);
  await form.getByTestId('register-submit').click();

  const code = (await page.getByTestId('recovery-code').textContent()) ?? '';
  expect(code).toMatch(/^[A-Z2-9]{4}(-[A-Z2-9]{4}){4}$/);
  await expect(page.getByTestId('recovery-continue')).toBeDisabled(); // saved first
  await page.getByTestId('recovery-saved').check();
  await page.getByTestId('recovery-continue').click();
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-username')).toHaveText(username);
  await expect(page.getByTestId('account-roles')).toHaveText('Viewer');
  await expect(page.getByTestId('recovery-status')).toContainText('has a recovery code');
  await page.goto('/admin/users');
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
});

test('a username is taken whatever its case; a wrong password is refused', async ({ page, browser }) => {
  const username = uniqueName('Mona');
  await registerUsername(page, username);
  const other = await (await browser.newContext()).newPage();
  await other.goto('/register');
  const form = other.getByTestId('register-form');
  await form.getByTestId('register-username').fill(username.toUpperCase());
  await form.getByTestId('register-password').fill(PASSWORD);
  await form.getByTestId('register-confirm').fill(PASSWORD);
  await form.getByTestId('register-submit').click();
  await expect(form.getByRole('alert')).toHaveText('This username is already used. Choose another.');

  await signIn(other, username, `wrong-${PASSWORD}`);
  await expect(other.getByTestId('sign-in-form').getByRole('alert')).toHaveText('The username or password is not correct.');
  await signIn(other, username.toUpperCase());
  await expect(other.getByTestId('account-page')).toBeVisible();
});

test('forgot password: the recovery code sets a new one and is replaced', async ({ page, browser }) => {
  const username = uniqueName('Rashid');
  const code = await registerUsername(page, username);
  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto('/sign-in');
  await fresh.getByRole('link', { name: 'Forgot password?' }).click();
  const form = fresh.getByTestId('recover-form');
  await form.getByTestId('recover-username').fill(username);
  await form.getByTestId('recover-code').fill('AAAA-BBBB-CCCC-DDDD-EEEE');
  await form.getByTestId('recover-password').fill(NEW_PASSWORD);
  await form.getByTestId('recover-confirm').fill(NEW_PASSWORD);
  await form.getByTestId('recover-submit').click();
  await expect(form.getByRole('alert')).toHaveText('The username or recovery code is not correct.');
  await form.getByTestId('recover-code').fill(code.toLowerCase());
  await form.getByTestId('recover-submit').click();
  await expect(fresh.getByTestId('recover-done')).toContainText('Your password was changed');
  const next = (await fresh.getByTestId('recovery-code').textContent()) ?? '';
  expect(next).not.toBe(code);

  await page.reload(); // the first browser was signed out
  await expect(page.getByTestId('signed-in-as')).toHaveCount(0);
  await signIn(page, username, PASSWORD);
  await expect(page.getByTestId('sign-in-form').getByRole('alert')).toContainText('not correct');
  await signIn(page, username, NEW_PASSWORD);
  await expect(page.getByTestId('account-page')).toBeVisible();
});

test('a new recovery code from the account page needs the current password', async ({ page }) => {
  await registerUsername(page, uniqueName('Aisha'));
  await page.getByTestId('recovery-saved').check();
  await page.getByTestId('recovery-continue').click();
  const section = page.getByTestId('recovery-section');
  await section.getByTestId('recovery-current-password').fill(`wrong-${PASSWORD}`);
  await section.getByTestId('recovery-new').click();
  await expect(section.getByRole('alert')).toHaveText('The current password is not correct.');
  await section.getByTestId('recovery-current-password').fill(PASSWORD);
  await section.getByTestId('recovery-new').click();
  await expect(section.getByTestId('recovery-code')).toBeVisible();
});

test('an administrator resets a forgotten password to a temporary one', async ({ page, browser }) => {
  const username = uniqueName('Khalid');
  await registerUsername(page, username);
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, 'admin@e2e.invalid');
  await expect(admin.getByTestId('account-page')).toBeVisible();
  await admin.goto('/admin/users');
  const row = admin.locator(`[data-testid="admin-users"] tr[data-username="${username}"]`);
  await row.getByTestId('reset-password').click();
  await row.getByTestId('reset-password-confirm').click();
  const temporary = (await admin.getByTestId('temporary-password').textContent()) ?? '';
  expect(temporary).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);

  await signIn(page, username, temporary);
  await expect(page.getByRole('heading', { name: 'Choose a new password to continue' })).toBeVisible();
});

test('older e-mail accounts: confirm, then sign in with the address in the username field', async ({ page }) => {
  const email = unique('register');
  await registerByEmail(page, email);
  await signIn(page, email);
  await expect(page.getByTestId('sign-in-form').getByRole('alert')).toContainText('Confirm your e-mail address first');
  await expect(page.getByRole('button', { name: 'Send a new confirmation e-mail' })).toBeVisible();

  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('Your e-mail address is confirmed');
  await expect(page).toHaveURL(/\/verify-email$/); // the token was removed from the address bar
  await signIn(page, email);
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-roles')).toHaveText('Viewer');
});

test('a confirmation link works once', async ({ page }) => {
  const email = unique('once');
  await registerByEmail(page, email);
  await page.goto('/dev/mail');
  const href = await page.locator(`[data-testid="dev-mail"] li[data-to="${email}"][data-purpose="verify_email"] a`).first().getAttribute('href');
  await page.goto(href ?? '');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');
  await page.goto(href ?? '');
  await expect(page.getByTestId('verify-result').getByRole('alert')).toContainText('already been used');
});

test('older e-mail accounts: the reset link (from Other ways to sign in) sets a new password once', async ({ page }) => {
  const email = unique('reset');
  await registerByEmail(page, email);
  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');

  await page.goto('/sign-in');
  await page.getByTestId('sign-in-other').click();
  await page.getByRole('link', { name: 'Reset a password by e-mail' }).click();
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

  await signIn(page, email, NEW_PASSWORD);
  await expect(page.getByTestId('account-page')).toBeVisible();
});

test('older e-mail accounts: the e-mail link signs in once after pressing the button', async ({ page, browser }) => {
  const email = unique('magic');
  await registerByEmail(page, email);
  await openMail(page, email, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('confirmed');

  await page.goto('/sign-in/other');
  await page.getByTestId('magic-form').getByLabel('E-mail address').fill(email);
  await page.getByRole('button', { name: 'Send sign-in link' }).click();
  await expect(page.getByTestId('magic-form')).toContainText('a message is on its way');

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

test('the main sign-in has no e-mail or phone; unconfigured Google and Microsoft are labelled on the other page', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await expect(form.locator('input')).toHaveCount(2); // username and password only
  await expect(page.getByTestId('sign-in-method')).toHaveCount(0);
  await page.goto('/sign-in/other');
  await expect(page.getByTestId('oidc-google-unconfigured')).toHaveText('Google sign-in is not configured on this server.');
  await expect(page.getByTestId('oidc-microsoft-unconfigured')).toBeVisible();
  await expect(page.getByTestId('oidc-google')).toHaveCount(0);
  await page.goto('/sign-in?error=identity_in_use');
  await expect(page.getByTestId('oidc-error')).toContainText('already linked to another OSRIP account');
});

test('an administrator grants a role explicitly; the user gains it on the next request', async ({ page, browser }) => {
  const username = uniqueName('grant');
  await registerUsername(page, username);
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, 'admin@e2e.invalid');
  await expect(admin.getByTestId('account-page')).toBeVisible();
  await admin.goto('/admin/users');
  const row = admin.locator(`[data-testid="admin-users"] tr[data-username="${username}"]`);
  await expect(row.getByTestId('role-viewer')).toBeChecked();
  await expect(row.getByTestId('role-analyst')).not.toBeChecked();
  await row.getByTestId('role-analyst').check();
  await expect(row.getByTestId('role-analyst')).toBeChecked();

  await page.goto('/account');
  await expect(page.getByTestId('account-roles')).toContainText('Analyst');
});

test('Arabic: the sign-in and registration pages are right-to-left, with translated messages', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('sign-in-identifier')).toHaveAttribute('dir', 'ltr');
  await expect(page.getByText('اسم المستخدم', { exact: true })).toBeVisible();
  await page.goto('/register');
  await page.getByTestId('register-password').fill(PASSWORD);
  await page.getByTestId('register-confirm').fill(`${PASSWORD}x`);
  await expect(page.getByTestId('register-mismatch')).toHaveText('كلمتا المرور غير متطابقتين.');
  await page.goto('/sign-in/other');
  await expect(page.getByTestId('oidc-google-unconfigured')).toContainText('غير مُعدّ');
  await expect(page.getByRole('radio', { name: 'رابط بالبريد' })).toBeVisible();
  await page.getByRole('button', { name: 'English' }).first().click();
});
