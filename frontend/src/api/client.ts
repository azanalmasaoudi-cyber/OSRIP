import { z } from 'zod';

import { DataAdapterError } from './adapter';
import { apiBaseUrl } from './config';

/**
 * Minimal fetch wrapper for the OSRIP API.
 *  - Sends the session cookie (same origin through the Vite proxy in development).
 *  - Echoes the CSRF cookie in X-CSRF-Token on state-changing requests; the server
 *    compares it with the hash stored for the session.
 *  - Turns the API's {error: {code, message}} envelope into DataAdapterError.
 * Authorization is enforced by the server on every request; nothing here grants access.
 */

const errorEnvelope = z.object({
  error: z.object({ code: z.string(), message: z.string(), details: z.unknown().optional() }),
});

function csrfToken(): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith('osrip_csrf='));
  return match ? decodeURIComponent(match.slice('osrip_csrf='.length)) : null;
}

/** The API could not be reached, or a gateway answered for it (502/503/504 without the API's
 * own error): the server is temporarily unavailable. Pages translate the code. */
export const SERVER_UNAVAILABLE = 'server_unavailable';
const UNAVAILABLE_MESSAGE = 'The OSRIP server is not responding right now. Try again in a moment.';

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
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const parsed = errorEnvelope.safeParse(body);
    if (parsed.success) {
      throw new ApiRequestError(response.status, parsed.data.error.code, parsed.data.error.message, parsed.data.error.details);
    }
    // A gateway answering for an API that is not running or not responding (the development
    // proxy, a reverse proxy): said plainly, never shown as success.
    throw [502, 503, 504].includes(response.status)
      ? new ApiRequestError(response.status, SERVER_UNAVAILABLE, UNAVAILABLE_MESSAGE)
      : new ApiRequestError(response.status, 'http_error', `Request failed with status ${response.status}.`);
  }
  return response;
}

export async function apiJson<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  const body: unknown = await response.json();
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiRequestError(response.status, 'contract_mismatch', 'The API response did not have the expected shape.');
  }
  return parsed.data;
}

export function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
