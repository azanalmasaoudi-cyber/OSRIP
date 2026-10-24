import { expect, test, type Page } from '@playwright/test';

import { showResults } from './sector';

// Research and decision support through the real stack: answer modes, validated
// recommendation cards, inline citations, saved research with a downloadable brief, the
// source library, the watchlist with alerts, and the governorate comparison. The model is
// the backend's scripted test double (labelled, refused in production).

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('E-mail address').fill('viewer@e2e.invalid');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
}

test('Analyze mode shows checked recommendation cards, inline citations, and saves a brief', async ({ page }) => {
  await signIn(page);
  await page.goto('/assistant?mode=synthetic');
  const modes = page.getByTestId('assistant-mode');
  await modes.getByRole('radio', { name: 'Analyze' }).click();
  await expect(modes.getByRole('radio', { name: 'Analyze' })).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('assistant-mode-hint')).toContainText('recommendation cards');
  await page.getByTestId('assistant-input').fill('What do you recommend for electricity generation?');
  await page.getByTestId('assistant-send').click();

  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-mode')).toHaveText('Analyze');
  await expect(reply.getByTestId('recommendation-card')).toHaveCount(1);
  await expect(reply).not.toContainText('25%'); // the invented saving was withheld by the server
  await expect(reply.getByTestId('reply-withheld')).toContainText('2');
  await expect(reply.getByTestId('reply-drivers')).toContainText('Hypothesis');
  // An inline citation moves focus to the cited evidence.
  const chip = reply.getByTestId('assistant-text').getByTestId('citation-chip').first();
  const id = await chip.getAttribute('data-evidence');
  await chip.click();
  await expect(reply.locator(`[data-testid="citation"][data-evidence="${id}"]`)).toBeFocused();

  await reply.getByTestId('save-research').click();
  await expect(reply.getByTestId('research-saved')).toBeVisible();
  await reply.getByTestId('research-saved').getByRole('link').click();
  await expect(page).toHaveURL(/\/library\?.*tab=saved/);
  const item = page.getByTestId('saved-item').first();
  await expect(item).toContainText('What do you recommend for electricity generation?');
  const [download] = await Promise.all([page.waitForEvent('download'), item.getByTestId('brief-html').click()]);
  expect(download.suggestedFilename()).toMatch(/^osrip-brief-.+\.html$/);
});

test('a series can be watched, with alert rules the reader controls', async ({ page }) => {
  await signIn(page);
  await page.goto('/energy/electricity?mode=synthetic');
  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  const card = page.getByTestId('applied-period');
  await card.getByTestId('watch-series').click();
  await expect(card.getByTestId('watching')).toBeVisible();
  await expect(page.getByTestId('alert-bell')).toBeVisible();
  await page.getByTestId('alert-bell').click();
  await expect(page).toHaveURL(/tab=watch/);
  const watched = page.getByTestId('watch-item').first();
  await expect(watched).toBeVisible();
  await watched.getByRole('button', { name: 'Add alert' }).click();
  const rule = watched.getByTestId('alert-rule').first();
  await expect(rule).toHaveAttribute('data-kind', 'new_data');
  await rule.getByRole('checkbox').uncheck();
  await expect(rule).toContainText('Off');
  await watched.getByTestId('unwatch').click();
  await expect(page.getByText('You are not watching any series yet')).toBeVisible();
});

test('the source library and governorate comparison are public and keep missing apart from zero', async ({ page }) => {
  await page.goto('/library');
  await expect(page.getByRole('tab', { name: 'Source library' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('tab', { name: 'Saved research' }).click();
  await expect(page.getByTestId('library-sign-in')).toBeVisible();
  await page.goto('/geography?mode=synthetic');
  const comparison = page.getByTestId('governorate-comparison');
  await expect(comparison).toBeVisible();
  // Every row says published, missing in the source, or no published value: never a blank or a zero.
  for (const row of await comparison.getByTestId('compare-row').all()) {
    await expect(row).toHaveAttribute('data-status', /^(published|missing_in_source|no_published_value)$/);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
