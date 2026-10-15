import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import { useUpdateSearch } from './useUpdateSearch';
import { DATA_MODES, type DataMode } from '@/domain/types';

const PARAM = 'mode';

function parseMode(raw: string | null): DataMode {
  return DATA_MODES.find((m) => m === raw) ?? 'verified_source';
}

/**
 * Data mode lives in the URL (?mode=synthetic) so it survives language
 * switches, reloads and shared links. Default is verified-source: synthetic
 * mode must be chosen deliberately (booklet 3.4).
 */
export function useDataMode(): [DataMode, (mode: DataMode) => void] {
  const [params] = useSearchParams();
  const update = useUpdateSearch();
  const mode = parseMode(params.get(PARAM));

  const setMode = useCallback(
    (next: DataMode) => {
      update((p) => {
        if (next === 'verified_source') p.delete(PARAM);
        else p.set(PARAM, next);
      }, { replace: false });
    },
    [update],
  );

  return [mode, setMode];
}
