import { expect, test, type Page } from '@playwright/test';

// The official outlook's review in Data Management, against the real API: two items staged
// for this run are pending; one is rejected (a note is needed) and one approved; only the
// approved one reaches the public outlook; decisions show their status and note. Arabic too.

test.skip(({ isMobile }) => isMobile, 'desktop layout');

const PASSWORD = process.env.OSRIP_E2E_PASSWORD ?? '';
const RUN = `${Date.now()}`;

async function signInAsManager(page: Page) {
  await page.goto('/sign-in');
  await page.getByLabel('Username').fill('e2emanager');
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('signed-in-as')).toBeVisible();
}

function item(metric: string, year: number, value: string) {
  return {
    section: 'water', metric_code: metric, metric_en: `E2E review ${metric}`, metric_ar: `مراجعة ${metric}`,
    year, value, unit: 'm3_per_day', scope_en: 'E2E zone', scope_ar: 'منطقة الاختبار', evidence_class: 'planned',
    status_note_en: 'Synthetic test item.', status_note_ar: 'بند اختبار.', source_title: 'E2E statement',
    source_publisher: 'E2E', source_url: `https://example.org/e2e-outlook-review/${RUN}`, source_locator: 'PDF p. 1',
    retrieved_on: '2026-11-25', issue_year: 2026,
  };
}

test('outlook review: pending items, a rejection needs a note, only the approved one is public', async ({ page }) => {
  await signInAsManager(page);
  const staged = await page.evaluate(async (items) => {
    const csrf = decodeURIComponent(document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='))?.split('=')[1] ?? '');
    const r = await fetch('/api/v1/outlook/batches', { method: 'POST', headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_label: 'e2e-review', items }) });
    return (await r.json()).inserted as number;
  }, [item('E2E_REVIEW_KEEP', 2030, '1000'), item('E2E_REVIEW_DROP', 2031, '2000')]);
  expect(staged).toBe(2);

  await page.goto('/data-management');
  const review = page.getByTestId('outlook-review');
  await expect(review.getByRole('heading', { name: 'Official outlook: review' })).toBeVisible();
  const card = (metric: string) => review.locator(`[data-testid="outlook-review-item"][data-metric="${metric}"]`);
  const keep = card('E2E_REVIEW_KEEP');
  const drop = card('E2E_REVIEW_DROP');
  await expect(keep).toHaveAttribute('data-status', 'pending');
  await expect(keep.locator('[data-class="planned"]')).toBeVisible();
  await expect(keep).toContainText('1,000 m³/day');
  await expect(keep).toContainText('PDF p. 1');

  // A rejection needs a reason; approval does not.
  await expect(drop.getByTestId('outlook-reject')).toBeDisabled();
  await drop.getByTestId('outlook-review-note').fill('Not in the statement (test).');
  await drop.getByTestId('outlook-reject').click();
  await keep.getByTestId('outlook-approve').click();
  await expect(card('E2E_REVIEW_KEEP')).toHaveCount(0); // decided items leave the pending list

  await review.getByTestId('outlook-review-status').getByRole('radio', { name: /Approved/ }).click();
  await expect(card('E2E_REVIEW_KEEP')).toHaveAttribute('data-status', 'approved');
  await review.getByTestId('outlook-review-status').getByRole('radio', { name: /Rejected/ }).click();
  await expect(card('E2E_REVIEW_DROP').getByTestId('outlook-review-decision')).toContainText('Not in the statement (test).');

  // The public outlook: the approved item only, without reviewers' notes.
  const pub = await page.evaluate(async () => (await (await fetch('/api/v1/outlook?section=water')).json()).items as { metric: { code: string }; review_note?: string }[]);
  const codes = pub.map((i) => i.metric.code);
  expect(codes).toContain('E2E_REVIEW_KEEP');
  expect(codes).not.toContain('E2E_REVIEW_DROP');
  expect(pub.some((i) => 'review_note' in i)).toBe(false);

  // Arabic, right to left.
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(review.getByRole('heading', { name: 'التوقعات الرسمية: المراجعة' })).toBeVisible();
  await page.getByRole('button', { name: 'English' }).first().click();
});
