import { expect, test, type Page, type Request } from '@playwright/test';

import { ask } from './chat';

// The AI Assistant page as a conversation, through the real API with the scripted model (it
// answers from tool results; "fail" makes it fail), on the desktop and Pixel 7 projects:
// greeting, a question and a follow-up that keeps the topic, a chart only when asked for,
// Markdown tables, failure and retry, Stop while answering, Enter and Shift+Enter, persona
// switching, and the "New messages" button when reading older messages.

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}-${test.info().project.name}.png` });
}

/** Questions sent (guest or account), in order. */
function sent(page: Page): Request[] {
  const out: Request[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && /\/assistant\/(guest\/messages|conversations\/[^/]+\/messages)$/.test(r.url())) out.push(r);
  });
  return out;
}

test('a greeting is answered at once, without a lookup or a charge, and the welcome goes', async ({ page }) => {
  const asks = sent(page);
  await page.goto('/assistant?mode=synthetic');
  await expect(page.getByTestId('chat-greeting')).toHaveText('How can I help you?');
  await snap(page, 'after-welcome');
  const examples = page.getByTestId('suggestion');
  expect(await examples.count()).toBeLessThanOrEqual(3);
  await page.getByTestId('assistant-input').fill('Hello');
  await page.getByTestId('assistant-input').press('Enter');
  await expect(page.getByTestId('user-message').last()).toHaveText('Hello'); // shown at once
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'profile');
  await expect(reply.getByTestId('chat-sources')).toHaveCount(0); // no statistical search
  await expect(page.getByTestId('chat-welcome')).toHaveCount(0);
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
  expect(asks[0]?.postDataJSON()).toMatchObject({ content: 'Hello', mode: 'auto' }); // no mode to choose first
});

test('a question, then a follow-up that keeps the topic; a chart only when asked for', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const first = await ask(page, 'What is the latest electricity generation?');
  await expect(first).toHaveAttribute('data-status', 'answered');
  await expect(first.getByTestId('assistant-text')).toContainText('50100');
  await expect(first.getByTestId('citation-chip')).toHaveCount(1);

  const follow = await ask(page, 'Compare it with the previous year.');
  await expect(follow).toHaveAttribute('data-status', 'answered');
  await expect(follow.getByTestId('reply-mode')).toHaveText('Compare'); // inferred from the words
  await expect(follow.getByTestId('assistant-text')).toContainText('2001');
  await expect(follow.getByTestId('assistant-text')).toContainText('2002');
  await expect(follow.getByTestId('citation-chip')).toHaveCount(2);
  // The sources are one line, opened on request; a citation opens them at its source.
  const sources = follow.getByTestId('chat-sources');
  await expect(sources).toContainText('Sources (2)');
  await expect(sources).not.toHaveAttribute('open', '');
  await follow.getByTestId('citation-chip').first().click();
  await expect(sources).toHaveAttribute('open', '');
  await expect(page.getByTestId('inline-chart')).toHaveCount(0); // never drawn unasked

  const chart = await ask(page, 'Show a chart of the history of electricity generation');
  await expect(chart).toHaveAttribute('data-status', 'answered');
  const figure = chart.getByTestId('inline-chart');
  await expect(figure).toHaveAttribute('data-points', '2');
  await expect(figure.getByTestId('inline-chart-sources')).toContainText('Published values only');
  await expect(page.getByTestId('inline-chart')).toHaveCount(1);
  await snap(page, 'after-follow-up-and-chart');
});

test('answers render Markdown safely: a heading, a table and a list', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'Show a table of electricity generation');
  const text = reply.getByTestId('assistant-text');
  await expect(text.locator('h3')).toHaveText('Published values');
  await expect(text.locator('th')).toHaveText(['Year', 'Value']);
  await expect(text.locator('tbody tr')).toHaveCount(2);
  await expect(text.locator('tbody tr').first()).toContainText('48000 GWh');
  await expect(text.locator('tbody tr').first().getByTestId('citation-chip')).toHaveCount(1);
  await expect(text.locator('ul li')).toHaveText('Published values only, nothing estimated.');
  await expect(text).not.toContainText('|'); // no raw Markdown left
  await snap(page, 'after-markdown-table');
});

test('a failed send keeps the question and Retry sends it; a failed answer service gives a labelled report', async ({ page }) => {
  let first = true;
  await page.route(/\/api\/v1\/assistant\/guest\/messages$/, async (route) => {
    if (first && route.request().method() === 'POST') {
      first = false;
      await route.abort('connectionreset');
      return;
    }
    await route.continue();
  });
  await page.goto('/assistant?mode=synthetic');
  const input = page.getByTestId('assistant-input');
  await input.fill('What is the latest electricity generation?');
  await input.press('Enter');
  await expect(page.getByTestId('assistant-error')).toBeVisible();
  await expect(input).toHaveValue('What is the latest electricity generation?'); // nothing lost
  await page.getByTestId('error-retry').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'answered');
  await expect(page.getByTestId('assistant-error')).toHaveCount(0);
  await expect(input).toHaveValue('');
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '4'); // charged once

  const failed = await ask(page, 'please fail: latest electricity generation');
  await expect(failed).toHaveAttribute('data-status', 'data_report');
  await expect(failed.getByTestId('non-ai-label')).toHaveText('Data-based report without AI interpretation');
  await expect(failed.getByTestId('retry-answer')).toBeVisible();
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '4'); // not charged
  await snap(page, 'after-failure-report');
});

test('while answering: a short progress line and Stop instead of Send', async ({ page }) => {
  await page.route(/\/api\/v1\/assistant\/guest\/messages$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-input').fill('What is the latest electricity generation?');
  await page.getByTestId('assistant-input').press('Enter');
  await expect(page.getByTestId('assistant-loading')).toBeVisible();
  await expect(page.getByTestId('assistant-stop')).toBeVisible();
  await expect(page.getByTestId('assistant-send')).toHaveCount(0);
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'answered');
  await expect(page.getByTestId('assistant-send')).toBeVisible();
  await expect(page.getByTestId('assistant-loading')).toHaveCount(0);
});

test('Enter sends once, Shift+Enter starts a new line', async ({ page }) => {
  const asks = sent(page);
  await page.goto('/assistant?mode=synthetic');
  const input = page.getByTestId('assistant-input');
  await input.fill('What is the latest');
  await input.press('Shift+Enter');
  await input.pressSequentially('electricity generation?');
  await expect(input).toHaveValue('What is the latest\nelectricity generation?');
  expect(asks).toHaveLength(0);
  await input.press('Enter');
  await input.press('Enter'); // a second Enter while sending does nothing
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', 'answered');
  expect(asks).toHaveLength(1);
});

test('switching to Ilham changes who answers; the conversation stays', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await ask(page, 'Hello');
  const header = page.getByTestId('chat-header');
  await header.getByTestId('persona-option-ilham').click();
  await expect(page.getByTestId('mulhim-name')).toHaveText('Ilham');
  await expect(header.getByTestId('assistant-avatar').locator('img')).toHaveAttribute('src', /ilham-portrait/);
  const reply = await ask(page, 'Who are you?');
  await expect(reply).toHaveAttribute('data-persona', 'ilham');
  await expect(page.getByTestId('assistant-message').first()).toHaveAttribute('data-persona', 'mulhim');
  await header.getByTestId('persona-option-mulhim').click();
});

test('reading older messages: a new reply does not pull the page; "New messages" brings it', async ({ page }, info) => {
  await page.goto('/assistant?mode=synthetic');
  for (const q of ['Hello', 'Who are you?', 'What is OSRIP?', 'Hello']) await ask(page, q);
  const list = page.getByTestId('assistant-messages');
  // The message box stays below the conversation, never over the latest message.
  const composer = (await page.getByTestId('chat-composer').boundingBox())!;
  const last = (await page.getByTestId('assistant-message').last().boundingBox())!;
  expect(last.y + last.height).toBeLessThanOrEqual(composer.y + 1);
  await expect(page.getByTestId('assistant-input')).toBeInViewport();
  test.skip(await list.evaluate((el) => el.scrollHeight <= el.clientHeight + 100), `the conversation fits on ${info.project.name} without scrolling`);

  await page.route(/\/api\/v1\/assistant\/guest\/messages$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await route.continue();
  });
  await page.getByTestId('assistant-input').fill('Who are you?');
  await page.getByTestId('assistant-input').press('Enter');
  await expect(page.getByTestId('assistant-loading')).toBeVisible();
  await list.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll')); }); // reading from the top
  await expect(page.getByTestId('assistant-message')).toHaveCount(5);
  await expect(page.getByTestId('chat-new-messages')).toBeVisible();
  expect(await list.evaluate((el) => el.scrollTop)).toBeLessThan(50); // not pulled down
  await page.getByTestId('chat-new-messages').click();
  await expect(page.getByTestId('chat-new-messages')).toHaveCount(0);
  await expect(page.getByTestId('assistant-message').last()).toBeInViewport();
});
