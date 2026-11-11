import { expect, test, type Page } from '@playwright/test';

// Account journeys through the real stack. Sign-in is a username and a password only; ordinary
// registration asks for a username (1-10 Arabic or English letters and digits), a password and
// the password again, and shows a recovery code once. E-mail, e-mail link, phone, Google and
// Microsoft sign-in are retired: old links land on the sign-in page, the API refuses them, and an
// e-mail address typed as a username signs nothing in. Older accounts keep working: a username
// longer than 10 characters still signs in, and an account without a username gets one from an
// administrator.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const NEW_PASSWORD = `new-${PASSWORD}`;

/** A unique username of at most 10 characters. */
function uniqueName(prefix = 'user'): string {
  return `${prefix.slice(0, 4)}${Math.random().toString(36).slice(2, 8)}`;
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

/** Records API answers of 502, 503 or 504 (a gateway with no API behind it). */
function watchGateway(page: Page): string[] {
  const seen: string[] = [];
  page.on('response', (r) => { if (r.url().includes('/api/') && [502, 503, 504].includes(r.status())) seen.push(`${r.status()} ${r.url()}`); });
  return seen;
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
    await form.getByLabel('Username').fill('e2eviewer');
    await form.getByLabel('Password').fill(PASSWORD);
    await form.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByTestId('signed-in-as')).toBeVisible();
    await page.goto('/');
    await expect(page.getByTestId('home-page')).toBeVisible();
    await expect(page.getByTestId('entrance')).toBeHidden();
  });
});

test('registration needs only a username and a password; the recovery code is shown once', async ({ page }) => {
  const gateway = watchGateway(page);
  await page.goto('/register');
  const form = page.getByTestId('register-form');
  // Username, password and the password again: nothing else.
  await expect(form.locator('input:not([type="checkbox"])')).toHaveCount(3);
  await expect(form.locator('input[type="email"], input[type="tel"]')).toHaveCount(0);
  await expect(form.getByTestId('register-username')).toHaveAttribute('maxlength', '10');
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
  expect(gateway).toEqual([]);
});

test('ten characters at most: the field stops there and says so; the server agrees', async ({ page }) => {
  await page.goto('/register');
  const field = page.getByTestId('register-username');
  await field.pressSequentially('abcdefghijk'); // eleven letters typed
  await expect(field).toHaveValue('abcdefghij');
  await expect(page.getByTestId('register-username-problem')).toHaveText('Username must not exceed 10 characters.');
  // The API refuses an eleventh character whatever the page does.
  const r = await page.request.post('/api/v1/auth/register/username', {
    data: { username: 'abcdefghijk', password: PASSWORD, password_confirm: PASSWORD },
  });
  expect(r.status()).toBe(422);
  expect((await r.json()).error.code).toBe('username_too_long');
  // Exactly ten is fine.
  const ten = uniqueName('Ten').padEnd(10, 'x');
  expect(ten).toHaveLength(10);
  await registerUsername(page, ten);
  await expect(page.getByTestId('recovery-code')).toBeVisible();
});

