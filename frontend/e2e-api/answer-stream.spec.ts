import { expect, test, type Page } from '@playwright/test';

import { closeDrawer, openChatSettings, openTools } from './chat';

// The answer as it is written, through the real stack: the scripted model streams its answer in
// pieces (25 ms apart here, OSRIP_FAKE_STREAM_DELAY_MS), the server sends each sentence once it
// passes the evidence check, and the conversation shows them in order while the question is open.
// Nothing is typed out by the browser: the text shown is what has arrived. Stop ends it; Ask again
// asks anew. The stored reply replaces the streamed text when it is complete.

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}-${test.info().project.name}.png` });
}

async function deepResearch(page: Page): Promise<void> {
  await openTools(page);
  await page.getByTestId('assistant-mode').getByRole('radio', { name: 'Deep research', exact: true }).click();
  await closeDrawer(page);
}

async function send(page: Page, question: string): Promise<void> {
  await page.getByTestId('assistant-input').fill(question);
  await page.getByTestId('assistant-send').click();
}

test('a report is written sentence by sentence while it is open, then replaced by the stored reply', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await deepResearch(page);
  await send(page, 'Write a report on electricity generation in 2023');
  const pending = page.getByTestId('assistant-loading');
  const streamed = pending.getByTestId('answer-stream-text');
  // Text arrives while the question is still open (Stop is offered, no reply stored yet).
  await expect(streamed).toContainText('Summary');
  await expect(pending).toHaveAttribute('data-phase', 'writing');
  await expect(page.getByTestId('assistant-stop')).toBeVisible();
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);
  const early = Number(await pending.getAttribute('data-segments'));
  expect(early).toBeGreaterThan(0);
  await expect(pending.getByTestId('answer-stream-note')).toContainText('checked against the sources');
  await expect(streamed).not.toContainText('[E'); // evidence markers stay hidden, as in the reply
  await snap(page, 'answer-streaming-en');
  // More arrives, in order, before the reply is complete.
  await expect.poll(async () => Number(await pending.getAttribute('data-segments') ?? '0')).toBeGreaterThan(early);

  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(pending).toHaveCount(0);
  await expect(reply.getByTestId('assistant-text')).toContainText('Limitations and missing information');
});

test('Stop while it is written ends the answer; Ask again asks it anew', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await deepResearch(page);
  await send(page, 'Write a report on electricity generation in 2023');
  await expect(page.getByTestId('answer-stream-text')).toBeVisible();
  await page.getByTestId('assistant-stop').click();
  const stopped = page.getByTestId('assistant-message').last();
  await expect(stopped).toHaveAttribute('data-status', 'cancelled');
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5'); // not counted
  await stopped.getByTestId('ask-again').click();
  const again = page.getByTestId('assistant-message').last();
  await expect(again).toHaveAttribute('data-status', 'answered');
  await expect(page.getByTestId('assistant-message')).toHaveCount(2);
});

test('the report is streamed in Arabic, right to left', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await openChatSettings(page);
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  await closeDrawer(page);
  await openTools(page);
  await page.getByTestId('assistant-mode').getByRole('radio', { name: 'بحث معمّق', exact: true }).click();
  await closeDrawer(page);
  await send(page, 'اكتب تقريرا عن توليد الكهرباء في 2023');
  const pending = page.getByTestId('assistant-loading');
  await expect(pending.getByTestId('answer-stream-text')).toContainText('الملخص');
  await expect(pending.getByTestId('answer-stream-phase')).toHaveText('الكتابة');
  await snap(page, 'answer-streaming-ar');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'answered');
});
