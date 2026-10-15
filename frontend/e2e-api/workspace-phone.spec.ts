import { expect, test } from '@playwright/test';

// The workspace on a phone (Pixel 7): Data, Study and Assistant are tabs; asking brings the
// Study tab forward with the live results; nothing scrolls sideways; tabs work by keyboard.

test.skip(({ isMobile }) => !isMobile, 'phone layout only');

test('phone: tabs for data, study and assistant; a question brings its study forward', async ({ page }) => {
  await page.goto('/overview?mode=synthetic');
  const tabs = page.getByTestId('workspace-tabs');
  await expect(tabs.getByRole('tab')).toHaveText(['Data', 'Study', 'Assistant']);
  await expect(page.getByTestId('workspace-data')).toBeVisible();
  await expect(page.getByTestId('open-assistant')).toHaveCount(0);
  // Keyboard: arrows move along the tabs.
  await tabs.getByRole('tab', { name: 'Data' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(tabs.getByRole('tab', { name: /Study/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('live-study')).toHaveAttribute('data-status', 'idle');
  await page.keyboard.press('ArrowRight');
  await expect(tabs.getByRole('tab', { name: 'Assistant' })).toHaveAttribute('aria-selected', 'true');

  await page.getByTestId('workspace-start-chat').click();
  const panel = page.getByTestId('workspace-assistant');
  await panel.getByTestId('assistant-input').fill('What is the latest electricity generation?');
  await panel.getByTestId('assistant-send').click();
  await expect(tabs.getByRole('tab', { name: /Study/ })).toHaveAttribute('aria-selected', 'true');
  const study = page.getByTestId('live-study');
  await expect(study).toHaveAttribute('data-status', 'completed');
  await expect(study.getByTestId('study-finding').first()).toContainText('50100');
  await expect(study.getByTestId('study-datasets').getByTestId('dataset')).toHaveAttribute('data-state', 'final');
  // Follow-up goes back to the assistant with the conversation kept.
  await study.getByTestId('study-follow-up').click();
  await expect(tabs.getByRole('tab', { name: 'Assistant' })).toHaveAttribute('aria-selected', 'true');
  await expect(panel.getByTestId('assistant-message')).toHaveCount(1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