test('an Arabic username registers and signs in; a look-alike spelling is the same name', async ({ page, browser }) => {
  const tag = Array.from({ length: 3 }, () => 'بتثجحخدذرزسشصض'[Math.floor(Math.random() * 14)]).join('');
  const username = `أحمد${tag}`;
  await registerUsername(page, username);
  await page.getByTestId('recovery-saved').check();
  await page.getByTestId('recovery-continue').click();
  await expect(page.getByTestId('account-username')).toHaveText(username);

  const other = await (await browser.newContext()).newPage();
  await other.goto('/register');
  const form = other.getByTestId('register-form');
  await form.getByTestId('register-username').fill(`احمد${tag}`); // alef without hamza
  await form.getByTestId('register-password').fill(PASSWORD);
  await form.getByTestId('register-confirm').fill(PASSWORD);
  await form.getByTestId('register-submit').click();
  await expect(form.getByRole('alert')).toHaveText('This username is already used. Choose another.');
  await signIn(other, username);
  await expect(other.getByTestId('account-page')).toBeVisible();
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

test('signing in survives a reload; signing out ends it', async ({ page }) => {
  await signIn(page, 'e2eviewer');
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  await page.getByTestId('signed-in-as').click();
  await page.getByTestId('sign-out').click();
  await expect(page.getByTestId('signed-in-as')).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId('signed-in-as')).toHaveCount(0);
  expect((await (await page.request.get('/api/v1/auth/me')).json()).authenticated).toBe(false);
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
  await signIn(admin, 'e2eadmin');
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

test('retired methods: old links land on sign-in, an e-mail address signs nothing in, the API refuses them', async ({ page }) => {
  for (const path of ['/sign-in/other', '/magic-link?token=abcdefghijklmnopqrstuvwxyz', '/verify-email?token=x', '/reset-password?token=x', '/link-email?token=x', '/forgot-password/email', '/dev/mail']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/sign-in$/); // tokens in old links are dropped
  }
  // The seeded viewer kept its old address as a record: typed as a username it finds nothing.
  await signIn(page, 'viewer@e2e.invalid');
  await expect(page.getByTestId('sign-in-form').getByRole('alert')).toHaveText('The username or password is not correct.');
  for (const [path, data] of [
    ['/api/v1/auth/magic-link', { email: 'viewer@e2e.invalid' }],
    ['/api/v1/auth/phone/request', { country_code: '+968', number: '90000001' }],
    ['/api/v1/auth/register', { email: 'new@e2e.invalid', display_name: 'N', password: PASSWORD }],
    ['/api/v1/auth/password/forgot', { email: 'viewer@e2e.invalid' }],
  ] as const) {
    const r = await page.request.post(path, { data });
    expect(r.status(), path).toBe(410);
  }
  expect((await page.request.get('/api/v1/auth/oidc/google/start')).status()).toBe(410);
  expect((await (await page.request.get('/api/v1/auth/me')).json()).authenticated).toBe(false);
});

test('the sign-in page offers a username and a password and nothing else', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await expect(form.locator('input:not([type="checkbox"])')).toHaveCount(2); // username and password only
  await expect(form.getByTestId('sign-in-remember')).not.toBeChecked(); // remember me is opt-in
  await expect(page.getByTestId('sign-in-card')).not.toContainText(/e-mail|email|phone|Google|Microsoft|SMS|WhatsApp/i);
  await expect(page.getByRole('link', { name: 'Create an account' })).toBeVisible();
});

test('an older account keeps its longer username and signs in with it', async ({ page }) => {
  await signIn(page, 'E2ELEGACY.USER'); // 14 characters, from before the 10-character rule; any case
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-username')).toHaveText('e2elegacy.user');
});

test('an account without a username gets one from an administrator, then signs in with it', async ({ page, browser }) => {
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, 'e2eadmin');
  await expect(admin.getByTestId('account-page')).toBeVisible();
  await admin.goto('/admin/users');
  const row = admin.locator('[data-testid="admin-users"] tr').filter({ hasText: 'E2E e-mail account' });
  await expect(row).toContainText('legacy-email@e2e.invalid'); // the record, shown for the administrator
  const given = uniqueName('Given');
  await row.getByTestId('assign-username-input').fill(given);
  await row.getByTestId('assign-username-save').click();
  const named = admin.locator(`[data-testid="admin-users"] tr[data-username="${given}"]`);
  await expect(named).toBeVisible();
  // The account's own password still works, now with its username.
  await signIn(page, given);
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-username')).toHaveText(given);
});

test('an administrator grants a role explicitly; the user gains it on the next request', async ({ page, browser }) => {
  const username = uniqueName('grant');
  await registerUsername(page, username);
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, 'e2eadmin');
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
  await expect(page.getByTestId('sign-in-identifier')).toHaveAttribute('dir', 'auto'); // Arabic or English names
  await expect(page.getByText('اسم المستخدم', { exact: true })).toBeVisible();
  await page.goto('/register');
  await page.getByTestId('register-username').pressSequentially('سالمسالمسالم'); // twelve letters typed
  await expect(page.getByTestId('register-username')).toHaveValue('سالمسالمسا');
  await expect(page.getByTestId('register-username-problem')).toHaveText('اسم المستخدم يجب ألا يتجاوز 10 أحرف.');
  await page.getByTestId('register-password').fill(PASSWORD);
  await page.getByTestId('register-confirm').fill(`${PASSWORD}x`);
  await expect(page.getByTestId('register-mismatch')).toHaveText('كلمتا المرور غير متطابقتين.');
  await page.getByRole('button', { name: 'English' }).first().click();
});
