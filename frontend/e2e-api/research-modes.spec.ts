import { expect, test, type Page } from '@playwright/test';

import { ask, closeDrawer, openChatSettings, openTools } from './chat';

// The three answer modes through the real stack, with the backend's scripted stand-ins for the
// model, web search and image service (nothing leaves the machine, nothing is billed):
// Quick answer, Deep internet research (plan, parallel searches, a calculation, a table checked
// against its sources, a chart of that table, a diagram and the report's sections), the same in
// Arabic, and an illustration made only for a signed-in person, labelled as not data.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}-${test.info().project.name}.png`, fullPage: true });
}

async function chooseMode(page: Page, name: string): Promise<void> {
  await openTools(page);
  await page.getByTestId('assistant-mode').getByRole('radio', { name, exact: true }).click();
  await closeDrawer(page);
}

test('the Tools drawer groups the internet modes apart from the data modes', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await openTools(page);
  const modes = page.getByTestId('assistant-mode');
  await expect(modes.locator('[data-group="web"] [role="radio"]')).toHaveText(['Quick answer', 'Deep research']);
  await expect(modes.locator('[data-group="data"] [role="radio"]')).toHaveText(['Data analysis', 'Ask', 'Compare', 'Scenario']);
  await modes.getByRole('radio', { name: 'Deep research' }).click();
  await expect(page.getByTestId('assistant-mode-hint')).toContainText('OSRIP’s datasets are not used unless you ask for them');
  await modes.getByRole('radio', { name: 'Quick answer' }).click();
  await expect(page.getByTestId('assistant-mode-hint')).toContainText('one or two web searches');
});

test('Deep research writes a planned, structured report with checked tables, a chart and a diagram', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await chooseMode(page, 'Deep research');
  const reply = await ask(page, 'Write a report on electricity generation in 2023');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-mode')).toHaveText('Deep internet research');
  const text = reply.getByTestId('assistant-text');
  for (const heading of ['Summary', 'Findings', 'Opportunities and risks', 'Recommendations', 'Limitations and missing information']) {
    await expect(text.getByRole('heading', { name: heading })).toBeVisible();
  }
  // The table: two rows, each checked against its source; sources only on request.
  const table = reply.getByTestId('research-table');
  await expect(table).toHaveAttribute('data-rows', '2');
  await expect(table.getByTestId('research-table-row').first()).toContainText('41,234');
  await expect(table.getByRole('columnheader', { name: 'Sources' })).toHaveCount(0);
  await reply.getByTestId('toggle-sources').click();
  await expect(table.getByRole('columnheader', { name: 'Sources' })).toBeVisible();
  const [csv] = await Promise.all([page.waitForEvent('download'), table.getByTestId('research-table-csv').click()]);
  expect(csv.suggestedFilename()).toMatch(/^osrip-rt1-\d+-en\.csv$/);
  // The chart is drawn from that table; the diagram has its four steps; the plan is listed.
  const chart = reply.getByTestId('research-chart');
  await expect(chart).toHaveAttribute('data-chart', 'bar');
  await expect(chart).toHaveAttribute('data-table', 'RT1');
  await expect(chart.locator('rect[data-point]')).toHaveCount(2);
  const diagram = reply.getByTestId('research-diagram');
  await expect(diagram).toHaveAttribute('data-nodes', '4');
  await expect(diagram.locator('[data-edge]')).toHaveCount(3);
  const [svg] = await Promise.all([page.waitForEvent('download'), diagram.getByTestId('research-diagram-svg').click()]);
  expect(svg.suggestedFilename()).toMatch(/^osrip-d1-\d+\.svg$/);
  await expect(reply.getByTestId('research-plan')).toHaveAttribute('data-questions', '2');
  // A guest gets no illustration (and none was asked for).
  await expect(reply.getByTestId('generated-image')).toHaveCount(0);
  await snap(page, 'deep-research-report-en');

  // At phone width the report fits without horizontal scrolling of the page.
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  // The flowchart runs top to bottom in the narrow card, so its labels stay readable.
  await expect(diagram).toHaveAttribute('data-layout', 'narrow');
  await diagram.scrollIntoViewIfNeeded();
  await snap(page, 'deep-research-report-phone');
});

test('a Quick answer searches the web and answers briefly', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await chooseMode(page, 'Quick answer');
  const reply = await ask(page, 'web electricity generation 2023');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-mode')).toHaveText('Quick answer');
  await expect(reply.getByTestId('research-plan')).toHaveCount(0);
});

test('the report in Arabic, right to left', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await openChatSettings(page);
  await page.getByTestId('assistant-language').getByRole('radio', { name: 'العربية' }).click();
  await closeDrawer(page);
  await chooseMode(page, 'بحث معمّق');
  const reply = await ask(page, 'اكتب تقريرا عن توليد الكهرباء في 2023');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  await expect(reply.getByTestId('reply-mode')).toHaveText('بحث معمّق على الإنترنت');
  await expect(reply.getByTestId('assistant-text').getByRole('heading', { name: 'الملخص' })).toBeVisible();
  await expect(reply.getByTestId('research-table').getByRole('columnheader').first()).toHaveText('المصدر');
  await expect(reply.getByTestId('research-diagram').locator('[data-node="generation"]')).toContainText('التوليد');
  // Counts in Arabic wording (no fallback to English plurals).
  await expect(reply.getByTestId('research-plan').locator('summary')).toContainText('عدد الأسئلة: 2');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await snap(page, 'deep-research-report-ar');
});

test('an illustration is made for a signed-in person, labelled as not data', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByTestId('sign-in-form').getByLabel('Username').fill('e2eviewer');
  await page.getByTestId('sign-in-form').getByLabel('Password').fill(PASSWORD);
  await page.getByTestId('sign-in-form').getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('account-page')).toBeVisible();
  await page.goto('/assistant?mode=synthetic');
  await chooseMode(page, 'Deep research');
  const reply = await ask(page, 'Write a report on electricity generation with an illustration');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  const image = reply.getByTestId('generated-image');
  await expect(image).toHaveCount(1);
  await expect(image.getByTestId('generated-image-label')).toHaveText('AI illustration — not data');
  // The picture loads from the server (the stand-in draws one; nothing is billed).
  await expect.poll(() => image.locator('img').evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(0);
  await snap(page, 'deep-research-illustration');
});
