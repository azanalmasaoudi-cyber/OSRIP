import { expect, test, type Page, type Request } from '@playwright/test';

import { BRIEF_DOMAINS, BRIEF_GOALS, BRIEF_MODE, briefDomains, buildResearchBrief } from '../src/lib/researchBrief';

import { closeDrawer, openChatSettings, openTools } from './chat';

// The research brief builder in the assistant's Tools drawer, through the real stack (scripted
// model). It only drafts: choosing a domain and goal fills the message box in the answer language,
// selects the answer mode and closes the drawer. Nothing is sent and no guest answer is used until
// the person presses Send. Runs on desktop and phone.

/** Questions sent to the assistant (guest or account), in order. */
function trackAsks(page: Page): Request[] {
  const asks: Request[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && /\/assistant\/(guest\/messages|conversations\/[^/]+\/messages)$/.test(r.url())) asks.push(r);
  });
  return asks;
}

/** The answer language is in the conversation settings. */
async function answerIn(page: Page, language: 'en' | 'ar'): Promise<void> {
  await openChatSettings(page);
  await page.getByTestId('assistant-language').getByRole('radio', { name: language === 'ar' ? 'العربية' : 'English' }).click();
  await closeDrawer(page);
}

async function useBrief(page: Page, domain: string, goal: string): Promise<void> {
  await openTools(page);
  const brief = page.getByTestId('research-brief');
  if (!(await brief.evaluate((el) => (el as HTMLDetailsElement).open))) await brief.locator('summary').click();
  await page.getByTestId('research-brief-domain').selectOption(domain);
  await page.getByTestId('research-brief-goal').selectOption(goal);
  await page.getByTestId('research-brief-use').click();
}

test('every domain and goal drafts an editable request with its answer mode, and nothing is sent until Send', async ({ page }) => {
  test.setTimeout(120_000); // 32 drafts, then one question
  const asks = trackAsks(page);
  await page.goto('/assistant?mode=synthetic');
  const allowance = page.getByTestId('guest-allowance');
  await expect(allowance).toHaveAttribute('data-remaining', '5');
  const input = page.getByTestId('assistant-input');
  const brief = page.getByTestId('research-brief');
  await expect(brief.locator('summary')).toHaveText('Build a research brief');

  for (const language of ['en', 'ar'] as const) {
    // The conversation's answer language; the interface stays in English.
    await answerIn(page, language);
    for (const domain of BRIEF_DOMAINS) {
      for (const goal of BRIEF_GOALS) {
        await useBrief(page, domain, goal);
        await expect(input).toHaveValue(buildResearchBrief(language, domain, goal));
        await expect(page.getByTestId('assistant-mode').locator(`[data-value="${BRIEF_MODE[goal]}"]`)).toHaveAttribute('aria-checked', 'true');
        await expect(page.getByTestId('chat-mode-chip')).toBeVisible(); // the chosen mode is shown above the box
        await expect(input).toBeFocused(); // the drawer closed: ready to review
        await expect(brief).not.toHaveAttribute('open', '');
      }
    }
  }
  // Thirty-two drafts later: no question sent, no answer used, no message shown.
  expect(asks).toHaveLength(0);
  await expect(allowance).toHaveAttribute('data-remaining', '5');
  await expect(page.getByTestId('assistant-message')).toHaveCount(0);

  // The draft is the person's to edit; Send sends exactly the edited text, in the selected mode.
  await answerIn(page, 'en');
  await useBrief(page, 'water', 'trend');
  await input.press('End');
  await input.pressSequentially(' Focus on Muscat.');
  const draft = `${buildResearchBrief('en', 'water', 'trend')} Focus on Muscat.`;
  await expect(input).toHaveValue(draft);
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message').last()).toHaveAttribute('data-status', /answered|no_evidence/);
  expect(asks).toHaveLength(1);
  const body = asks[0]?.postDataJSON() as { content: string; mode: string; language: string };
  expect(body).toMatchObject({ content: draft, mode: 'analyze', language: 'en' });
  await expect(allowance).toHaveAttribute('data-remaining', '4'); // charged once, on Send
  await expect(input).toHaveValue('');
});

test('in Arabic the builder is right to left, labelled in Arabic, drafts in Arabic and fits the screen', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('osrip.language', 'ar'));
  const asks = trackAsks(page);
  await page.goto('/assistant?mode=synthetic');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await openTools(page);
  const brief = page.getByTestId('research-brief');
  await brief.locator('summary').click();
  await expect(brief.locator('summary')).toHaveText('جهّز طلب دراسة متكاملة');
  await expect(brief.getByText('المحور', { exact: true })).toBeVisible();
  await expect(brief.getByText('هدف الدراسة', { exact: true })).toBeVisible();
  await expect(page.getByTestId('research-brief-domain').locator('option')).toHaveText(Object.values(briefDomains.ar));
  await expect(page.getByTestId('research-brief-use')).toHaveText('إضافة الطلب للمراجعة');
  expect(await brief.evaluate((el) => getComputedStyle(el).direction)).toBe('rtl');

  // Nothing hidden or cut off, and nothing scrolls sideways.
  const viewport = page.viewportSize();
  const box = await brief.boundingBox();
  expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(viewport?.width ?? 0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  for (const id of ['research-brief-domain', 'research-brief-goal', 'research-brief-use']) {
    await expect(page.getByTestId(id)).toBeVisible();
    expect(await page.getByTestId(id).evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  }

  await page.getByTestId('research-brief-domain').selectOption('food');
  await page.getByTestId('research-brief-goal').selectOption('scenario');
  await page.getByTestId('research-brief-use').click();
  await expect(page.getByTestId('assistant-input')).toHaveValue(buildResearchBrief('ar', 'food', 'scenario'));
  await expect(page.getByTestId('assistant-mode').locator('[data-value="scenario"]')).toHaveAttribute('aria-checked', 'true');
  expect(asks).toHaveLength(0);
  await expect(page.getByTestId('guest-allowance')).toHaveAttribute('data-remaining', '5');
});

test('the builder works by keyboard and does not trap focus', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  // Tools opens from the keyboard too.
  await page.getByTestId('chat-tools').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('chat-tools-sheet')).toBeVisible();
  const summary = page.getByTestId('research-brief').locator('summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('research-brief')).toHaveAttribute('open', '');
  await page.keyboard.press('Tab');
  await expect(page.getByTestId('research-brief-domain')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByTestId('research-brief-goal')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByTestId('research-brief-use')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('assistant-input')).toBeFocused();
  await expect(page.getByTestId('assistant-input')).toHaveValue(buildResearchBrief('en', 'electricity', 'trend'));
  // The drawer closed; focus moves back from the message box to the Tools button, not trapped.
  await expect(page.getByTestId('chat-tools-sheet')).toBeHidden();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByTestId('chat-tools')).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByTestId('chat-tools')).not.toBeFocused();
});
