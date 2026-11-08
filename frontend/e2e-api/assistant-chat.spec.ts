import { expect, test, type Page } from '@playwright/test';

import { ask, closeDrawer, openHistory, openTools } from './chat';

// The one Al Mulhim conversation through the real stack (scripted model and search stand-ins:
// nothing leaves the machine). The old Talk screen is gone and /talk opens this page; there is
// one assistant screen, with the conversation history beside it (a drawer on phones), a
// centred welcome, a large message box and the optional Tools menu. Synthetic demonstration
// data is named on the answers that use it, never on internet answers.

async function noSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('/talk opens the conversation, keeping only the data mode and a question to prefill', async ({ page }) => {
  await page.goto('/talk?mode=synthetic&persona=ilham&q=Water%20production%20in%202025');
  await expect(page).toHaveURL(/\/assistant\?mode=synthetic&q=Water\+production\+in\+2025$/);
  await expect(page.getByTestId('talk-workspace')).toHaveCount(0);
  await expect(page.getByTestId('assistant-panel')).toHaveCount(1); // one assistant screen
  // The question is prefilled for review, never sent by itself.
  await expect(page.getByTestId('assistant-input')).toHaveValue('Water production in 2025');
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  // No navigation item or link leads to the old screen.
  await expect(page.locator('a[href*="/talk"]')).toHaveCount(0);
});

test('desktop: history beside a centred welcome and a large message box; no persona choice, mode buttons or call controls', async ({ page }, info) => {
  test.skip(info.project.name === 'mobile', 'the phone layout is tested below');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/assistant?mode=synthetic');
  const history = page.getByTestId('chat-history');
  await expect(history).toBeVisible();
  await expect(history.getByTestId('history-new')).toBeVisible();
  await expect(history.getByTestId('history-guest-note')).toContainText('Sign in to keep your conversations');
  await expect(page.getByTestId('chat-history-open')).toBeHidden();
  const welcome = page.getByTestId('chat-welcome');
  await expect(welcome).toContainText('How can I help you?');
  await expect(page.getByTestId('chat-welcome-lead')).toContainText('search the internet');
  // The welcome is centred over the message box, which is at least 640px wide.
  const box = (await page.getByTestId('chat-composer').boundingBox())!;
  const greeting = (await page.getByTestId('chat-greeting').boundingBox())!;
  expect(box.width).toBeGreaterThanOrEqual(640);
  expect(Math.abs((greeting.x + greeting.width / 2) - (box.x + box.width / 2))).toBeLessThan(3);
  // The clutter of the old screen is gone; Tools is one small control.
  for (const id of ['persona-picker', 'talk-end', 'talk-workspace', 'assistant-controls', 'assistant-identity']) {
    await expect(page.getByTestId(id)).toHaveCount(0);
  }
  await expect(page.getByTestId('assistant-mode')).toBeHidden(); // in the Tools menu, not on screen
  await expect(page.getByTestId('chat-composer').getByTestId('voice-start')).toBeVisible();
  await expect(page.getByTestId('chat-composer').getByTestId('chat-tools')).toBeVisible();
  // A guest's conversation appears in the history once started.
  await ask(page, 'What is the latest electricity generation?');
  await expect(history.locator('[data-testid="conversation-item"][data-active="true"]')).toHaveText(/Current conversation/);
  await noSidewaysScroll(page);
});

test('synthetic data is named on answers from OSRIP’s data, never on internet answers', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const data = await ask(page, 'What is the latest electricity generation?');
  await expect(data).toHaveAttribute('data-status', 'answered');
  await expect(data.getByTestId('data-mode-badge')).toHaveText('Synthetic');
  await openTools(page);
  await page.getByTestId('assistant-mode').getByRole('radio', { name: 'Quick answer', exact: true }).click();
  await closeDrawer(page);
  const web = await ask(page, 'web electricity generation 2023');
  await expect(web).toHaveAttribute('data-status', 'answered');
  await expect(web.getByTestId('reply-mode')).toHaveText('Quick answer');
  await expect(web.getByTestId('data-mode-badge')).toHaveCount(0);
  // No evidence list under the answers until asked for.
  for (const reply of [data, web]) {
    await expect(reply).toHaveAttribute('data-sources', 'hidden');
    await expect(reply.getByTestId('chat-sources')).toHaveCount(0);
  }
});

test('phone: the history is a drawer; one column without sideways scrolling, in Arabic too', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'phone layout');
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('chat-history')).toBeHidden();
  const history = await openHistory(page);
  await expect(history.getByTestId('history-new')).toBeVisible();
  await closeDrawer(page);
  await expect(page.getByTestId('assistant-input')).toBeInViewport();
  await noSidewaysScroll(page);
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('chat-greeting')).toHaveText('كيف يمكنني مساعدتك؟');
  await noSidewaysScroll(page);
  await page.getByRole('button', { name: 'English' }).first().click();
});
