import { useCallback, useEffect } from 'react';
import { useLocation, useSearchParams } from 'react-router';

/**
 * React Router's functional setSearchParams updater receives the params of the
 * last render, so two quick updates (e.g. two filters changed before the first
 * navigation commits) would drop the earlier one. Every URL-state update goes
 * through here instead and builds on the most recently *requested* query.
 */
let pending: { pathname: string; search: string } | null = null;

export function useUpdateSearch() {
  const [, setParams] = useSearchParams();
  const location = useLocation();

  // Once the router has caught up (or the user went to another page), the real
  // location is authoritative again.
  useEffect(() => {
    if (pending && (pending.pathname !== location.pathname || pending.search === location.search)) {
      pending = null;
    }
  }, [location.pathname, location.search]);

  return useCallback(
    (mutate: (params: URLSearchParams) => void, options: { replace: boolean }) => {
      const base = pending && pending.pathname === location.pathname ? pending.search : location.search;
      const next = new URLSearchParams(base);
      mutate(next);
      const search = next.size ? `?${next.toString()}` : '';
      pending = { pathname: location.pathname, search };
      setParams(next, { ...options, preventScrollReset: true });
    },
    [location.pathname, location.search, setParams],
  );
}
