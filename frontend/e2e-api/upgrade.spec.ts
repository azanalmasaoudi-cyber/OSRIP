import { expect, test } from '@playwright/test';

// Release 0.8 through the real stack: Al Mulhim's labelled face, web research with
// labelled sources (scripted search provider, refused in production), the review queue,
// and a username account that must replace its temporary password first.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

test('the floating control is Al Mulhim, labelled as an AI assistant, in English and Arabic', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const open = page.getByTestId('open-assistant');
  await expect(open).toContainText('Al Mulhim');
  await expect(open.getByTestId('assistant-avatar').first()).toHaveAttribute('data-state', 'idle');
  await open.click();
  const identity = page.getByTestId('assistant-identity');
  await expect(identity).toContainText('AI assistant');
  await expect(identity).not.toContainText('not a real person'); // no long notes under the portrait
  const help = page.getByTestId('assistant-help');
  await help.locator('summary').click();
  await expect(help).toContainText('not a real person');
  await expect(help).toContainText('not lip synchronisation');
  await expect(identity.getByRole('img', { name: /generated image of a fictional Omani man/i })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'العربية' }).click();
  await expect(page.getByTestId('open-assistant')).toContainText('المُلْهِم');
  await page.getByRole('button', { name: 'English' }).click();
});

test('web research cites a labelled official source and failures are shown, not hidden', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  await page.getByTestId('open-assistant').click();
  await expect(page.getByTestId('web-toggle')).toBeChecked();
  await page.getByTestId('assistant-input').fill('Search the web for electricity generation 2023');
  await page.getByTestId('assistant-send').click();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'answered');
  const citation = reply.getByTestId('web-citation');
  await expect(citation).toHaveAttribute('data-class', 'official');
  await expect(citation.getByTestId('evidence-class')).toHaveText('Official data');
  await expect(citation.getByRole('link')).toHaveAttribute('href', /^https:\/\/www\.ncsi\.gov\.om\//);
  await expect(citation).toContainText('Date given by the search engine');
  await expect(citation).toContainText('Retrieved');
  await expect(reply.getByTestId('search-log')).toContainText('Web search');
  await expect(reply).toContainText('review queue');

  // The scripted primary route fails on "fail"; the scripted fallback route on "gemini down".
  await page.getByTestId('assistant-input').fill('web search that will fail, gemini down');
  await page.getByTestId('assistant-send').click();
  const failed = page.getByTestId('assistant-message').last();
  await expect(failed).toHaveAttribute('data-status', 'no_evidence');
  const failures = failed.getByTestId('search-log').locator('[data-status="failed"]');
  await expect(failures).toHaveCount(2);
  await expect(failures.first()).toContainText('Web search failed');
  await expect(failures.nth(1)).toHaveAttribute('data-role', 'fallback');
  await expect(failed.getByTestId('grounded-context')).toHaveCount(0);
  // Neither the failed search nor anything else was charged twice: one answer used.
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '4');
});

test('a data manager reviews web figures; accepting needs a note and publishes nothing', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username or e-mail address').fill('manager@e2e.invalid');
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
  await page.goto('/data-management');
  const queue = page.getByTestId('research-queue');
  await expect(queue).toBeVisible();
  const item = queue.getByTestId('research-candidate').first();
  await expect(item).toContainText('41,234');
  await expect(item).toContainText('National Centre for Statistics and Information');
  await expect(item.getByTestId('research-accept')).toBeDisabled();
  await item.getByLabel('Review note').fill('Checked against the NCSI bulletin table.');
  await item.getByTestId('research-accept').click();
  await queue.getByTestId('research-status').getByRole('radio', { name: 'Accepted' }).click();
  await expect(queue.getByTestId('research-candidate').first()).toHaveAttribute('data-status', 'accepted');
});

test('a username account must replace its temporary password before anything else', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('Username or e-mail address').fill('E2ETemp');
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Choose a new password to continue' })).toBeVisible();
  await page.goto('/overview');
  await expect(page.getByTestId('password-change-banner')).toBeVisible();
  await page.getByTestId('password-change-banner').getByRole('link').click();
  const change = page.getByTestId('change-password');
  await change.getByLabel('Current password').fill(PASSWORD);
  await change.getByLabel('New password').fill(`${PASSWORD}-changed`);
  await change.getByTestId('change-password-submit').click();
  await expect(page.getByTestId('account-page')).toBeVisible();
  await expect(page.getByTestId('account-username')).toHaveText('e2etemp');
  await expect(page.getByTestId('password-change-banner')).toHaveCount(0);
});
