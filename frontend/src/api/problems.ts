/*
 * What went wrong when the interface asked the OSRIP API for something, sorted into the few
 * situations a person can act on. Pages show the matching message (problems.* in the
 * translations) instead of a generic "Data unavailable" or "Something went wrong".
 *
 * No imports: the unit tests load this file directly (tests/api-problems.test.mjs).
 */

export type ProblemKind =
  /** No OSRIP API answers at this address: a static host (for example Vercel serving only the
   * built interface) or a wrong API address. Retrying does not help. */
  | 'not_connected'
  /** The API or the gateway in front of it is not responding: no network answer, or 502/503/504
   * from a proxy. Usually temporary. */
  | 'server_unavailable'
  /** The API answered, but its database cannot be reached. */
  | 'database_unavailable'
  /** The API needs a signed-in account for this (401). */
  | 'sign_in_required'
  /** The signed-in account lacks the permission (403). */
  | 'forbidden'
  /** The API answered with a shape this interface does not understand (version mismatch). */
  | 'invalid_response'
  /** Any other refusal by the API; its own message says why. */
  | 'request_failed';

export const API_NOT_CONNECTED = 'api_not_connected';
export const SERVER_UNAVAILABLE = 'server_unavailable';
export const DATABASE_UNAVAILABLE = 'database_unavailable';
export const CONTRACT_MISMATCH = 'contract_mismatch';

interface HeaderReader {
  get(name: string): string | null;
}

/**
 * True when a response came from the OSRIP API itself rather than from a host or proxy in front of
 * it. Every API response carries `X-Request-ID` (added by the API's request middleware) and, since
 * this release, `X-OSRIP-API`. A static host's own "404 page not found" carries neither, even when
 * its JSON looks like the API's `{error: {code, message}}` (Vercel's does).
 */
export function isFromOsripApi(headers: HeaderReader): boolean {
  if (headers.get('x-vercel-error')) return false;
  return Boolean(headers.get('x-osrip-api') || headers.get('x-request-id'));
}

/** The code for a failed response that did not come from the API: a gateway error means the API is
 * not responding; anything else means no API is behind this address at all. */
export function foreignFailureCode(status: number): string {
  return status >= 500 ? SERVER_UNAVAILABLE : API_NOT_CONNECTED;
}

export interface Problem {
  kind: ProblemKind;
  status: number | null;
  code: string | null;
  /** The API's own message (English), for `request_failed`; shown as technical detail. */
  message: string | null;
}

const FORBIDDEN_CODES = new Set(['forbidden', 'permission_denied', 'not_permitted', 'insufficient_permissions']);

/** Sorts any thrown value; API errors carry `code` and `status` (ApiRequestError). */
export function problemOf(error: unknown): Problem {
  const e = (error ?? {}) as { code?: unknown; status?: unknown; message?: unknown };
  const code = typeof e.code === 'string' ? e.code : null;
  const status = typeof e.status === 'number' && e.status > 0 ? e.status : null;
  const message = typeof e.message === 'string' && e.message ? e.message : null;
  const of = (kind: ProblemKind): Problem => ({ kind, status, code, message });
  if (code === API_NOT_CONNECTED) return of('not_connected');
  if (code === SERVER_UNAVAILABLE) return of('server_unavailable');
  if (code === DATABASE_UNAVAILABLE) return of('database_unavailable');
  if (code === CONTRACT_MISMATCH) return of('invalid_response');
  if (status === 401 || code === 'authentication_required') return of('sign_in_required');
  if (status === 403 || (code !== null && FORBIDDEN_CODES.has(code))) return of('forbidden');
  return of('request_failed');
}

/** Whether asking again soon can help (React Query retries only these): a server that is not
 * responding, an unreachable database or a server-side failure. Never a missing API, a sign-in,
 * a permission or a refused request. */
export function isWorthRetrying(error: unknown): boolean {
  const { kind, status } = problemOf(error);
  if (kind === 'server_unavailable' || kind === 'database_unavailable') return true;
  return kind === 'request_failed' && (status === null || status >= 500);
}
