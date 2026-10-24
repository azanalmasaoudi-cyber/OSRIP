/**
 * Display formatting. Values are stored and transported unrounded; rounding
 * happens here only. Both languages use Latin digits (0–9) so that English and
 * Arabic views show visibly identical numbers (booklet UX01 / T08). This is a
 * documented design decision open to team review (see docs/SPEC_CONFLICTS.md).
 */

export type AppLanguage = 'en' | 'ar';

const LOCALES: Record<AppLanguage, string> = {
  en: 'en-GB',
  ar: 'ar-OM-u-nu-latn',
};

export function formatDecimal(
  value: string | null,
  language: AppLanguage,
  maximumFractionDigits = 2,
): string | null {
  if (value === null) return null; // caller renders an explicit "missing" label
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return new Intl.NumberFormat(LOCALES[language], {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(numeric);
}

/** Short form for axis ticks and headline figures (e.g. 48K, 40M). Display only. */
export function formatCompact(value: number, language: AppLanguage): string {
  return new Intl.NumberFormat(LOCALES[language], { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

/** A calendar date, or the date of a timestamp (e.g. 16 Oct 2026); the input itself if unreadable. */
export function formatDate(value: string, language: AppLanguage): string {
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(LOCALES[language], { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(date);
}

/** A moment in the reader's own time zone (e.g. 23 Oct 2026, 16:45); the input if unreadable. */
export function formatDateTime(value: string, language: AppLanguage): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(LOCALES[language], { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export function formatPeriod(start: string, end: string, language: AppLanguage): string {
  const s = new Date(`${start}T00:00:00Z`);
  const e = new Date(`${end}T00:00:00Z`);
  const isCalendarYear =
    start.endsWith('-01-01') && end.endsWith('-12-31') && s.getUTCFullYear() === e.getUTCFullYear();
  if (isCalendarYear) {
    return new Intl.DateTimeFormat(LOCALES[language], { year: 'numeric', timeZone: 'UTC' }).format(s);
  }
  const fmt = new Intl.DateTimeFormat(LOCALES[language], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
  // A dated statement covers one day, not a range.
  if (start === end) return fmt.format(s);
  return `${fmt.format(s)} – ${fmt.format(e)}`;
}
