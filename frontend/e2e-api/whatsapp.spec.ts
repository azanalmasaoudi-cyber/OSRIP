import { expect, test, type Page } from '@playwright/test';

// The phone form when the server delivers codes by WhatsApp in test mode. The e2e server
// uses the scripted SMS provider, so the provider status is rewritten in the browser to
// what a WhatsApp test-mode server reports; codes still come from the scripted provider.
// Nothing is sent to WhatsApp or to a real phone.

async function asWhatsAppSandbox(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/providers', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.sms = { ...body.sms, status: 'sandbox', channel: 'whatsapp', provider: 'whatsapp' };
    await route.fulfill({ response, json: body });
  });
}

function omaniNumber(): string {
  return `9${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
}

test('WhatsApp test mode is labelled and the form speaks of WhatsApp', async ({ page }) => {
  await asWhatsAppSandbox(page);
  await page.goto('/register?method=phone');
  await expect(page.getByTestId('whatsapp-sandbox')).toContainText('only the approved test numbers');
  await expect(page.getByTestId('sms-test-mode')).toHaveCount(0);
  const national = omaniNumber();
  await page.getByTestId('phone-number').fill(national);
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-sent')).toContainText(`We sent a code by WhatsApp to +968 ••••••${national.slice(-2)}`);
  await expect(page.getByLabel('Code from the WhatsApp message')).toBeVisible();
});

test('a number outside the approved test list is explained, with e-mail offered', async ({ page }) => {
  await asWhatsAppSandbox(page);
  await page.route('**/api/v1/auth/phone/request', (route) => route.fulfill({
    status: 422,
    json: { error: { code: 'sms_not_test_recipient', message: 'This is a WhatsApp demonstration.' } },
  }));
  await page.goto('/register?method=phone');
  await page.getByTestId('phone-number').fill(omaniNumber());
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-error')).toHaveAttribute('data-code', 'sms_not_test_recipient');
  await expect(page.getByTestId('phone-error')).toContainText('codes are sent only to the approved test numbers');
  await page.getByRole('button', { name: 'Use e-mail instead' }).click();
  await expect(page.getByTestId('register-form')).toBeVisible();
});

test('Arabic: WhatsApp test mode and wording', async ({ page }) => {
  await asWhatsAppSandbox(page);
  await page.goto('/register?method=phone');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('whatsapp-sandbox')).toContainText('أرقام الاختبار المعتمدة فقط');
  await page.getByTestId('phone-number').fill(omaniNumber());
  await page.getByTestId('phone-send').click();
  await expect(page.getByTestId('phone-sent')).toContainText('أرسلنا رمزاً عبر واتساب');
  await page.getByRole('button', { name: 'English' }).first().click();
});
