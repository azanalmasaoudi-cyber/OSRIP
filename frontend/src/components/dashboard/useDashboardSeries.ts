import { useBackendStatus } from '@/api/backendStatus';
import { previewSeries } from '@/api/previewFixtures';
import { useSeries } from '@/api/queries';
import type { SectionCode, SeriesResponse } from '@/domain/types';
import { useDataMode } from '@/state/useDataMode';

export type DashboardSeries =
  | { state: 'loading' }
  | { state: 'error'; error: Error; retry: () => void }
  | { state: 'ready'; response: SeriesResponse; preview: boolean };

/**
 * Series for one section through the existing adapter. Only when the OSRIP API does not
 * answer at all are labelled preview fixtures returned instead (never to fill gaps in a
 * live response).
 */
export function useDashboardSeries(section: SectionCode, frequency?: string): DashboardSeries {
  const [mode] = useDataMode();
  const backend = useBackendStatus();
  const query = useSeries(section, mode, frequency);
  if (backend === 'offline') return { state: 'ready', response: previewSeries(section, frequency), preview: true };
  if (query.isPending) return { state: 'loading' };
  if (query.isError) return { state: 'error', error: query.error, retry: () => void query.refetch() };
  return { state: 'ready', response: query.data, preview: false };
}
