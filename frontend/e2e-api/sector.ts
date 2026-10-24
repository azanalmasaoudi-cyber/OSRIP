import { expect, type Page } from '@playwright/test';

/**
 * The period-first sector workflow, as a person uses it: choose the indicator (and its
 * geography and breakdown where offered), a frequency and a start and end period from those
 * published, then press Show results. Periods are period start dates ("2002-01-01").
 */
export interface SectorChoice {
  indicator?: string;
  area?: string;
  /** Commodity, partner and flow codes joined by "|" ("SYNTH_COMMODITY|PARTNER_A|import"). */
  breakdown?: string;
  view?: 'annual' | 'quarterly' | 'monthly';
  from: string;
  to: string;
}

export async function chooseSelection(page: Page, choice: SectorChoice): Promise<void> {
  await expect(page.getByTestId('sector-form')).toBeVisible();
  if (choice.indicator) await page.getByTestId('sector-indicator').selectOption(choice.indicator);
  if (choice.area) await page.getByTestId('sector-area').selectOption(choice.area);
  if (choice.breakdown !== undefined) await page.getByTestId('sector-breakdown').selectOption(choice.breakdown);
  if (choice.view) await page.getByTestId('sector-frequency').locator(`[data-value="${choice.view}"]`).click();
  await page.getByTestId('sector-from').selectOption(choice.from);
  await page.getByTestId('sector-to').selectOption(choice.to);
}

export async function showResults(page: Page, choice: SectorChoice): Promise<void> {
  await chooseSelection(page, choice);
  await page.getByTestId('sector-show-results').click();
  await expect(page.getByTestId('sector-results')).toBeVisible();
}

/** Opens the calculations for the applied period (a closed section until asked for). */
export async function openCalculations(page: Page): Promise<void> {
  const details = page.getByTestId('sector-calculations');
  if (!(await details.evaluate((d) => (d as HTMLDetailsElement).open))) await details.locator(':scope > summary').click();
}

/** Opens the sector's reviewed notes (review cards). */
export async function openReviews(page: Page): Promise<void> {
  const details = page.getByTestId('sector-reviews');
  if (!(await details.evaluate((d) => (d as HTMLDetailsElement).open))) await details.locator(':scope > summary').click();
}
