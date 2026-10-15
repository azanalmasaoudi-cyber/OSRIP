/**
 * VITE_DATA_ADAPTER=http (default): the OSRIP API. `mock` is kept only for
 * offline interface work and the mock-mode test suite; it has no calculations,
 * review cards or reports.
 */
export const adapterKind: 'mock' | 'http' = import.meta.env.VITE_DATA_ADAPTER === 'mock' ? 'mock' : 'http';

// Default: same origin through the Vite dev proxy (see vite.config.ts), so the
// SameSite=Strict session cookie is sent without any cross-origin setup.
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
