import { expect, test, type Page } from '@playwright/test';

import { showResults } from './sector';

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

/** The conversation page: header, messages and message box, one under another, in one centred
 * column at most 800px wide; only the message list scrolls. */
async function oneColumn(page: Page): Promise<void> {
  const header = (await page.getByTestId('chat-header').boundingBox())!;
  const messages = (await page.getByTestId('assistant-messages').boundingBox())!;
  const composer = (await page.getByTestId('chat-composer').boundingBox())!;
  for (const box of [header, composer]) expect(box.width).toBeLessThanOrEqual(800.5);
  expect(header.y + header.height).toBeLessThanOrEqual(messages.y + 1);
  expect(messages.y + messages.height).toBeLessThanOrEqual(composer.y + 1);
  expect(Math.abs((header.x + header.width / 2) - (composer.x + composer.width / 2))).toBeLessThan(2);
  await expect(page.getByTestId('assistant-input')).toBeInViewport();
  const scrolling = await page.getByTestId('assistant-panel').evaluate((root) => [...root.querySelectorAll(':not(textarea)')]
    // Only what is on screen: the closed Settings and Tools drawers are not.
    .filter((e) => e.getClientRects().length > 0 && /(auto|scroll)/.test(getComputedStyle(e).overflowY))
    .map((e) => e.getAttribute('data-testid')));
  expect(scrolling).toEqual(['assistant-messages']);
  await noHorizontalScroll(page);
}

test('desktop: one centred conversation without the profile card, analysis or notes, in English and Arabic', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const language of ['English', 'العربية']) {
    await page.goto('/assistant?mode=synthetic');
    if (language === 'العربية') await page.getByRole('button', { name: 'العربية' }).first().click();
    await expect(page.getByTestId('assistant-workspace')).toHaveAttribute('data-layout', 'conversation');
    await expect(page.getByTestId('chat-greeting')).toHaveText(language === 'English' ? 'How can I help you?' : 'كيف يمكنني مساعدتك؟');
    await expect(page.getByTestId('suggestion')).toHaveCount(3);
    await expect(page.getByTestId('assistant-input')).toHaveAttribute('placeholder', language === 'English' ? 'Ask your question…' : 'اكتب سؤالك هنا…');
    await oneColumn(page);
    // Moved out of the conversation: the profile card, the analysis form, the results, the
    // help and voice notes, the research-mode tabs and the large allowance meter.
    for (const id of ['assistant-identity-card', 'conversation-panel']) await expect(page.getByTestId(id)).toHaveCount(0);
    for (const id of ['analysis-form', 'results-area', 'assistant-help', 'assistant-mode', 'research-brief']) {
      await expect(page.getByTestId(id)).toBeHidden();
    }
    await expect(page.getByTestId('voice-support')).toHaveCount(0);
    await expect(page.getByTestId('guest-allowance')).toHaveText(language === 'English' ? '5 of 5 free answers left' : /5/);
  }
  await page.getByRole('button', { name: 'English' }).first().click();
});

test('phone: header, conversation and message box in one column without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/assistant?mode=synthetic');
  await oneColumn(page);
});

test('when the answer service fails, the reply is a data-based report, labelled, uncharged and retryable', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  // A question without a topic (and nothing earlier to take one from): the missing information
  // and next steps, no figures.
  await page.getByTestId('assistant-input').fill('please fail');
  await page.getByTestId('assistant-send').click();
  const vague = page.getByTestId('assistant-message').last();
  await expect(vague.getByTestId('data-report-missing')).toBeVisible();
  await expect(vague.getByTestId('data-report-next')).toBeVisible();
  await expect(vague.getByTestId('assistant-text')).not.toContainText(/\d/);

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
  await reply.scrollIntoViewIfNeeded();
  await snap(page, 'data-report-reply');
});

test('a sector page: period first, then the table, the chart only on request, in time order, with a CSV', async ({ page }) => {
  await page.goto('/energy/electricity?mode=synthetic');
  // Before a period is chosen: the explanation and the selectors, no figures and no chart.
  await expect(page.getByTestId('sector-form')).toBeVisible();
  await expect(page.getByTestId('sector-results')).toHaveCount(0);
  await expect(page.getByTestId('series-chart')).toHaveCount(0);
  await snap(page, 'sector-choose');
  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  await expect(page.getByTestId('applied-range')).toHaveText('2001 – 2002');
  await expect(page.getByTestId('sector-summary')).toBeVisible();
  const table = page.getByTestId('series-table');
  await expect(table).toBeVisible();
  await expect(page.getByTestId('series-chart')).toHaveCount(0); // hidden until asked for
  await snap(page, 'sector-results');
  const periods = await table.getByTestId('series-row').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-period') ?? ''));
  expect([...periods].sort()).toEqual(periods); // time order, not alphabetical labels
  await page.getByTestId('sector-show-chart').click();
  const chart = page.getByTestId('series-chart');
  await expect(chart).toBeVisible();
  const id = await chart.getAttribute('data-dataset-id');
  expect(id).toBeTruthy();
  await expect(table).toHaveAttribute('data-dataset-id', id!); // the same rows
  await snap(page, 'sector-chart');
  await page.getByTestId('sector-hide-chart').click();
  await expect(page.getByTestId('series-chart')).toHaveCount(0);
  await expect(page.getByTestId('series-csv')).toHaveAttribute('href', /\/series\/timeline\.csv\?.*indicator=.*period_from=2001-01-01/);
  const csv = await page.request.get((await page.getByTestId('series-csv').getAttribute('href'))!);
  expect(csv.status()).toBe(200);
  expect(await csv.text()).toContain(`dataset_id=${id}`);
  // Arabic labels for the same results.
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.getByTestId('sector-results')).toContainText('جدول البيانات');
  await expect(page.getByTestId('sector-show-chart')).toHaveText('إظهار الرسم البياني');
  await snap(page, 'sector-results-ar');
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
