import { expect, test, type Page } from '@playwright/test';

// Full stack: the booklet's SYNTHETIC fixtures, calculated by the API and shown in the interface.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('E-mail address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

function calc(page: Page, kind: string) {
  return page.locator(`[data-testid="calculation"][data-kind="${kind}"]`);
}

test('electricity shows growth with formula, inputs, version and limitations', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const growth = calc(page, 'percentage_change').first();
  await expect(growth.getByTestId('calc-value')).toHaveText('4.38%');
  await expect(growth.getByTestId('calc-exact')).toContainText('4.375');
  await expect(growth.getByTestId('calc-formula')).toContainText('100 × (current − previous) ÷ previous');
  await expect(growth.getByTestId('calc-inputs')).toContainText('fixtures-v1');
  await expect(growth.getByTestId('calc-inputs')).toContainText('48,000');
  await expect(calc(page, 'absolute_change').first().getByTestId('calc-value')).toContainText('2,100');
  // Generation is not consumption: no per-subscriber figure is derived from it.
  await expect(calc(page, 'use_per_subscriber')).toContainText('generation is not consumption');
  const series = page.getByTestId('series-card').first();
  await expect(series.getByTestId('series-limitation')).toContainText('not consumption');
  await expect(series.getByTestId('series-geography')).toHaveText('Oman (national)');
});

test('water keeps leakage and source composition unavailable, with reasons', async ({ page }) => {
  await page.goto('/energy/water?mode=synthetic');
  await expect(calc(page, 'percentage_change').first().getByTestId('calc-value')).toHaveText('3.94%');
  const declined = calc(page, 'not_calculated');
  await expect(declined).toHaveCount(2);
  await expect(declined.first().getByTestId('calc-reason')).toContainText('not calculated as leakage');
  await expect(declined.nth(1).getByTestId('calc-reason')).toContainText('No breakdown of production by water source');
});

test('food shows the balance, both contributions and why they do not sum to 100%', async ({ page }) => {
  await page.goto('/food-security?mode=synthetic');
  const availability = calc(page, 'apparent_availability');
  await expect(availability.getByTestId('calc-value')).toHaveText('160,000 tonne');
  await expect(availability.getByTestId('calc-formula')).toContainText('stock change = 0 (declared assumption)');
  await expect(availability.getByTestId('calc-caveats')).toContainText('declared assumption');
  await expect(calc(page, 'local_production_contribution').getByTestId('calc-value')).toHaveText('62.5%');
  await expect(calc(page, 'local_production_contribution').getByTestId('calc-caveats'))
    .toContainText('not a complete food-security assessment');
  const gross = calc(page, 'gross_import_contribution');
  await expect(gross.getByTestId('calc-value')).toHaveText('50%');
  await expect(gross.getByTestId('calc-notes')).toContainText('62.5% + 50% = 112.5%');

  // The stock-assumption filter changes the calculation and the export link together.
  await page.getByTestId('filter-stock').selectOption('unknown');
  await expect(page).toHaveURL(/stock=unknown/);
  await expect(availability.getByTestId('calc-caveats')).toContainText('not adjusted for stocks');
  await expect(page.getByTestId('export-calculations').first()).toHaveAttribute('href', /stock_assumption=unknown/);
});

test('trade shows shares, balance and unit values without profit or retail wording', async ({ page }) => {
  await page.goto('/trade?mode=synthetic');
  const shares = calc(page, 'largest_partner_share');
  await expect(shares.getByTestId('calc-value')).toHaveText('60%');
  await expect(shares.getByTestId('calc-breakdown')).toContainText('Partner A (fictional)');
  await expect(shares.getByTestId('calc-breakdown')).toContainText('25%');
  await expect(shares.getByTestId('calc-breakdown')).toContainText('15%');
  const balance = calc(page, 'trade_balance');
  await expect(balance.getByTestId('calc-value')).toContainText('-28,000,000');
  await expect(balance.getByTestId('calc-caveats')).toContainText('It is not a profit or loss');
  const unitValues = calc(page, 'unit_value');
  await expect(unitValues.first().getByTestId('calc-value')).toContainText('500');
  await expect(unitValues.nth(1).getByTestId('calc-value')).toContainText('600');
  await expect(unitValues.first().getByTestId('calc-caveats')).toContainText('not a retail or consumer price');
});

test('filters narrow calculations, tables and exports consistently', async ({ page, request }) => {
  await page.goto('/trade?mode=synthetic&commodity=WHEAT');
  await expect(page.getByTestId('calculations')).toHaveCount(0);
  await expect(page.locator('[data-state="empty"]').first()).toBeVisible();
  const href = await page.getByTestId('export-observations').first().getAttribute('href');
  expect(href).toContain('commodity=WHEAT');
  const csv = await (await request.get(href ?? '')).text();
  expect(csv).toContain('SYNTHETIC DEMONSTRATION DATA');
  expect(csv).not.toContain('SYNTH_COMMODITY');
});

test('an analyst runs the rules, reviews a card and freezes a report', async ({ page }) => {
  await signIn(page, 'analyst@e2e.invalid');
  await page.goto('/trade?mode=synthetic');
  await page.getByTestId('run-rules').click();
  const card = page.locator('[data-testid="review-card"][data-rule="R02"]').first();
  await expect(card.getByTestId('card-observation')).toContainText('supplies 60%');
  await expect(card.getByTestId('card-next')).toContainText('not a probability of disruption');
  await expect(card.getByTestId('card-status')).toHaveText('Open');

  const form = card.getByTestId('review-form');
  await form.getByLabel('New status').selectOption('explained');
  await form.getByLabel('Reason').fill('Fictional partners in a demonstration fixture.');
  await form.getByRole('button', { name: 'Save review' }).click();
  await expect(card.getByTestId('review-history')).toContainText('Fictional partners in a demonstration fixture.');
  await expect(card.getByTestId('card-status')).toHaveText('Explained');

  // Freeze the food view with an explicit assumption and open the print view.
  await page.goto('/food-security?mode=synthetic&stock=unknown');
  await page.getByTestId('save-report').click();
  await page.getByTestId('save-report-form').getByRole('button', { name: 'Create report' }).click();
  await page.getByTestId('open-new-report').click();
  const report = page.getByTestId('report');
  await expect(report.getByTestId('report-label')).toContainText('SYNTHETIC DEMONSTRATION DATA');
  await expect(report.getByTestId('report-assumptions')).toContainText('stock_assumption=unknown');
  await expect(report.getByTestId('report-sources')).toContainText('fixtures-v1');
  await expect(report.locator('[data-kind="apparent_availability"] [data-testid="calc-value"]')).toHaveText('160,000 tonne');
  await expect(report.getByTestId('report-export')).toHaveAttribute('href', /\/reports\/.+\/export\.csv$/);
});

test('a viewer sees the cards but cannot run rules, review or save reports', async ({ page }) => {
  await signIn(page, 'viewer@e2e.invalid');
  await page.goto('/trade?mode=synthetic');
  await expect(page.getByTestId('review-cards')).toBeVisible();
  await expect(page.getByTestId('run-rules')).toHaveCount(0);
  await expect(page.getByTestId('save-report')).toHaveCount(0);
  await expect(page.getByTestId('review-form')).toHaveCount(0);
});
