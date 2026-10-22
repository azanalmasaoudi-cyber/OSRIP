import { useLocation } from 'react-router';

/**
 * Query parameters that apply to the whole app and follow the user between
 * pages. Page filters (flow, partner, …) are page-scoped and are not carried
 * to other pages. Language switching never touches the URL at all, so both
 * kinds survive a language change.
 */
const GLOBAL_PARAMS = ['mode'] as const;

/** Navigation targets keep the global query parameters (currently the data mode). A target
 * may carry its own parameters ("/studies?create=water"); they are added to the kept ones. */
export function usePreservedSearch(): (pathname: string) => { pathname: string; search: string } {
  const { search } = useLocation();
  const current = new URLSearchParams(search);
  const kept = new URLSearchParams();
  for (const key of GLOBAL_PARAMS) {
    const value = current.get(key);
    if (value !== null) kept.set(key, value);
  }
  return (target: string) => {
    const [pathname = '', own = ''] = target.split('?', 2);
    const merged = new URLSearchParams(kept);
    for (const [key, value] of new URLSearchParams(own)) merged.set(key, value);
    return { pathname, search: merged.size ? `?${merged.toString()}` : '' };
  };
}
