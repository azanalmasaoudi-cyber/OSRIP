import { expect, test, type Page } from '@playwright/test';

import { openHistory, setAnswerLanguage } from './chat';

// The assistant through the real stack. The model is the backend's scripted test
// double (OSRIP_ASSISTANT_PROVIDER=fake, refused in production): it answers only
// from tool results, unless asked to "invent" (to exercise the evidence check) or
// to "fail" (to exercise the model-failure path). Runs on desktop and phone. There is one
// conversation, on the AI Assistant page; the floating orb on other pages is a shortcut to it.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('Username').fill('e2eviewer');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
}

async function openAssistant(page: Page, path = '/energy/electricity?mode=synthetic'): Promise<void> {
  await page.goto(path);
  await page.getByTestId('open-assistant').first().click();
  await expect(page).toHaveURL(/\/assistant/);
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
    // The conversation's own answer language (Settings); the interface stays in English.
    await setAnswerLanguage(page, arabic ? 'العربية' : 'English');
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
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '0');
  await expect(page.getByTestId('assistant-sign-in')).toBeVisible();
  await expect(page.getByTestId('assistant-message')).toHaveCount(5);
  // Public statistics stay open.
  await page.goto('/energy/electricity?mode=synthetic');
  await expect(page.getByTestId('sector-form')).toBeVisible();
});

test('the orb is a keyboard shortcut to the one conversation, never a second chat', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const orb = page.getByTestId('open-assistant').first();
  await expect(orb).toHaveAttribute('data-state', 'idle');
  await expect(page.getByTestId('assistant-panel')).toHaveCount(0); // no chat on this page
  await orb.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/assistant\?mode=synthetic$/); // the data mode is kept
  await expect(page.getByTestId('assistant-panel')).toHaveCount(1);
  await expect(page.getByTestId('open-assistant')).toHaveCount(0); // the conversation is on screen
  await page.getByTestId('assistant-input').fill('please fail');
  await page.keyboard.press('Enter');
  // The answer service failed: a data-based report (no topic named, so no figures), not charged.
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'data_report');
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
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
  // The sources stay with the answer and are shown only when asked for.
  const citation = reply.getByTestId('citation');
  await expect(citation).toHaveCount(0);
  await reply.getByTestId('toggle-sources').click();
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
  await expect(withheld).toContainText('ask for the sources to see what was found');
  await expect(withheld.getByTestId('citation')).toHaveCount(0);
  await withheld.getByTestId('toggle-sources').click();
  await expect(withheld.getByTestId('citation')).toContainText('50,100'); // what was found, on request

  await ask(page, 'please fail');
  const failed = page.getByTestId('assistant-message').last();
  await expect(failed).toHaveAttribute('data-status', 'data_report');
  await expect(failed.getByRole('button', { name: 'Try the AI answer again' })).toBeVisible();

  await ask(page, 'How did it change?');
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'clarification');
});

test('one unsupported figure leaves the rest of the answer; sources are listed when asked for', async ({ page }) => {
  await signIn(page);
  await openAssistant(page);
  await ask(page, 'Partly invent the latest electricity generation');
  const partial = page.getByTestId('assistant-message').last();
  await expect(partial).toHaveAttribute('data-status', 'answered');
  await expect(partial.getByTestId('assistant-text')).toContainText('50100');
  await expect(partial.getByTestId('assistant-text')).toContainText('completeness');
  await expect(partial).not.toContainText('987654321');
  await expect(partial.getByTestId('omitted-claims')).toContainText('could not be matched to the evidence (1)');

  await ask(page, 'Show sources');
  const listed = page.getByTestId('assistant-message').last();
  await expect(listed).toHaveAttribute('data-status', 'sources');
  await expect(listed.getByTestId('non-ai-label')).toHaveText('Sources, as asked');
  await expect(listed.getByTestId('assistant-text')).toContainText('Sources of the previous answer:');
  await expect(listed.getByTestId('assistant-text')).toContainText('OSRIP booklet worked-example fixtures (synthetic)');
  await expect(listed.getByTestId('citation').first()).toBeVisible(); // the details, shown at once
  await expect(listed.getByTestId('toggle-sources')).toHaveCount(0);
});

test('missing verified data is reported as unavailable, not zero', async ({ page }) => {
  await signIn(page);
  await openAssistant(page, '/energy/electricity');
  await ask(page, 'What is the latest electricity generation?');
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'no_evidence');
  await expect(reply).toContainText('no published data');
});

test('Arabic questions get Arabic answers in a right-to-left conversation', async ({ page }) => {
  await signIn(page);
  await page.goto('/energy/electricity?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await page.getByTestId('open-assistant').first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await ask(page, 'ما آخر قيمة لتوليد الكهرباء؟');
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply.getByTestId('assistant-text')).toContainText('آخر قيمة منشورة');
  await expect(reply.getByTestId('ai-label')).toHaveText('مولّد بالذكاء الاصطناعي');
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('conversations are listed in the history, reopened and deleted there', async ({ page }) => {
  await signIn(page);
  await openAssistant(page);
  const question = `How did it change? ${Date.now()}`;
  await ask(page, question);
  await expect(page.getByTestId('assistant-message')).toHaveCount(1);
  let history = await openHistory(page);
  await expect(history.locator('[data-testid="conversation-item"][data-active="true"]')).toHaveCount(1);
  if (await page.locator('dialog[open]').count()) await page.keyboard.press('Escape');
  // A new conversation empties the chat; the earlier one is reopened from the history.
  await page.getByTestId('chat-new').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
  await expect(page.getByTestId('chat-welcome')).toBeVisible();
  history = await openHistory(page);
  await history.getByTestId('conversation-item').first().getByTestId('conversation-open').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(1);
  await expect(page.getByTestId('user-message').first()).toHaveText(question);
  // Deleting asks once more, then removes it from the list and the chat.
  history = await openHistory(page);
  const count = await history.getByTestId('conversation-item').count();
  const current = history.locator('[data-testid="conversation-item"][data-active="true"]');
  await current.getByTestId('conversation-delete').click();
  await current.getByTestId('conversation-delete-confirm').click();
  await expect(history.getByTestId('conversation-item')).toHaveCount(count - 1);
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
});
