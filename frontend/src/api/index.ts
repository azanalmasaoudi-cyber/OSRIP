import type { DataAdapter } from './adapter';
import { adapterKind, apiBaseUrl } from './config';
import { createHttpAdapter } from './httpAdapter';
import { createMockAdapter } from './mockAdapter';

export { adapterKind, apiBaseUrl };

export const dataAdapter: DataAdapter = adapterKind === 'http' ? createHttpAdapter() : createMockAdapter();
