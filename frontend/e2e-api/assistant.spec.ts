import { expect, test, type Page } from '@playwright/test';

// The assistant through the real stack. The model is the backend's scripted test
// double (OSRIP_ASSISTANT_PROVIDER=fake, refused in production): it answers only
// from tool results, unless asked to "invent" (to exercise the evidence check) or
// to "fail" (to exercise the model-failure path). Runs on desktop and phone.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('E-mail address').fill('viewer@e2e.invalid');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
}

async function openAssistant(page: Page, path = '/energy/electricity?mode=synthetic'): Promise<void> {
  await page.goto(path);
  await page.getByTestId('open-assistant').first().click();
  await expect(page.getByTestId('assistant-panel')).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  await page.getByTestId('assistant-input').fill(question);
  await page.getByTestId('assistant-send').click();
}

test('guests get five answers across languages, then a sign-in prompt that survives reload', async ({ page }) => {
  await openAssistant(page);
  const allowance = page.getByTestId('guest-allowance');
  await expect(allowance).toContainText('5 of 5 free answers left');
  const questions = ['What is the latest electricity generation?', 'ما آخر قيمة لتوليد الكهرباء؟'];
  for (let n = 1; n <= 5; n += 1) {
    const arabic = n % 2 === 0;
    // The panel's own language selector; the interface stays in English.
    await page.getByTestId('assistant-language').getByRole('radio', { name: arabic ? 'العربية' : 'English' }).click();
    await ask(page, questions[arabic ? 1 : 0] ?? '');
    await expect(page.getByTestId('assistant-message')).toHaveCount(n);
    await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'answered');
    await expect(allowance).toHaveAttribute('data-remaining', String(5 - n));
  }
  // The fifth answer is complete; the next question needs an account.
  await expect(page.getByTestId('assistant-message').last().getByTestId('assistant-text')).toContainText('50100');
  await expect(page.getByTestId('assistant-sign-in')).toContainText('You have used the free answers');
  await expect(page.getByTestId('assistant-input')).toBeDisabled();
  // Reloading (or another tab) keeps the server-side count and the conversation.
  await page.reload();
  await page.getByTestId('open-assistant').first().click();
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '0');
  await expect(page.getByTestId('assistant-sign-in')).toBeVisible();
  await expect(page.getByTestId('assistant-message')).toHaveCount(5);
  // Public statistics stay open.
  await page.keyboard.press('Escape');
  await page.goto('/energy/electricity?mode=synthetic');
  await expect(page.getByTestId('series-card').first()).toBeVisible();
});

test('the orb shows real states and the panel works by keyboard', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const orb = page.getByTestId('open-assistant').first();
  await expect(orb).toHaveAttribute('data-state', 'idle');
  await orb.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('assistant-panel')).toBeVisible();
  await page.getByTestId('assistant-input').fill('please fail');
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'unavailable');
  // A failure is not charged.
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('assistant-panel')).toBeHidden();
  await expect(orb).toBeFocused(); // focus returns to the orb
});

test('answers cite the published source and are labelled AI-generated', async ({ page }) => {
  await signIn(page);
  await openAssistant(page);
  await expect(page.getByTestId('suggestions')).toBeVisible();
  await ask(page, 'What is the latest electricity generation?');
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('ai-label')).toHaveText('AI-generated');
  await expect(reply.getByTestId('assistant-text')).toContainText('50100');
  const citation = reply.getByTestId('citation');
  await expect(citation).toContainText('50,100');
  await expect(citation).toContainText('OSRIP booklet worked-example fixtures (synthetic)');
  await expect(citation).toContainText('Synthetic demonstration data');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('an unsupported number is withheld; failures and ambiguity are explained', async ({ page }) => {
  await signIn(page);
  await openAssistant(page);
  await ask(page, 'Invent the latest electricity generation');
  const withheld = page.getByTestId('assistant-message').last();
  await expect(withheld).toHaveAttribute('data-status', 'unverified');
  await expect(withheld).not.toContainText('123456789');
  await expect(withheld.getByTestId('citation')).toContainText('50,100'); // the evidence is shown instead

  await ask(page, 'please fail');
  const failed = page.getByTestId('assistant-message').last();
  await expect(failed).toHaveAttribute('data-status', 'unavailable');
  await expect(failed.getByRole('button', { name: 'Try again' })).toBeVisible();

  await ask(page, 'How did it change?');
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'clarification');
});

test('missing verified data is reported as unavailable, not zero', async ({ page }) => {
  await signIn(page);
  await openAssistant(page, '/energy/electricity');
  await ask(page, 'What is the latest electricity generation?');
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'no_evidence');
  await expect(reply).toContainText('no published data');
});

test('Arabic questions get Arabic answers in a right-to-left panel', async ({ page }) => {
  await signIn(page);
  await page.goto('/energy/electricity?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await page.getByTestId('open-assistant').first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await ask(page, 'ما آخر قيمة لتوليد الكهرباء؟');
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply.getByTestId('assistant-text')).toContainText('آخر قيمة منشورة');
  await expect(reply.getByTestId('ai-label')).toHaveText('مولّد بالذكاء الاصطناعي');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('a conversation can be deleted', async ({ page }) => {
  await signIn(page);
  await openAssistant(page);
  await ask(page, 'How did it change?');
  await expect(page.getByTestId('assistant-message')).toHaveCount(1);
  const select = page.getByTestId('conversation-select');
  const id = await select.inputValue();
  expect(id).not.toBe('');
  await page.getByTestId('delete-conversation').click();
  await page.getByTestId('delete-conversation').click(); // confirm
  await expect(select).toHaveValue('');
  await expect(select.locator(`option[value="${id}"]`)).toHaveCount(0);
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
});
