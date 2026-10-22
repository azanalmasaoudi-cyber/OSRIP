import { expect, test, type Page } from '@playwright/test';

// The research workflow through the real stack (scripted assistant, search and speech
// providers; no external service is called): the assistant workspace layout, the data-based
// report when the answer service fails, a sector page in its fixed order with one series
// drawn as chart and table, a background study, and Settings.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('E-mail address').fill(email);
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).not.toHaveURL(/sign-in/);
}

/** With OSRIP_SCREENSHOT_DIR set, keeps a screenshot for the test report. */
async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.OSRIP_SCREENSHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}.png` });
}

async function noHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('desktop: the conversation is on the right and the portrait and results on the left, in English and Arabic', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const language of ['English', 'العربية']) {
    await page.goto('/assistant?mode=synthetic');
    if (language === 'العربية') await page.getByRole('button', { name: 'العربية' }).first().click();
    const workspace = page.getByTestId('assistant-workspace');
    await expect(workspace).toHaveAttribute('data-layout', 'conversation-right');
    const chat = await page.getByTestId('conversation-panel').boundingBox();
    const card = await page.getByTestId('assistant-identity-card').boundingBox();
    const results = await page.getByTestId('results-area').boundingBox();
    expect(chat && card && results).toBeTruthy();
    expect(chat!.x).toBeGreaterThan(card!.x + card!.width - 1); // right of the identity card
    expect(chat!.x).toBeGreaterThan(results!.x + results!.width - 1);
    expect(chat!.width).toBeGreaterThanOrEqual(400); // wide enough to read
    // The composer is visible without scrolling; no long notes under the portrait.
    await expect(page.getByTestId('assistant-input')).toBeInViewport();
    await expect(page.getByTestId('assistant-identity-card')).not.toContainText('not a real person');
    await expect(page.getByTestId('assistant-help')).not.toHaveAttribute('open', '');
    await expect(page.getByTestId('voice-support')).toBeVisible(); // a short consent label
    await noHorizontalScroll(page);
  }
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('phone: identity, conversation and results follow one another without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/assistant?mode=synthetic');
  const card = await page.getByTestId('assistant-identity-card').boundingBox();
  const chat = await page.getByTestId('conversation-panel').boundingBox();
  const results = await page.getByTestId('results-area').boundingBox();
  expect(card!.y).toBeLessThan(chat!.y);
  expect(chat!.y).toBeLessThan(results!.y);
  await noHorizontalScroll(page);
});

test('when the answer service fails, the reply is a data-based report, labelled, uncharged and retryable', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-input').fill('please fail: latest electricity generation');
  await page.getByTestId('assistant-send').click();
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).toHaveAttribute('data-status', 'data_report');
  await expect(reply.getByTestId('non-ai-label')).toHaveText('Data-based report without AI interpretation');
  await expect(reply.getByTestId('ai-label')).toHaveCount(0);
  const notice = reply.getByTestId('data-report-notice');
  await expect(notice).toContainText('nothing was written or interpreted by AI');
  await expect(notice.getByTestId('data-report-updated')).toContainText('Data last updated');
  // Figures come with their evidence and OSRIP's own calculation.
  await expect(reply.getByTestId('citation-chip').first()).toBeVisible();
  await expect(reply.getByTestId('how-calculated')).toBeVisible();
  await expect(reply.getByTestId('retry-answer')).toHaveText(/Try the AI answer again/);
  // A question without a topic gets the missing information and next steps, no figures.
  await page.getByTestId('assistant-input').fill('please fail');
  await page.getByTestId('assistant-send').click();
  const vague = page.getByTestId('assistant-message').last();
  await expect(vague.getByTestId('data-report-missing')).toBeVisible();
  await expect(vague.getByTestId('data-report-next')).toBeVisible();
  await expect(vague.getByTestId('assistant-text')).not.toContainText(/\d/);
  await reply.scrollIntoViewIfNeeded();
  await snap(page, 'data-report-reply');
});

test('a sector page: fixed order, one series as chart and table, chronological months, CSV', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  const parts = ['part-indicators', 'part-trends', 'part-table', 'part-analysis', 'part-recommendations', 'part-sources'];
  const tops: number[] = [];
  for (const part of parts) tops.push((await page.getByTestId(part).boundingBox())!.y);
  expect([...tops].sort((a, b) => a - b)).toEqual(tops);
  await expect(page.getByTestId('kpi-card').first()).toBeVisible();
  const chart = page.getByTestId('series-chart');
  const table = page.getByTestId('series-table');
  await expect(chart).toBeVisible();
  const id = await chart.getAttribute('data-dataset-id');
  expect(id).toBeTruthy();
  await expect(table).toHaveAttribute('data-dataset-id', id!); // the same rows
  const periods = await table.getByTestId('series-row').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-period') ?? ''));
  expect([...periods].sort()).toEqual(periods); // time order, not alphabetical labels
  await expect(page.getByTestId('series-csv')).toHaveAttribute('href', /\/series\/timeline\.csv\?.*indicator=/);
  const csv = await page.request.get((await page.getByTestId('series-csv').getAttribute('href'))!);
  expect(csv.status()).toBe(200);
  expect(await csv.text()).toContain(`dataset_id=${id}`);
  // Arabic month and year labels come from the same rows.
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.getByTestId('part-trends')).toContainText('الاتجاهات التاريخية');
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('create a study: it runs in the background with visible steps and ends with conclusions', async ({ page }) => {
  await signIn(page, 'analyst@e2e.invalid');
  await page.goto('/studies?mode=synthetic&create=water');
  const form = page.getByTestId('create-study');
  await expect(form.getByTestId('job-sector')).toHaveValue('water');
  await form.getByTestId('job-question').fill('Is there a water shortage, and what data are missing?');
  const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/research/jobs') && r.request().method() === 'POST');
  await form.getByTestId('job-submit').click();
  expect((await created).status()).toBe(202); // returned at once
  const job = page.getByTestId('job-view');
  await expect(job).toHaveAttribute('data-state', /succeeded|partial/, { timeout: 30_000 });
  await expect(job.getByTestId('job-steps').locator('li')).toHaveCount(8);
  await expect(job.getByTestId('job-steps').locator('[data-stage="retrieve"]')).toHaveAttribute('data-state', 'skipped');
  await expect(job.getByTestId('job-conclusion')).toBeVisible();
  await expect(job.getByTestId('job-next-steps')).toBeVisible();
  await expect(job.getByTestId('job-analysis')).toHaveAttribute('href', /analysis=/);
  await expect(page.getByTestId('my-jobs')).toContainText('water shortage');
  await job.scrollIntoViewIfNeeded();
  await snap(page, 'study-completed');
});

test('navigation and Settings: the main destinations in order, services and scheduled reports', async ({ page }) => {
  await signIn(page, 'admin@e2e.invalid');
  await page.goto('/overview?mode=synthetic');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const names = await nav.getByRole('link').allInnerTexts();
  const main = names.map((n) => n.trim()).slice(0, 8);
  expect(main).toEqual(['Overview', 'Electricity', 'Water', 'Food Security', 'Trade', 'Studies', 'Sources', 'Settings']);
  await nav.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByTestId('settings-services')).toBeVisible();
  await expect(page.getByTestId('service-answers').getByTestId('assistant-service')).toBeVisible();
  await expect(page.getByTestId('service-retrieval')).toContainText('Not configured');
  await expect(page.getByTestId('scheduler-off')).toBeVisible(); // off by default
  const schedules = page.getByTestId('settings-schedules');
  await schedules.getByTestId('schedule-name').fill('Monthly water (e2e)');
  await schedules.getByTestId('schedule-create').click();
  const row = schedules.getByTestId('schedule-row').filter({ hasText: 'Monthly water (e2e)' });
  await expect(row).toHaveAttribute('data-enabled', 'false'); // created switched off
  await row.getByTestId('schedule-toggle').click();
  await expect(row).toHaveAttribute('data-enabled', 'true');
  await schedules.scrollIntoViewIfNeeded();
  await snap(page, 'settings-schedules');
  await expect(page.getByTestId('settings-help')).toBeVisible();
  await noHorizontalScroll(page);
});
