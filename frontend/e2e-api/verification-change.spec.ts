import { expect, test, type Page } from '@playwright/test';

// Changing a confirmed e-mail address and a verified phone number through the real stack.
// E-mails go to the development outbox and SMS codes to the scripted test provider
// (serve_e2e.py); nothing is sent to a real inbox or phone.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

function unique(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.invalid`;
}

function omaniNumber(): string {
  return `9${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
}

async function openMail(page: Page, to: string, purpose: string): Promise<void> {
  await page.goto('/dev/mail');
  const message = page.locator(`[data-testid="dev-mail"] li[data-to="${to}"][data-purpose="${purpose}"]`).first();
  await expect(message).toBeVisible();
  await message.getByRole('link').first().click();
}

async function smsCode(page: Page, national: string): Promise<string> {
  let code: string | undefined;
  await expect.poll(async () => {
    const messages = (await (await page.request.get('/api/v1/dev/sms-outbox')).json()) as Array<{ to: string; code: string }>;
    code = messages.find((m) => m.to === `+968${national}`)?.code;
    return code;
  }).toBeTruthy();
  return code ?? '';
}

/** A new e-mail account, confirmed and signed in, on the account page. */
async function confirmedAccount(page: Page): Promise<string> {
  const address = unique('change');
  await page.goto('/register');
  const form = page.getByTestId('register-form');
  await form.getByLabel('Name').fill('E2E Change');
  await form.getByLabel('E-mail address').fill(address);
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Create an account' }).click();
  await expect(page.getByTestId('register-done')).toBeVisible();
  await openMail(page, address, 'verify_email');
  await expect(page.getByTestId('verify-result')).toContainText('Your e-mail address is confirmed');
  await page.goto('/sign-in');
  const signIn = page.getByTestId('sign-in-form');
  await signIn.getByLabel('E-mail address').fill(address);
  await signIn.getByLabel('Password').fill(PASSWORD);
  await signIn.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/account/);
  return address;
}

async function verifyNumber(page: Page, national: string): Promise<void> {
  await page.getByTestId('phone-number').fill(national);
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-sent')).toBeVisible();
  await page.getByTestId('phone-code').fill(await smsCode(page, national));
  await page.getByTestId('phone-verify').click();
}

test('a confirmed address changes only after the link to the new one is opened', async ({ page }) => {
  const old = await confirmedAccount(page);
  const change = page.getByTestId('change-email');
  await expect(change).toBeVisible();
  await expect(page.getByTestId('add-email')).toHaveCount(0);

  const next = unique('changed');
  await change.getByTestId('change-email-address').fill(next);
  await expect(change.getByTestId('change-email-submit')).toBeDisabled(); // the password comes first
  await change.getByTestId('change-email-password').fill(`wrong-${PASSWORD}`);
  await change.getByTestId('change-email-submit').click();
  await expect(change.getByRole('alert')).toHaveText('The current password is not correct.');

  await change.getByTestId('change-email-password').fill(PASSWORD);
  await change.getByTestId('change-email-submit').click();
  await expect(change).toContainText(`Check ${next}`);
  await page.reload();
  await expect(page.getByTestId('account-email')).toContainText(old); // nothing changes yet

  await openMail(page, next, 'change_email');
  await expect(page).toHaveURL(/\/link-email/);
  await page.getByTestId('link-email-confirm').click();
  await expect(page.getByTestId('link-email')).toContainText('Your e-mail address was changed');
  await page.goto('/account');
  await expect(page.getByTestId('account-email')).toContainText(next);
  await expect(page.getByTestId('account-email')).toContainText('Confirmed');

  // The previous address is told, with the new one masked.
  await page.goto('/dev/mail');
  const notice = page.locator(`[data-testid="dev-mail"] li[data-to="${old}"][data-purpose="email_changed"]`).first();
  await expect(notice).toContainText(`${next[0]}•••@e2e.invalid`);
  await expect(notice).not.toContainText(next);
});

test('a verified number is replaced only with the password and the new code', async ({ page }) => {
  await confirmedAccount(page);
  const first = omaniNumber();
  await page.getByTestId('add-phone-open').click();
  await verifyNumber(page, first);
  await expect(page.getByTestId('add-phone')).toContainText('Phone number verified');
  await page.reload();

  const change = page.getByTestId('change-phone');
  await change.getByTestId('change-phone-open').click();
  const second = omaniNumber();
  await change.getByTestId('phone-number').fill(second);
  await expect(change.getByTestId('phone-send')).toBeDisabled(); // the password comes first
  await change.getByTestId('phone-password').fill(PASSWORD);
  await verifyNumber(page, second);
  await expect(change).toContainText('Your phone number was changed.');
  await expect(page.getByTestId('account-phone')).toContainText(second.slice(-2));
});

test('Arabic: the change forms and their errors are translated', async ({ page }) => {
  await confirmedAccount(page);
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const change = page.getByTestId('change-email');
  await expect(change.getByRole('heading')).toHaveText('تغيير البريد الإلكتروني');
  await expect(change.getByTestId('change-email-address')).toHaveAttribute('dir', 'ltr');
  await change.getByTestId('change-email-address').fill(unique('arabic'));
  await change.getByTestId('change-email-password').fill(`wrong-${PASSWORD}`);
  await change.getByTestId('change-email-submit').click();
  await expect(change.getByRole('alert')).toHaveText('كلمة المرور الحالية غير صحيحة.');
  await page.getByRole('button', { name: 'English' }).first().click();
});
