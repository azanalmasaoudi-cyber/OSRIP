import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { dataAdapter } from './index';
import { mixedFrequencies } from '@/components/common/MixedFrequency';
import { PERIOD_KINDS, type DataMode, type SectionCode, type SeriesResponse } from '@/domain/types';

/** Query keys include the data mode so the two modes never share cache entries. */
export const queryKeys = {
  series: (section: SectionCode, mode: DataMode, frequency?: string) => ['series', mode, section, frequency ?? 'all'] as const,
  commodities: (mode: DataMode) => ['commodities', mode] as const,
};

function seriesQuery(section: SectionCode, mode: DataMode, frequency?: string) {
  return {
    queryKey: queryKeys.series(section, mode, frequency),
    queryFn: () => dataAdapter.getSeries(section, mode, frequency),
    // A refused mixed-frequency read is an answer, not a transient failure.
    retry: (count: number, error: Error) => mixedFrequencies(error) === null && count < 2,
  };
}

export function useSeries(section: SectionCode, mode: DataMode, frequency?: string) {
  return useQuery(seriesQuery(section, mode, frequency));
}

/** A section's series as one answer: loading, failed (with the first error) or loaded. */
export type SectionSeriesQuery = { refetch: () => Promise<unknown> } & (
  | { isPending: true; isError: false; error: null; data: undefined }
  | { isPending: false; isError: true; error: Error; data: undefined }
  | { isPending: false; isError: false; error: null; data: SeriesResponse }
);

type Loaded = Extract<SeriesResponse, { status: 'ok' }>;

function combineKinds(results: UseQueryResult<SeriesResponse>[]): SectionSeriesQuery {
  const refetch = () => Promise.all(results.map((r) => r.refetch()));
  const failed = results.find((r) => r.isError)?.error;
  if (failed) return { isPending: false, isError: true, error: failed, data: undefined, refetch };
  const responses = results.flatMap((r) => (r.data ? [r.data] : []));
  const first = responses[0];
  if (!first || responses.length < results.length) return { isPending: true, isError: false, error: null, data: undefined, refetch };
  const loaded = responses.filter((d): d is Loaded => d.status === 'ok');
  const data: SeriesResponse = loaded.length === 0 ? first
    : loaded.length === 1 ? loaded[0]!
      : { status: 'ok', dataMode: loaded[0]!.dataMode, series: loaded.flatMap((d) => d.series) };
  return { isPending: false, isError: false, error: null, data, refetch };
}

/**
 * Series of one section. With a period kind, one read. Without one (the "All" filter), one
 * read per period kind: the API refuses a read that mixes full years, year-to-date totals,
 * quarters, months or statements of one indicator, so each kind is read on its own and the
 * kinds are listed apart (`byPeriodKind`), never merged into one series. These are the same
 * cached reads as choosing each kind.
 */
export function useSectionSeries(section: SectionCode, mode: DataMode, frequency?: string): SectionSeriesQuery {
  const kinds: readonly string[] = frequency ? [frequency] : PERIOD_KINDS;
  return useQueries({ queries: kinds.map((kind) => seriesQuery(section, mode, kind)), combine: combineKinds });
}

export function useCommodities(mode: DataMode) {
  return useQuery({
    queryKey: queryKeys.commodities(mode),
    queryFn: () => dataAdapter.getCommodities(mode),
  });
}
