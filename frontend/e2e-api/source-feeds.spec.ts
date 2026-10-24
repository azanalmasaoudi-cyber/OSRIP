import { expect, test, type Page } from '@playwright/test';

// Official statistics feeds through the real API (no request leaves for the publisher here:
// the bulletin feed is never checked in this test). The public status keeps the last successful
// check, the latest release and the latest observation apart; administrators switch the daily
// schedule on and off; the portal that needs access is reported as such and cannot be enabled.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

test('the Sources page shows each feed with its three moments kept apart', async ({ page }) => {
  await page.goto('/sources');
  const bulletin = page.locator('[data-testid="public-feed"][data-feed="ncsi-monthly-bulletin"]');
  await expect(bulletin).toContainText('Monthly Statistical Bulletin');
  await expect(bulletin.getByTestId('feed-last-success')).toContainText('Last successful check');
  await expect(bulletin.getByTestId('feed-latest-release')).toContainText('Latest release found');
  await expect(bulletin.getByTestId('feed-latest-observation')).toContainText('Latest observation period');
  const portal = page.locator('[data-testid="public-feed"][data-feed="ncsi-data-portal"]');
  await expect(portal).toContainText('Needs access OSRIP does not have');
  await expect(portal).toContainText('HTTP 403');
});

test('an administrator schedules the bulletin check; the portal cannot be enabled', async ({ page }) => {
  await signIn(page, 'admin@e2e.invalid');
  await page.goto('/data-management');
  const panel = page.getByTestId('source-feeds-admin');
  await expect(panel).toBeVisible();
  const bulletin = panel.locator('[data-testid="feed-admin"][data-feed="ncsi-monthly-bulletin"]');
  const enabled = bulletin.getByTestId('feed-enabled');
  await expect(enabled).not.toBeChecked();
  await enabled.check();
  await expect(enabled).toBeChecked();
  await expect(bulletin).toContainText('Next check:');
  await expect(bulletin).toContainText('python -m app.worker');
  await expect(bulletin.getByTestId('feed-auto-publish')).not.toBeChecked(); // off by default
  await enabled.uncheck();
  await expect(enabled).not.toBeChecked();

  // The portal: no schedule controls; a manual check reports it as not accessible.
  const portal = panel.locator('[data-testid="feed-admin"][data-feed="ncsi-data-portal"]');
  await expect(portal.getByTestId('feed-enabled')).toHaveCount(0);
  await portal.getByTestId('feed-check-now').click();
  await expect(portal.getByTestId('feed-result')).toHaveAttribute('data-status', 'not_accessible');
  await expect(portal.getByTestId('feed-result')).toContainText('403');
});

test('a viewer cannot see or change the feeds in Data Management', async ({ page }) => {
  await signIn(page, 'viewer@e2e.invalid');
  await page.goto('/data-management');
  await expect(page.getByTestId('source-feeds-admin')).toHaveCount(0);
  await expect(page.locator('[data-state="restricted"]')).toBeVisible();
});
