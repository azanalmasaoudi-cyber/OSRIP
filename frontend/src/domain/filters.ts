import { PERIOD_KINDS, type Frequency, type Series, type TradeFlow } from './types';

/**
 * Selection only. These helpers choose which series to show; they never derive
 * new values (business calculations live in the backend domain layer).
 */

export const ALL = 'all' as const;
export const NATIONAL_TOTAL = 'total' as const;

export const TRADE_FLOWS: readonly TradeFlow[] = ['import', 'domestic_export', 're_export'];

export const DISPLAY_OPTIONS = ['chart', 'table'] as const;
export type DisplayOption = (typeof DISPLAY_OPTIONS)[number];

export interface SeriesFilter {
  indicator?: string;
  flow?: string;
  /** `all`, `total` (partnerCode null) or a partner code. */
  partner?: string;
  commodity?: string;
  /** Area code of the series itself (national, a governorate or a wilayat); never aggregated. */
  area?: string;
  /** ISO dates, same semantics as the API: period_end >= from, period_start <= to. */
  periodFrom?: string;
  periodTo?: string;
}

export function filterSeries(series: readonly Series[], filter: SeriesFilter): Series[] {
  return series
    .map((s) => ({
      ...s,
      observations: s.observations.filter(
        (o) => (!filter.periodFrom || o.periodEnd >= filter.periodFrom) && (!filter.periodTo || o.periodStart <= filter.periodTo),
      ),
    }))
    .filter((s) => s.observations.length > 0)
    .filter((s) => {
    if (filter.indicator && filter.indicator !== ALL && s.indicatorCode !== filter.indicator) return false;
    if (filter.flow && filter.flow !== ALL && s.flow !== filter.flow) return false;
    if (filter.partner && filter.partner !== ALL) {
      if (filter.partner === NATIONAL_TOTAL ? s.partnerCode !== null : s.partnerCode !== filter.partner) return false;
    }
    if (filter.commodity && filter.commodity !== ALL && s.commodityCode !== filter.commodity) return false;
    if (filter.area && filter.area !== ALL && (s.area?.code ?? 'OM') !== filter.area) return false;
    return true;
  });
}

/** Distinct values in first-seen order, for building filter options from the data. */
export function distinct<T>(values: Iterable<T | null>): T[] {
  const seen: T[] = [];
  for (const v of values) if (v !== null && !seen.includes(v)) seen.push(v);
  return seen;
}

export function seriesKey(s: Series): string {
  // The source too: two sources can publish the same indicator, area and period kind in one
  // reference-pack version (each is its own series and card).
  return `${s.indicatorCode}_${s.area?.code ?? 'OM'}_${s.frequency ?? ''}_${s.ytdEndMonth ?? ''}_${s.flow ?? ''}_${s.partnerCode ?? ''}_${s.commodityCode ?? ''}_${s.source.versionLabel}_${s.source.sourceCode ?? s.source.title}`;
}

/**
 * Series listed by period kind (full years, year-to-date totals, quarters, months, dated
 * statements, then any without a stated kind), so a year-to-date total is never shown among
 * full years. Empty kinds are left out.
 */
export function byPeriodKind(series: readonly Series[]): { kind: Frequency | undefined; series: Series[] }[] {
  return [...PERIOD_KINDS, undefined]
    .map((kind) => ({ kind, series: series.filter((s) => s.frequency === kind) }))
    .filter((group) => group.series.length > 0);
}

/** Latest observation by period end; null if the series has none. */
export function latestObservation(s: Series) {
  const sorted = [...s.observations].sort((a, b) => a.periodEnd.localeCompare(b.periodEnd));
  return { latest: sorted.at(-1) ?? null, previous: sorted.at(-2) ?? null };
}

/**
 * Partner rows that can be shown side by side: same indicator, flow, unit and
 * a single shared period. Returns null when the rows are not comparable.
 */
export function comparablePartnerRows(series: readonly Series[]): Series[] | null {
  const partners = series.filter((s) => s.partnerCode !== null && s.observations.length === 1);
  const first = partners[0];
  const firstObs = first?.observations[0];
  if (partners.length < 2 || !first || !firstObs) return null;
  const sameShape = partners.every((s) => {
    const obs = s.observations[0];
    return (
      obs !== undefined &&
      s.indicatorCode === first.indicatorCode &&
      s.flow === first.flow &&
      s.unit.code === first.unit.code &&
      obs.periodStart === firstObs.periodStart &&
      obs.periodEnd === firstObs.periodEnd &&
      obs.periodComplete
    );
  });
  return sameShape ? partners : null;
}
