import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { adapterKind, apiBaseUrl } from './config';

/**
 * Whether the OSRIP API answers at all. `mock` means the build uses the in-browser adapter
 * (no backend expected); `offline` means the HTTP adapter is configured but `/health` did not
 * answer, so the dashboard falls back to clearly labelled preview fixtures.
 */
export type BackendStatus = 'mock' | 'checking' | 'online' | 'offline';

const HEALTH_KEY = ['backend-health'] as const;

export function useBackendStatus(): BackendStatus {
  const query = useQuery({
    queryKey: HEALTH_KEY,
    queryFn: async () => {
      const response = await fetch(`${apiBaseUrl}/health`, { credentials: 'same-origin' });
      return response.ok;
    },
    enabled: adapterKind === 'http',
    retry: false,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  if (adapterKind === 'mock') return 'mock';
  if (query.isPending) return 'checking';
  return query.data === true ? 'online' : 'offline';
}

export function useRecheckBackend() {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: HEALTH_KEY });
    void client.invalidateQueries({ queryKey: ['series'] });
  }, [client]);
}
