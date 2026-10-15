import { expect, test } from '@playwright/test';

// Studies through the real stack: the server runs an allowlisted study from published
// synthetic observations, and the page shows its cards, chart, table, sources and
// downloads from the one stored result. The assistant's study opens at the same address.

test('a trend study runs, opens at its own address and reproduces identically', async ({ page }) => {
  await page.goto('/studies?mode=synthetic');
  await page.getByTestId('study-indicator').selectOption('ELEC_GENERATION');
  await page.getByTestId('study-run').click();
  await expect(page).toHaveURL(/\/studies\/[0-9a-f-]{36}\?mode=synthetic/);
  const view = page.getByTestId('study-view');
  await expect(view).toHaveAttribute('data-status', 'ok');
  await expect(view.getByTestId('study-row')).toHaveCount(2);
  await expect(view.getByTestId('study-card').first()).toContainText('50,100');
  await expect(view.getByTestId('study-line-chart')).toBeVisible();
  await expect(view.getByRole('link', { name: 'Download CSV' })).toHaveAttribute('href', /\/studies\/[0-9a-f-]{36}\/export\.csv\?language=en/);
  await view.getByTestId('study-sources').locator('summary').click();
  await expect(view.getByTestId('study-sources')).toContainText('S2');
  await view.getByTestId('study-reproduce').click();
  await expect(view.getByTestId('study-reproduced')).toContainText('identical result');

  // Sorting reorders rows without changing values; missing values always sort last.
  await view.getByRole('button', { name: /Sort by Period/ }).click();
  await view.getByRole('button', { name: /Sort by Period/ }).click();
  await expect(view.getByTestId('study-row').first()).toContainText('2002');
});

test('partner concentration in Arabic shows ranked shares from the server', async ({ page }) => {
  await page.goto('/studies?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await page.getByTestId('study-kind').selectOption('partner_concentration');
  await page.getByTestId('study-commodity').selectOption('SYNTH_COMMODITY');
  await page.getByTestId('study-run').click();
  const view = page.getByTestId('study-view');
  await expect(view).toHaveAttribute('data-kind', 'partner_concentration');
  await expect(view.getByTestId('study-bar-chart')).toBeVisible();
  const rows = view.getByTestId('study-row');
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText('PARTNER_A');
  await expect(rows.first()).toContainText('60');
  await expect(view.getByTestId('study-limitations')).toContainText('رموز تجريبية خيالية');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
});

test('a study the assistant used opens from its answer', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-input').fill('Run a study of electricity generation');
  await page.getByTestId('assistant-send').click();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await reply.getByTestId('reply-study-link').click();
  await expect(page).toHaveURL(/\/studies\/[0-9a-f-]{36}/);
  await expect(page.getByTestId('study-view')).toHaveAttribute('data-kind', 'trend');
});

test('an unknown study address says so', async ({ page }) => {
  await page.goto('/studies/00000000-0000-4000-8000-000000000000');
  await expect(page.getByText('This study does not exist or has been deleted.')).toBeVisible();
});
