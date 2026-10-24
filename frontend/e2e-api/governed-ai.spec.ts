import { expect, test, type Page } from '@playwright/test';

import { closeDrawer, openTools } from './chat';

// The governed AI and research service through the real stack (scripted providers, no
// network): every source states its data status; one search route by default, a second only
// as a fallback after a failure or as a cross-check the person asks for; Google-style grounded
// results shown verbatim apart from the answer; and the provider-readiness view for
// administrators, which names missing settings and never shows a key.

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';

async function ask(page: Page, question: string) {
  const before = await page.getByTestId('assistant-message').count();
  await page.getByTestId('assistant-input').fill(question);
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message')).toHaveCount(before + 1);
  const reply = page.getByTestId('assistant-message').last();
  await expect(reply).not.toHaveAttribute('data-status', '');
  return reply;
}

test('every source states its data status; approved data come first for numbers', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'What is the latest electricity generation?');
  await expect(reply).toHaveAttribute('data-status', 'answered');
  const citation = reply.getByTestId('citation').first();
  // Synthetic mode: demonstration data, never presented as approved official statistics.
  await expect(citation.getByTestId('data-status')).toHaveAttribute('data-status', 'synthetic_demonstration');
  await expect(reply.locator('[data-testid="data-status"][data-status="approved_official"]')).toHaveCount(0);
  await expect(reply.getByTestId('reply-method')).toContainText('Answered by: Scripted test provider');

  const web = await ask(page, 'web electricity generation 2023');
  await expect(web.getByTestId('web-citation').first().getByTestId('data-status')).toHaveText('Unreviewed external evidence');
  await expect(web.getByTestId('reply-method')).toContainText('OSRIP’s published data were checked before any web search');
  // One route only: no fallback, no cross-check, no grounded panel.
  await expect(web.getByTestId('search-log').locator('li[data-role="primary"]').first()).toHaveAttribute('data-provider', 'fake-search');
  await expect(web.getByTestId('search-log').locator('li[data-role="cross_check"], li[data-role="fallback"]')).toHaveCount(0);
  await expect(web.getByTestId('grounded-context')).toHaveCount(0);
});

test('the fallback route is used only after the first fails; its Google results are shown apart', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const reply = await ask(page, 'web search that will fail');
  const log = reply.getByTestId('search-log');
  await expect(log.locator('li[data-status="failed"]')).toHaveAttribute('data-provider', 'fake-search');
  const fallback = log.locator('li[data-role="fallback"]');
  await expect(fallback).toHaveAttribute('data-provider', 'fake-gemini');
  await expect(fallback).toContainText('shown below the answer, not used in it');
  const grounded = reply.getByTestId('grounded-context');
  await expect(grounded).toContainText('Google Search results');
  await expect(grounded).toContainText('not used for the answer above');
  await expect(grounded.getByTestId('grounded-text')).toContainText('41,234 GWh');
  await expect(grounded.getByTestId('grounded-citations').getByRole('link')).toHaveAttribute('href', 'https://www.ncsi.gov.om/test-fixture/electricity');
  // Google's Search Suggestions: rendered as provided, in a frame that cannot run scripts.
  const frame = grounded.getByTestId('grounded-suggestions');
  await expect(frame).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox');
  await expect(page.frameLocator('[data-testid="grounded-suggestions"]').first().locator('.chip')).toContainText('Oman electricity generation 2023');
  // The answer itself does not use the grounded text, and no web figure is cited from it.
  await expect(reply.getByTestId('assistant-text')).not.toContainText('41,234');
  await expect(reply.getByTestId('web-citation')).toHaveCount(0);
});

test('Research mode offers a cross-check, off by default and labelled as not independent', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  // The answer mode and the cross-check are optional tools, in the Tools drawer.
  await openTools(page);
  await page.getByTestId('assistant-mode').getByRole('radio', { name: 'Research' }).click();
  const toggle = page.getByTestId('cross-check-toggle');
  await expect(toggle).not.toBeChecked();
  await expect(page.getByText('agreement between two AI routes is not independent evidence')).toBeVisible();
  await closeDrawer(page);

  const plain = await ask(page, 'web electricity generation 2023');
  await expect(plain.getByTestId('search-log').locator('li[data-role="cross_check"]')).toHaveCount(0);

  await openTools(page);
  await toggle.check();
  await closeDrawer(page);
  const checked = await ask(page, 'web electricity generation 2023');
  const cross = checked.getByTestId('search-log').locator('li[data-role="cross_check"]');
  await expect(cross).toHaveAttribute('data-provider', 'fake-gemini');
  await expect(cross).toContainText('Cross-check (not independent evidence)');
  await expect(checked.getByTestId('grounded-context')).toBeVisible();
  await expect(checked.getByTestId('reply-method')).toContainText('agreement between AI routes is not independent evidence');
  await expect(checked.getByTestId('reply-method')).toContainText('Google Search results shown separately and not used: 1');
});

test('provider readiness: administrators see each provider’s state and missing setting names, never keys', async ({ page }) => {
  await page.goto('/sign-in');
  const form = page.getByTestId('sign-in-form');
  await form.getByLabel('E-mail address').fill('admin@e2e.invalid');
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
  await page.goto('/admin/health');
  const view = page.getByTestId('provider-readiness');
  await expect(view).toContainText('Agreement between two models is not independent evidence');
  for (const name of ['anthropic', 'openai', 'gemini', 'brave', 'firecrawl']) {
    // No keys in the test server: every real provider is unavailable, and says why.
    await expect(view.locator(`[data-testid="provider"][data-name="${name}"]`)).toHaveAttribute('data-status', 'unavailable');
  }
  await expect(view.locator('[data-name="openai"]').getByTestId('provider-missing').first()).toContainText('OSRIP_OPENAI_API_KEY');
  await expect(view.locator('[data-name="gemini"]')).toContainText('OSRIP_GEMINI_SEARCH_MODEL');
  await expect(view.locator('[data-name="firecrawl"]')).toContainText('OSRIP_FIRECRAWL_API_KEY');
  // Nothing to test without settings: no live-test buttons for unavailable capabilities.
  await expect(view.locator('[data-testid^="provider-test-"]')).toHaveCount(0);
  await expect(page.getByTestId('provider-routing')).toHaveText('Answering: fake · Web search: fake → fake-gemini');
  await expect(view).toContainText('A subscription to a consumer chat service is not API access');
});
