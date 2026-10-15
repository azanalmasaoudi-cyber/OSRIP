import { expect, test, type Page } from '@playwright/test';

// Registration, sign-in and linking by phone through the real stack. SMS delivery
// uses the scripted test provider (serve_e2e.py): codes are read from the
// development SMS outbox, the way a person reads the message on their phone.
// Numbers are random Omani-format test numbers; nothing is sent to a real phone.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

function omaniNumber(): string {
  return `9${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
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

async function sendCode(page: Page, national: string, name?: string): Promise<void> {
  const box = page.getByTestId('phone-verification');
  if (name !== undefined) await box.locator('input[autocomplete="name"]').fill(name);
  await expect(page.getByTestId('phone-country')).toHaveValue('+968'); // Oman by default
  await page.getByTestId('phone-number').fill(national);
  await page.getByTestId('phone-send').click();
  // Right after another code to the same number, the server asks the user to wait
  // (3 s cooldown in e2e); the button counts down, then the user sends again.
  const sent = page.getByTestId('phone-sent');
  const cooldown = page.locator('[data-testid="phone-error"][data-code="sms_resend_cooldown"]');
  await expect(sent.or(cooldown)).toBeVisible();
  if (await cooldown.isVisible()) {
    await expect(page.getByTestId('phone-send')).toBeEnabled({ timeout: 10_000 });
    await page.getByTestId('phone-send').click();
  }
  await expect(sent).toContainText(`+968 ••••••${national.slice(-2)}`);
}

async function enterCode(page: Page, code: string): Promise<void> {
  await page.getByTestId('phone-code').fill(code);
  await page.getByTestId('phone-verify').click();
}

async function registerByPhone(page: Page, national: string, name = 'Phone E2E'): Promise<void> {
  await page.goto('/register?method=phone');
  await sendCode(page, national, name);
  await enterCode(page, await smsCode(page, national));
  await expect(page).toHaveURL(/\/account/);
}

test('register with a phone number only: code, wrong code, ordinary access', async ({ page }) => {
  const national = omaniNumber();
  await page.goto('/register');
  // Email is the default; choosing Phone is kept in the address.
  await page.getByTestId('register-method').getByRole('radio', { name: 'Phone' }).click();
  await expect(page).toHaveURL(/method=phone/);
  await expect(page.getByTestId('sms-test-mode')).toContainText('not sent to real phones');
  await sendCode(page, national, 'Salim E2E');
  const code = await smsCode(page, national);
  // The code never appears in the page itself.
  await expect(page.locator('body')).not.toContainText(code);

  await enterCode(page, code === '000000' ? '111111' : '000000');
  await expect(page.getByTestId('phone-error')).toHaveAttribute('data-code', 'sms_code_incorrect');
  await expect(page.getByTestId('phone-error')).toContainText('4 attempts left');

  await enterCode(page, code);
  await expect(page).toHaveURL(/\/account/);
  await expect(page.getByTestId('account-phone')).toContainText(`+968 ••••••${national.slice(-2)}`);
  await expect(page.getByTestId('account-phone')).toContainText('Verified');
  await expect(page.getByTestId('account-email')).toContainText('No e-mail address');
  await expect(page.getByTestId('account-roles')).toHaveText('Viewer');
});

test('Arabic: phone registration is right-to-left, the number stays left-to-right', async ({ page }) => {
  const national = omaniNumber();
  await page.goto('/register?method=phone');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByText('رقم الهاتف المحمول')).toBeVisible();
  await expect(page.getByTestId('phone-number')).toHaveAttribute('dir', 'ltr');
  await expect(page.getByTestId('phone-country').locator('option:checked')).toContainText('+968');
  await page.getByTestId('phone-number').fill('24123456'); // a landline cannot receive SMS
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-error')).toHaveAttribute('data-code', 'invalid_phone');
  await expect(page.getByTestId('phone-error')).toContainText('تبدأ بـ 7 أو 9');
  await page.getByTestId('phone-number').fill(national);
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-sent')).toContainText('أرسلنا رمزاً');
  await enterCode(page, await smsCode(page, national));
  await expect(page).toHaveURL(/\/account/);
  await expect(page.getByTestId('account-phone')).toContainText('تم التحقق');
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('sign in with a phone code, including the resend countdown', async ({ page, browser }) => {
  const national = omaniNumber();
  await registerByPhone(page, national);

  const context = await browser.newContext();
  const other = await context.newPage();
  await other.goto('/sign-in');
  await other.getByTestId('sign-in-method').getByRole('radio', { name: 'Phone' }).click();
  await sendCode(other, national);
  const first = await smsCode(other, national);
  await expect(other.getByTestId('phone-resend')).toBeDisabled();
  await expect(other.getByTestId('phone-resend')).toContainText('New code in');
  // The e2e server's cooldown is 3 s; then a new code can be sent.
  await expect(other.getByTestId('phone-resend')).toBeEnabled({ timeout: 10_000 });
  await other.getByTestId('phone-resend').click();
  await expect.poll(async () => (await smsCode(other, national)) !== first).toBe(true);
  await enterCode(other, await smsCode(other, national));
  await expect(other).toHaveURL(/\/account/);
  await expect(other.getByTestId('account-phone')).toContainText(national.slice(-2));
  await context.close();
});

test('keyboard: the method choice moves with the arrow keys, mirrored in Arabic', async ({ page }) => {
  await page.goto('/register');
  const email = page.getByTestId('register-method').getByRole('radio', { name: 'E-mail' });
  await email.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('register-method').getByRole('radio', { name: 'Phone' })).toBeFocused();
  await expect(page).toHaveURL(/method=phone/);
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await page.getByTestId('register-method').getByRole('radio', { checked: true }).focus();
  await page.keyboard.press('ArrowLeft'); // "forward" in right-to-left
  await expect(page).not.toHaveURL(/method=phone/); // wrapped back to e-mail
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('the chosen method survives Back and Forward', async ({ page }) => {
  await page.goto('/register');
  await page.getByTestId('register-method').getByRole('radio', { name: 'Phone' }).click();
  await expect(page).toHaveURL(/method=phone/);
  await page.getByRole('link', { name: 'Already have an account? Sign in' }).click();
  await expect(page).toHaveURL(/\/sign-in/);
  await page.goBack();
  await expect(page).toHaveURL(/\/register\?.*method=phone/);
  await expect(page.getByTestId('register-method').getByRole('radio', { name: 'Phone' })).toHaveAttribute('aria-checked', 'true');
  await page.goForward();
  await expect(page).toHaveURL(/\/sign-in/);
});

test('delivery failure is explained and offers e-mail instead', async ({ page }) => {
  await page.goto('/register?method=phone');
  await page.getByTestId('phone-number').fill('90000000'); // test number: undeliverable
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-error')).toHaveAttribute('data-code', 'sms_undeliverable');
  await page.getByRole('button', { name: 'Use e-mail instead' }).click();
  await expect(page).not.toHaveURL(/method=phone/);
  await expect(page.getByTestId('register-form')).toBeVisible();
});

test('when SMS is not configured, phone is marked unavailable and e-mail is offered', async ({ page }) => {
  await page.route('**/api/v1/auth/providers', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.sms = { ...body.sms, available: false, status: 'not_configured', provider: null };
    await route.fulfill({ response, json: body });
  });
  await page.goto('/register');
  const phone = page.getByTestId('register-method').getByRole('radio', { name: /Phone/ });
  await expect(phone).toContainText('(unavailable)');
  await phone.click();
  await expect(page.getByTestId('phone-unavailable')).toContainText('no SMS service configured');
  await page.getByTestId('phone-unavailable').getByRole('button', { name: 'Use e-mail instead' }).click();
  await expect(page.getByTestId('register-form')).toBeVisible();
});

test('linking: an e-mail account adds a phone only after verifying it', async ({ page }, info) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  // One account per project (desktop and phone both run this spec).
  await form.getByLabel('E-mail address').fill(info.project.name === 'mobile' ? 'manager@e2e.invalid' : 'viewer@e2e.invalid');
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/account/);
  const national = omaniNumber();
  const add = page.getByTestId('add-phone');
  await add.getByTestId('add-phone-open').click();
  await sendCode(page, national);
  await expect(page.getByTestId('account-phone')).toContainText('No phone number'); // not before verification
  await enterCode(page, await smsCode(page, national));
  await expect(add).toContainText('Phone number verified');
  await page.reload();
  await expect(page.getByTestId('account-phone')).toContainText(national.slice(-2));
  await expect(page.getByTestId('add-phone')).toHaveCount(0);
});

test('linking: a phone account adds an e-mail only after opening the link sent to it', async ({ page }) => {
  await registerByPhone(page, omaniNumber());
  const address = `linked-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.invalid`;
  const add = page.getByTestId('add-email');
  await add.getByLabel('E-mail address').fill(address);
  await add.getByRole('button', { name: 'Send confirmation link' }).click();
  await expect(add).toContainText('a message is on its way');
  await page.reload();
  await expect(page.getByTestId('account-email')).toContainText('No e-mail address');

  await page.goto('/dev/mail');
  const message = page.locator(`[data-testid="dev-mail"] li[data-to="${address}"][data-purpose="link_email"]`).first();
  await message.getByRole('link').first().click();
  await expect(page).toHaveURL(/\/link-email/);
  await page.getByTestId('link-email-confirm').click();
  await expect(page.getByTestId('link-email')).toContainText('confirmed and added');
  await page.goto('/account');
  await expect(page.getByTestId('account-email')).toContainText(address);
  await expect(page.getByTestId('account-email')).toContainText('Confirmed');
});
