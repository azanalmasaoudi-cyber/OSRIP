import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import { useUpdateSearch } from './useUpdateSearch';

/**
 * One page filter stored in the URL query as a stable code (never a translated
 * label), so it survives language switches, reloads and shared links (T08).
 * Unknown values fall back to the default; the default is omitted from the URL.
 */
export function useUrlFilter<T extends string>(
  param: string,
  allowed: readonly T[],
  fallback: T,
): [T, (next: T) => void] {
  const [params] = useSearchParams();
  const update = useUpdateSearch();
  const raw = params.get(param);
  const value = allowed.find((option) => option === raw) ?? fallback;

  const setValue = useCallback(
    (next: T) => {
      update((p) => {
        if (next === fallback) p.delete(param);
        else p.set(param, next);
      }, { replace: true });
    },
    [param, fallback, update],
  );

  return [value, setValue];
}

/** Clears the given page filters, leaving global parameters such as the data mode. */
export function useResetFilters(paramsToClear: readonly string[]): { reset: () => void; active: boolean; count: number } {
  const [params] = useSearchParams();
  const update = useUpdateSearch();
  const count = paramsToClear.filter((p) => params.has(p)).length;
  const reset = useCallback(() => {
    update((p) => {
      for (const key of paramsToClear) p.delete(key);
    }, { replace: true });
  }, [paramsToClear, update]);
  return { reset, active: count > 0, count };
}
