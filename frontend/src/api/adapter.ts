import type { Commodity, DataMode, SectionCode, SeriesResponse } from '@/domain/types';

/**
 * The only way UI code obtains data. Two implementations exist:
 *  - mockAdapter: in-browser SYNTHETIC fixtures; no backend involved.
 *  - httpAdapter: the OSRIP FastAPI service.
 * Selected at build time with VITE_DATA_ADAPTER (see src/api/index.ts).
 */
export interface DataAdapter {
  readonly kind: 'mock' | 'http';
  /** `frequency` narrows the read; without it the API refuses mixed frequencies. */
  getSeries(section: SectionCode, mode: DataMode, frequency?: string): Promise<SeriesResponse>;
  getCommodities(mode: DataMode): Promise<readonly Commodity[]>;
}

/** Stable, user-explainable failure (mirrors the API's {error: {code, message}}). */
export class DataAdapterError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'DataAdapterError';
    this.code = code;
  }
}
