import { expect, type Page } from '@playwright/test';

/**
 * The AI Assistant page (/assistant) is one conversation; its optional controls are in two
 * drawers: Tools (answer mode, web search, research brief, analysis, a full study) and
 * conversation Settings (answer language, voice, conversations, memory, help).
 */
export async function openTools(page: Page): Promise<void> {
  await page.getByTestId('chat-tools').click();
  await expect(page.getByTestId('chat-tools-sheet')).toBeVisible();
}

export async function openChatSettings(page: Page): Promise<void> {
  await page.getByTestId('chat-settings').click();
  await expect(page.getByTestId('chat-settings-sheet')).toBeVisible();
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
