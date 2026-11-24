import { expect, test } from '@playwright/test';

import { ask } from './chat';

// Al Mulhim through the real stack (scripted model): asked for recommendations without an
// objective, it gives the results first and asks which objectives to serve; the person ticks them
// in the reply and sends them as the next message, written out; the next reply records them.
// With an objective in the first request, nothing is asked again.

test('recommendations wait for objectives, which the reply lets the person choose', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'What should be done about electricity generation?');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('assistant-text')).toContainText('latest published value');
  await expect(reply.getByTestId('assistant-text')).toContainText('Which objective should the recommendations serve');
  await expect(reply.getByTestId('recommendation-card')).toHaveCount(0);
  const choose = reply.getByTestId('reply-objectives');
  await expect(choose).toHaveAttribute('data-status', 'ask');
  await expect(choose.getByTestId('reply-objectives-send')).toBeDisabled();
  await choose.getByTestId('reply-objective-reduce_shortages').check();
  await choose.getByTestId('reply-objective-diversify').check();
  const before = await page.getByTestId('assistant-message').count();
  await choose.getByTestId('reply-objectives-send').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(before + 1);
  await expect(page.getByText('My objectives: Reduce shortages, Diversify. Please give the recommendations.')).toBeVisible();
  const next = page.getByTestId('assistant-message').last();
  await expect(next).toHaveAttribute('data-status', 'answered');
  const known = next.getByTestId('reply-objectives');
  await expect(known).toHaveAttribute('data-status', 'known');
  await expect(known).toContainText('Reduce shortages');
  await expect(known).toContainText('Diversify');
  await expect(next.getByTestId('assistant-text')).not.toContainText('Which objective');
});

test('an objective in the request: no question about objectives, in Arabic too', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  const reply = await ask(page, 'ما توصياتك لتوليد الكهرباء لتقليل العجز؟');
  await expect(reply.getByTestId('reply-objectives')).toHaveAttribute('data-status', 'known');
  await expect(reply.getByTestId('reply-objectives')).toContainText('تقليل العجز');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByRole('button', { name: 'English' }).first().click();
});
