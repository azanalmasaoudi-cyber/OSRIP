import { z } from 'zod';

import { DataAdapterError } from './adapter';
import { apiBaseUrl } from './config';
import { API_NOT_CONNECTED, CONTRACT_MISMATCH, SERVER_UNAVAILABLE, foreignFailureCode, isFromOsripApi } from './problems';

export { SERVER_UNAVAILABLE } from './problems';

/**
 * Minimal fetch wrapper for the OSRIP API.
 *  - Sends the session cookie (same origin through the Vite proxy in development).
 *  - Echoes the CSRF cookie in X-CSRF-Token on state-changing requests; the server
 *    compares it with the hash stored for the session.
 *  - Turns the API's {error: {code, message}} envelope into DataAdapterError.
 *  - Tells the API's own answers apart from a host or proxy answering in its place (see
 *    problems.ts): a static host's "page not found" becomes `api_not_connected`, a gateway
 *    error `server_unavailable`, never a made-up API error or an empty result.
 * Authorization is enforced by the server on every request; nothing here grants access.
 */

const errorEnvelope = z.object({
  error: z.object({ code: z.string(), message: z.string(), details: z.unknown().optional() }),
});

function csrfToken(): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='));
  return match ? decodeURIComponent(match.slice('osrip_csrf='.length)) : null;
}

/** English fallbacks; pages show the translated text for the code (problems.* keys). */
const UNAVAILABLE_MESSAGE = 'The OSRIP server is not responding right now. Try again in a moment.';
const NOT_CONNECTED_MESSAGE = 'No OSRIP API answers at this address, so no data can be loaded.';

export class ApiRequestError extends DataAdapterError {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(code, message);
    this.status = status;
    this.details = details;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = csrfToken();
    if (token) headers.set('X-CSRF-Token', token);
  }
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers, credentials: 'same-origin' });
  } catch {
    throw new ApiRequestError(0, SERVER_UNAVAILABLE, UNAVAILABLE_MESSAGE);
  }
  const fromApi = isFromOsripApi(response.headers);
  if (!response.ok) {
    if (!fromApi) {
      // A host or proxy answering in the API's place: a gateway error (the development proxy or a
      // reverse proxy with the API stopped) or a static host with no API behind it at all. Its
      // body is not read: Vercel's 404 even mimics the API's error shape.
      const code = foreignFailureCode(response.status);
      throw new ApiRequestError(response.status, code, code === API_NOT_CONNECTED ? NOT_CONNECTED_MESSAGE : UNAVAILABLE_MESSAGE);
    }
    const body: unknown = await response.json().catch(() => null);
    const parsed = errorEnvelope.safeParse(body);
    if (parsed.success) {
      throw new ApiRequestError(response.status, parsed.data.error.code, parsed.data.error.message, parsed.data.error.details);
    }
    throw [502, 503, 504].includes(response.status)
      ? new ApiRequestError(response.status, SERVER_UNAVAILABLE, UNAVAILABLE_MESSAGE)
      : new ApiRequestError(response.status, 'http_error', `Request failed with status ${response.status}.`);
  }
  // A static host that sends its page for every address answers API requests with HTML and 200:
  // that is no API either.
  if (!fromApi && !(response.headers.get('content-type') ?? '').includes('json')) {
    throw new ApiRequestError(response.status, API_NOT_CONNECTED, NOT_CONNECTED_MESSAGE);
  }
  return response;
}

export async function apiJson<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  const body: unknown = await response.json().catch(() => undefined);
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiRequestError(response.status, CONTRACT_MISMATCH, 'The API response did not have the expected shape.');
  }
  return parsed.data;
}

export function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
