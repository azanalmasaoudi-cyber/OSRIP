import { expect, test, type Page } from '@playwright/test';

// Al Mulhim's identity through the real stack: approved greeting and introduction (not
// AI-generated, not charged), the About panel with the interpretation and reference, and
// the "what is remembered" panel with delete controls.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('E-mail address').fill('viewer@e2e.invalid');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
}

test('a guest greeting gets the approved reply once, free of charge, in Arabic', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const allowance = page.getByTestId('guest-allowance');
  await expect(allowance).toHaveAttribute('data-remaining', '5');
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  await page.getByTestId('assistant-input').fill('السلام عليكم');
  await page.getByTestId('assistant-send').click();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'profile');
  await expect(reply.getByTestId('assistant-text')).toContainText('وعليكم السلام ورحمة الله وبركاته');
  await expect(reply.getByTestId('assistant-text')).toContainText('أنا المُلْهِم، مساعد OSRIP');
  await expect(reply.getByTestId('non-ai-label')).toBeVisible();
  await expect(allowance).toHaveAttribute('data-remaining', '5');
  // A second greeting does not repeat the introduction.
  await page.getByTestId('assistant-input').fill('السلام عليكم');
  await page.getByTestId('assistant-send').click();
  const second = page.getByTestId('assistant-message').last();
  await expect(second.getByTestId('assistant-text')).toContainText('كيف أستطيع مساعدتك؟');
  await expect(second.getByTestId('assistant-text')).not.toContainText('أنا المُلْهِم');
});

test('the About panel shows the meaning, the interpretation label and the cited reference', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const about = page.getByTestId('about-mulhim');
  await about.locator('summary').click();
  await expect(about).toContainText('one who inspires');
  await expect(about.getByTestId('mulhim-interpretation')).toContainText('Linguistic interpretation');
  await expect(about.getByRole('link', { name: /Academy of the Arabic Language in Cairo/ })).toHaveAttribute('href', /arabicacademy\.gov\.eg/);
  await expect(about).toContainText('Approved profile version');
});

test('a signed-in user sees what is kept and can delete all conversations', async ({ page }) => {
  await signIn(page);
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-input').fill('Who are you?');
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'profile');
  const memory = page.getByTestId('mulhim-memory');
  await memory.locator('summary').click();
  await expect(memory.getByTestId('memory-counts')).toContainText('Your conversations:');
  await memory.getByTestId('delete-all-conversations').click();
  await memory.getByTestId('delete-all-conversations').click(); // confirm
  await expect(memory).toContainText(/Deleted \d+ conversations/);
  await expect(memory.getByTestId('memory-counts')).toContainText('Your conversations: 0');
});
