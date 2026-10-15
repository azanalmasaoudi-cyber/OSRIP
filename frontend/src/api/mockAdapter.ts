import type { DataAdapter } from './adapter';
import { COMMODITY_REGISTRY, SYNTHETIC_SERIES } from './syntheticFixtures';
import type { Commodity, DataMode, SectionCode, SeriesResponse } from '@/domain/types';

/**
 * Frontend-only adapter. It holds NO verified-source data: in verified mode it
 * reports that nothing is published rather than substituting synthetic values.
 */
export function createMockAdapter(latencyMs = 150): DataAdapter {
  const delay = () => new Promise<void>((resolve) => setTimeout(resolve, latencyMs));

  return {
    kind: 'mock',

    async getSeries(section: SectionCode, mode: DataMode, frequency?: string): Promise<SeriesResponse> {
      await delay();
      if (mode === 'verified_source') {
        return { status: 'no_published_data', dataMode: mode, reason: 'no_verified_source_data' };
      }
      const series = SYNTHETIC_SERIES[section].filter((s) => !frequency || s.frequency === frequency);
      return { status: 'ok', dataMode: mode, series };
    },

    async getCommodities(mode: DataMode): Promise<readonly Commodity[]> {
      await delay();
      return COMMODITY_REGISTRY.filter((c) => mode === 'synthetic' || !c.syntheticOnly);
    },
  };
}
