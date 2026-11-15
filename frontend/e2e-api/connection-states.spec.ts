import { expect, test, type Page, type Route } from '@playwright/test';

// What every page says when it cannot get data, against the real API: a static host answering in
// the API's place (the published Vercel site has no API behind it), the database down, a gateway
// error, and nobody signed in. The failures are imitated by answering the API requests here; the
// last test lets them through to the real API again and checks that Try again recovers.

const NO_FAILURE_TEXT = /Data unavailable|Something went wrong|The page could not be found|Authorized access only/;

/** Vercel's answer for /api/v1/... on the static site, byte for byte as seen on osrip.vercel.app. */
async function vercelNotFound(route: Route): Promise<void> {
  await route.fulfill({
    status: 404,
    contentType: 'application/json',
    headers: { 'x-vercel-error': 'NOT_FOUND', 'x-vercel-id': 'bom1::e2e', server: 'Vercel' },
    body: '{"error": {"code": "404", "message": "The page could not be found"}}',
  });
}

async function databaseDown(route: Route): Promise<void> {
  await route.fulfill({
    status: 503,
    contentType: 'application/json',
    headers: { 'x-request-id': 'e2e', 'x-osrip-api': '0.8.0' },
    body: JSON.stringify({ error: { code: 'database_unavailable', message: 'The data store is not available. Published snapshots cannot be read right now.' } }),
  });
}

async function gatewayDown(route: Route): Promise<void> {
  await route.fulfill({ status: 502, contentType: 'text/plain', body: 'Bad Gateway' });
}

async function answerApiWith(page: Page, handler: (route: Route) => Promise<void>): Promise<void> {
  await page.route('**/api/v1/**', handler);
}

test('no API behind the site (Vercel’s 404): every page says the server is not connected, never “Data unavailable”', async ({ page }) => {
  await answerApiWith(page, vercelNotFound);
  await page.goto('/');
  const banner = page.getByTestId('connection-banner');
  await expect(banner).toHaveAttribute('data-problem', 'not_connected');
  await expect(banner).toContainText('Not connected to the OSRIP server');
  // The headline cards name the reason instead of a missing value.
  const cards = page.getByTestId('latest-card');
  await expect(cards).toHaveCount(4);
  await expect(cards.first().locator('[data-problem="not_connected"]')).toHaveText('Server not connected');
  await expect(page.locator('main')).not.toContainText(NO_FAILURE_TEXT);

  for (const path of ['/energy/electricity', '/geography', '/forecasts', '/reports', '/sources', '/datasets', '/data-management']) {
    await page.goto(path);
    await expect(banner).toHaveAttribute('data-problem', 'not_connected');
    const panel = page.locator('main [data-state="error"][data-problem="not_connected"]').first();
    await expect(panel, path).toBeVisible();
    await expect(panel.getByTestId('state-title')).toHaveText('Not connected to the OSRIP server');
    await expect(page.locator('main'), path).not.toContainText(NO_FAILURE_TEXT);
  }
  // Signed-in pages: a failed account check is not "authorized access only".
  for (const path of ['/admin/health', '/admin/users', '/admin/audit', '/account']) {
    await page.goto(path);
    await expect(page.locator('main [data-problem="not_connected"]').first(), path).toBeVisible();
    await expect(page.locator('main'), path).not.toContainText(NO_FAILURE_TEXT);
  }
  // Al Mulhim does not claim to be ready.
  await page.goto('/assistant');
  await expect(page.getByTestId('chat-state')).toHaveAttribute('data-problem', 'not_connected');
  await expect(page.getByTestId('chat-state')).toHaveText('Server not connected');
});

test('Arabic: the same explanations in Arabic', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('osrip.language', 'ar'));
  await answerApiWith(page, vercelNotFound);
  await page.goto('/energy/water');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('connection-banner')).toContainText('غير متصل بخادم OSRIP');
  await expect(page.locator('main [data-problem="not_connected"]').first().getByTestId('state-title')).toHaveText('غير متصل بخادم OSRIP');
  await expect(page.locator('main')).not.toContainText(/البيانات غير متاحة|حدث خطأ|للدخول المخوّل فقط/);
});

test('database unavailable and a gateway error are told apart from a missing server', async ({ page }) => {
  await answerApiWith(page, databaseDown);
  await page.goto('/');
  await expect(page.getByTestId('connection-banner')).toHaveAttribute('data-problem', 'database_unavailable');
  await expect(page.getByTestId('latest-card').first().locator('[data-problem="database_unavailable"]')).toHaveText('Database unavailable');
  await page.goto('/trade');
  await expect(page.locator('main [data-problem="database_unavailable"]').first().getByTestId('state-title')).toHaveText('The OSRIP database is unavailable');
  await expect(page.locator('main [data-problem="database_unavailable"]').first().getByTestId('state-retry')).toBeVisible();

  await page.unroute('**/api/v1/**');
  await answerApiWith(page, gatewayDown);
  await page.goto('/energy/electricity');
  await expect(page.getByTestId('connection-banner')).toHaveAttribute('data-problem', 'server_unavailable');
  await expect(page.locator('main [data-problem="server_unavailable"]').first().getByTestId('state-title')).toHaveText('The OSRIP server is not responding');
});

test('Try again recovers once the server answers again, and the pages load their data', async ({ page }) => {
  await answerApiWith(page, gatewayDown);
  await page.goto('/?mode=synthetic');
  const banner = page.getByTestId('connection-banner');
  await expect(banner).toHaveAttribute('data-problem', 'server_unavailable');
  await page.unroute('**/api/v1/**'); // the real API answers again
  await page.getByTestId('connection-retry').click();
  await expect(banner).toHaveCount(0);
  await expect(page.getByTestId('latest-card').first().getByTestId('kpi-value')).toBeVisible();
});

test('signed out: account and administration pages ask for a sign-in, with a link to it', async ({ page }) => {
  await page.goto('/account');
  await expect(page.locator('main [data-state="sign_in_required"]')).toContainText('Sign in to continue');
  for (const path of ['/admin/health', '/admin/users', '/admin/audit']) {
    await page.goto(path);
    const panel = page.locator('main [data-state="sign_in_required"]');
    await expect(panel, path).toContainText('Sign in to continue');
    await panel.getByTestId('state-sign-in').click();
    await expect(page).toHaveURL(/\/sign-in/);
  }
  await expect(page.getByTestId('connection-banner')).toHaveCount(0); // the real API is fine
});
