import { expect, test } from '@playwright/test';

test('direct links bypass the entrance; workspace navigation remains bilingual @mobile', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('osrip.intro.autoplay')); // the introduction switched on
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/workspace?mode=synthetic');
  await expect(page.getByRole('heading', { name: 'Choose your next step' })).toBeVisible();
  await page.getByRole('button', { name: 'العربية', exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole('heading', { name: 'اختر خطوتك التالية' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await page.getByRole('link', { name: /تحقّق من المصادر/ }).click();
  await expect(page).toHaveURL(/sources\?mode=synthetic/);
  expect(errors).toEqual([]);
});

test('research briefs cover each domain and language within the existing message limit', async ({ page }) => {
  await page.goto('/overview');
  const result = await page.evaluate(async () => {
    // Vite serves the actual source module under test.
    // @ts-expect-error browser-only Vite module URL
    const m = await import('/src/lib/researchBrief.ts');
    return ['ar', 'en'].flatMap(language => m.BRIEF_DOMAINS.flatMap((domain: string) =>
      m.BRIEF_GOALS.map((goal: string) => ({ language, text: m.buildResearchBrief(language, domain, goal) }))));
  });
  expect(result).toHaveLength(32);
  for (const item of result) {
    expect(item.text.length).toBeLessThanOrEqual(1000);
    expect(item.text).toContain(item.language === 'ar' ? '٢٠٢١' : '2021'); // the verified scope starts in 2021
    expect(item.text).toContain(item.language === 'ar' ? 'المراجع' : 'source links');
  }
});

const loaded = (img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0);

test('the portrait loads; a missing one shows the AI badge in the same box @mobile', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  // The conversation header: Al Mulhim's portrait, and no persona choice (one persona).
  const identity = page.getByTestId('chat-header');
  await expect(identity.getByTestId('persona-picker')).toHaveCount(0);
  const portrait = identity.getByTestId('assistant-avatar').locator('img');
  await expect(portrait).toHaveAttribute('src', /mulhim-portrait-432\.jpg$/);
  await expect.poll(() => portrait.evaluate(loaded)).toBeGreaterThan(0);
  const box = await portrait.boundingBox();

  // A copy shared without the portrait: the badge takes its place, same size and shape.
  await page.route(/\/images\/assistant\/mulhim-/, (route) => route.fulfill({ status: 404, body: '' }));
  await page.reload();
  const fallback = page.getByTestId('chat-header').getByTestId('assistant-avatar').locator('img');
  await expect(fallback).toHaveAttribute('data-testid', 'persona-image-fallback');
  await expect(fallback).toHaveAttribute('alt', 'AI assistant');
  await expect.poll(() => fallback.evaluate(loaded)).toBeGreaterThan(0); // the badge itself renders
  const fallbackBox = await fallback.boundingBox();
  expect(fallbackBox?.width).toBeCloseTo(box?.width ?? 0, 0);
  expect(fallbackBox?.height).toBeCloseTo(box?.height ?? 0, 0);
});

test('unknown browser voices are not misrepresented as female', async ({ page }) => {
  await page.goto('/overview');
  const genders = await page.evaluate(async () => {
    // @ts-expect-error browser-only Vite module URL
    const { voiceGender } = await import('/src/lib/speech.ts');
    return ['Google العربية', 'Google UK English Female', 'Google UK English Male', 'Microsoft Abdullah Online'].map(voiceGender);
  });
  expect(genders).toEqual(['unknown', 'female', 'male', 'male']);
});
