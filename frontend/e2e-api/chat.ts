import { expect, type Locator, type Page } from '@playwright/test';

/**
 * The AI Assistant page (/assistant) is the one Al Mulhim conversation, with its history beside
 * it (a drawer on narrow screens); its optional controls are in two drawers: Tools (answer mode,
 * web search, research brief, analysis, a full study) and conversation Settings (answer
 * language, voice, memory, help).
 */
export async function openTools(page: Page): Promise<void> {
  await page.getByTestId('chat-tools').click();
  await expect(page.getByTestId('chat-tools-sheet')).toBeVisible();
}

export async function openChatSettings(page: Page): Promise<void> {
  await page.getByTestId('chat-settings').click();
  await expect(page.getByTestId('chat-settings-sheet')).toBeVisible();
}

/** The conversation history: the column beside the chat on wide screens, a drawer otherwise. */
export async function openHistory(page: Page): Promise<Locator> {
  const column = page.getByTestId('chat-history');
  if (await column.isVisible()) return column;
  await page.getByTestId('chat-history-open').click();
  const drawer = page.locator('dialog[open]');
  await expect(drawer.getByTestId('chat-history-body')).toBeVisible();
  return drawer;
}

/** Chooses the language Al Mulhim answers in (conversation Settings). */
export async function setAnswerLanguage(page: Page, language: 'English' | 'العربية'): Promise<void> {
  await openChatSettings(page);
  await page.getByTestId('assistant-language').getByRole('radio', { name: language }).click();
  await closeDrawer(page);
}

/** Closes the open drawer (Escape, as a keyboard user would). */
export async function closeDrawer(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect(page.locator('dialog[open]')).toHaveCount(0);
}

/** Sends a question with Enter and waits for one more reply. */
export async function ask(page: Page, question: string) {
  const before = await page.getByTestId('assistant-message').count();
  await page.getByTestId('assistant-input').fill(question);
  await page.getByTestId('assistant-input').press('Enter');
  await expect(page.getByTestId('assistant-message')).toHaveCount(before + 1);
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).not.toHaveAttribute('data-status', '');
  return reply;
}
