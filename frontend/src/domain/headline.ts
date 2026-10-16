import type { useSeries } from '@/api/queries';
import type { ObservationRecord, SectionCode, Series } from './types';

/** One headline per resource; the first indicator with published national data is shown. */
export const HEADLINE: ReadonlyArray<{ section: SectionCode; indicators: readonly string[] }> = [
  { section: 'electricity', indicators: ['ELEC_GROSS_GENERATION', 'ELEC_GENERATION'] },
  { section: 'water', indicators: ['WATER_PRODUCTION', 'WATER_CONSUMPTION'] },
  { section: 'food_security', indicators: ['FISH_CAPTURE_LANDINGS', 'FOOD_PRODUCTION'] },
  { section: 'trade', indicators: ['TRADE_MERCH_EXPORTS', 'TRADE_VALUE'] },
];

export type SeriesQuery = ReturnType<typeof useSeries>;

/** The most recent national value of the first available indicator, from full years and
 * year-to-date totals (the home page's latest figures and the workspace's resource cards). */
export function latestOf(queries: readonly SeriesQuery[], indicators: readonly string[]): { series: Series; obs: ObservationRecord } | null {
  const all = queries.flatMap((q) => (q.data?.status === 'ok' ? q.data.series : []));
  for (const code of indicators) {
    const candidates = all.filter(
      (s) => s.indicatorCode === code && (s.area?.code ?? 'OM') === 'OM' && s.partnerCode === null && (s.flow === null || s.flow === 'domestic_export'),
    );
    let best: { series: Series; obs: ObservationRecord } | null = null;
    for (const series of candidates) {
      for (const obs of series.observations) {
        if (obs.value !== null && (!best || obs.periodEnd > best.obs.periodEnd)) best = { series, obs };
      }
    }
    if (best) return best;
  }
  return null;
}
