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
    expect(item.text).toContain(item.language === 'ar' ? '٢٠٢٢' : '2022');
    expect(item.text).toContain(item.language === 'ar' ? 'المراجع' : 'source links');
  }
});

const loaded = (img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0);

test('a missing persona portrait shows the AI badge in the same box and recovers when the source changes @mobile', async ({ page }) => {
  // Ilham's images cannot be loaded here, as in a copy shared without them.
  await page.route(/\/images\/assistant\/ilham-/, (route) => route.fulfill({ status: 404, body: '' }));
  await page.goto('/assistant?mode=synthetic');
  // The conversation header: the chosen persona's portrait and the Al Mulhim / Ilham switch.
  const identity = page.getByTestId('chat-header');
  const portrait = identity.getByTestId('assistant-avatar').locator('img');
  await expect.poll(() => portrait.evaluate(loaded)).toBeGreaterThan(0); // Al Mulhim's portrait loads
  const box = await portrait.boundingBox();

  await identity.getByTestId('persona-option-ilham').click();
  await expect(portrait).toHaveAttribute('data-testid', 'persona-image-fallback');
  await expect(portrait).toHaveAttribute('alt', 'AI assistant');
  await expect.poll(() => portrait.evaluate(loaded)).toBeGreaterThan(0); // the badge itself renders
  const fallbackBox = await portrait.boundingBox();
  expect(fallbackBox?.width).toBeCloseTo(box?.width ?? 0, 0);
  expect(fallbackBox?.height).toBeCloseTo(box?.height ?? 0, 0);

  // Choosing Al Mulhim again (a new source) shows his portrait.
  await identity.getByTestId('persona-option-mulhim').click();
  await expect(identity.getByTestId('assistant-avatar').getByTestId('persona-image-fallback')).toHaveCount(0);
  await expect(portrait).toHaveAttribute('src', /mulhim-portrait-432\.jpg$/);
});

test('an available Ilham portrait still loads', async ({ page }) => {
  await page.goto('/assistant?mode=synthetic');
  const identity = page.getByTestId('chat-header');
  await identity.getByTestId('persona-option-ilham').click();
  const portrait = identity.getByTestId('assistant-avatar').locator('img');
  await expect(portrait).toHaveAttribute('src', /ilham-portrait-432\.jpg$/);
  await expect.poll(() => portrait.evaluate(loaded)).toBeGreaterThan(0);
  await expect(identity.getByTestId('persona-image-fallback')).toHaveCount(0);
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
