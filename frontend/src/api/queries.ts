import { useQuery } from '@tanstack/react-query';

import { dataAdapter } from './index';
import { mixedFrequencies } from '@/components/common/MixedFrequency';
import type { DataMode, SectionCode } from '@/domain/types';

/** Query keys include the data mode so the two modes never share cache entries. */
export const queryKeys = {
  series: (section: SectionCode, mode: DataMode, frequency?: string) => ['series', mode, section, frequency ?? 'all'] as const,
  commodities: (mode: DataMode) => ['commodities', mode] as const,
};

export function useSeries(section: SectionCode, mode: DataMode, frequency?: string) {
  return useQuery({
    queryKey: queryKeys.series(section, mode, frequency),
    queryFn: () => dataAdapter.getSeries(section, mode, frequency),
    // A refused mixed-frequency read is an answer, not a transient failure.
    retry: (count, error) => mixedFrequencies(error) === null && count < 2,
  });
}

export function useCommodities(mode: DataMode) {
  return useQuery({
    queryKey: queryKeys.commodities(mode),
    queryFn: () => dataAdapter.getCommodities(mode),
  });
}
