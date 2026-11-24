import { expect, test } from '@playwright/test';

import { ask } from './chat';

// A sector and Al Mulhim on a phone (Pixel 7), through the real stack: the three sector views
// are tabs that fit the screen, one panel at a time (no box that scrolls inside the page), and a
// question's live study opens under its reply. Nothing scrolls sideways.

test.skip(({ isMobile }) => !isMobile, 'phone layout only');

const sideways = (page: import('@playwright/test').Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test('phone: the sector tabs fit, each view shows on its own, and nothing scrolls sideways', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const tabs = page.getByTestId('sector-tabs');
  await expect(tabs.getByRole('tab')).toHaveText(['Data and indicators', 'Guided analysis', 'Tables and charts']);
  await expect(page.getByTestId('sector-guide')).toBeVisible();
  expect(await sideways(page)).toBeLessThanOrEqual(0);
  await tabs.locator('[data-tab="data"]').click();
  await expect(page.getByTestId('indicator-card').first()).toBeVisible();
  await expect(page.getByTestId('sector-guide')).toHaveCount(0);
  expect(await sideways(page)).toBeLessThanOrEqual(0);
  await tabs.locator('[data-tab="charts"]').click();
  await expect(page.getByTestId('sector-form')).toBeVisible();
  expect(await sideways(page)).toBeLessThanOrEqual(0);
});

test('phone: a question in Al Mulhim opens its live study under the reply', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'What is the latest electricity generation?');
  await reply.getByTestId('open-study').click();
  const study = reply.getByTestId('reply-live-study').getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.getByTestId('study-finding').first()).toContainText('50100');
  await expect(study.getByTestId('study-datasets').getByTestId('dataset')).toHaveAttribute('data-state', 'final');
  expect(await sideways(page)).toBeLessThanOrEqual(0);
});
