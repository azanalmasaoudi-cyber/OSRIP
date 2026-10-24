import { expect, test } from '@playwright/test';

import { showResults } from './sector';

// The short spoken explanation of a sector result, through the real API with the scripted speech
// provider (a test tone, not a voice; refused in production): nothing plays before Listen; the
// transcript, Stop and the shared volume are beside it; each persona uses its own Omani voice.

test('a sector result is explained in a few spoken sentences only when asked', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (r) => { if (r.url().includes('/assistant/voice/series')) requests.push(r.url()); });
  await page.goto('/energy/electricity?mode=synthetic');
  await showResults(page, { indicator: 'ELEC_GENERATION', view: 'annual', from: '2001-01-01', to: '2002-01-01' });
  const block = page.getByTestId('sector-listen-block');
  await expect(block).toHaveAttribute('data-state', 'idle');
  expect(requests).toHaveLength(0); // no audio is requested, and nothing plays, on its own

  await block.getByTestId('sector-listen-volume').fill('40');
  const spoken = page.waitForResponse((r) => r.url().includes('/assistant/voice/series') && r.request().method() === 'POST');
  await block.getByTestId('sector-listen').click();
  const response = await spoken;
  expect(response.status()).toBe(200);
  expect(response.headers()['x-voice']).toBe('en-GB-RyanNeural'); // Al Mulhim in English
  await expect(block.getByTestId('sector-listen-transcript')).toContainText('Electricity generation for Oman (national)');
  await expect(block.getByTestId('sector-listen-transcript')).toContainText('50,100');
  await expect(block).toHaveAttribute('data-state', /playing|loading/);
  await block.getByTestId('sector-listen-stop').click();
  await expect(block).toHaveAttribute('data-state', 'idle');
  expect(await page.evaluate(() => window.localStorage.getItem('osrip.voice.volume'))).toBe('40');

  // In Arabic with Ilham: her Omani voice.
  await page.getByRole('button', { name: 'العربية' }).first().click();
  await page.goto('/assistant?mode=synthetic');
  await page.getByTestId('assistant-identity-card').getByTestId('persona-option-ilham').click();
  await page.goto('/energy/electricity?mode=synthetic');
  const arabic = page.waitForResponse((r) => r.url().includes('/assistant/voice/series') && r.request().method() === 'POST');
  await page.getByTestId('sector-listen').click();
  expect((await arabic).headers()['x-voice']).toBe('ar-OM-AyshaNeural');
  await expect(page.getByTestId('sector-listen-transcript')).toContainText('توليد الكهرباء');
  await page.getByTestId('sector-listen-stop').click();
  await page.getByRole('button', { name: 'English' }).first().click();
});
