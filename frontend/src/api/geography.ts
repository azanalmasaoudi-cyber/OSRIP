import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson } from './client';
import { adapterKind } from './config';
import type { DataMode } from '@/domain/types';

/**
 * Administrative registry (which areas exist) and statistical coverage (which
 * published observations exist for each exact area) are separate responses, so
 * the interface can never read "listed in the registry" as "has data".
 */

const areaSchema = z.object({
  code: z.string(),
  level: z.enum(['national', 'governorate', 'wilayat']),
  parent_code: z.string().nullable(),
  name_en: z.string(),
  name_ar: z.string(),
  iso_3166_2: z.string().nullable(),
  code_authority: z.enum(['osrip', 'iso_3166_2']),
  verified_on: z.string().nullable(),
  note_en: z.string().nullable(),
  note_ar: z.string().nullable(),
  references: z.array(z.object({ code: z.string(), supports: z.array(z.string()) })),
});
export type RegistryArea = z.infer<typeof areaSchema>;

const referenceSchema = z.object({
  code: z.string(),
  publisher: z.string(),
  title: z.string(),
  url: z.string(),
  language: z.enum(['en', 'ar']),
  published_on: z.string().nullable(),
  page_updated_on: z.string().nullable(),
  accessed_on: z.string(),
  supports: z.string(),
});
export type GeoReference = z.infer<typeof referenceSchema>;

const registrySchema = z.object({
  verification: z
    .object({
      verified_on: z.string(),
      expected_governorates: z.number(),
      expected_wilayats: z.number(),
      found_governorates: z.number(),
      found_wilayats: z.number(),
      complete: z.boolean(),
      basis_en: z.string(),
      basis_ar: z.string(),
      reference_codes: z.array(z.string()),
    })
    .nullable(),
  references: z.array(referenceSchema),
  geometry: z.object({ available: z.boolean(), en: z.string(), ar: z.string() }),
  areas: z.array(areaSchema),
});
export type Registry = z.infer<typeof registrySchema>;

const coverageIndicator = z.object({
  code: z.string(),
  name_en: z.string(),
  name_ar: z.string(),
  frequency: z.string(),
  observations: z.number(),
  values: z.number(),
  first_period: z.string(),
  last_period: z.string(),
});

const coverageSchema = z.object({
  data_mode: z.enum(['verified_source', 'synthetic']),
  label: z.string(),
  note_en: z.string(),
  note_ar: z.string(),
  areas: z.record(
    z.string(),
    z.object({ observations: z.number(), values: z.number(), missing: z.number(), indicators: z.array(coverageIndicator) }),
  ),
});
export type Coverage = z.infer<typeof coverageSchema>;
export type AreaCoverage = Coverage['areas'][string];

export function useAreaRegistry() {
  return useQuery({
    queryKey: ['areas'],
    queryFn: () => apiJson('/areas', registrySchema),
    enabled: adapterKind === 'http',
    staleTime: 60 * 60 * 1000,
  });
}

export function useAreaCoverage(mode: DataMode) {
  return useQuery({
    queryKey: ['area-coverage', mode],
    queryFn: () => apiJson(`/areas/coverage?data_mode=${mode}`, coverageSchema),
    enabled: adapterKind === 'http',
  });
}

const areaObservations = z.object({
  status: z.string(),
  series: z.array(
    z.object({
      indicator: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
      unit: z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() }),
      frequency: z.string(),
      commodity: z.object({ code: z.string() }).nullable(),
      partner: z.object({ code: z.string() }).nullable(),
      flow: z.string().nullable(),
      dataset_version: z.object({ id: z.string(), label: z.string() }),
      source: z.object({ dataset_title: z.string() }),
      observations: z.array(
        z.object({ period_start: z.string(), period_end: z.string(), value: z.string().nullable(), source_row: z.string() }),
      ),
    }),
  ),
});
export type AreaObservations = z.infer<typeof areaObservations>;

/** Published observations recorded for exactly this area (never a parent's or the nation's). */
export function useAreaObservations(mode: DataMode, area: string | null, frequency?: string) {
  const freq = frequency ? `&period_kind=${frequency}` : '';
  return useQuery({
    queryKey: ['area-observations', mode, area, frequency ?? 'all'],
    queryFn: () => apiJson(`/observations?data_mode=${mode}&area=${encodeURIComponent(area ?? '')}${freq}`, areaObservations),
    enabled: adapterKind === 'http' && area !== null,
    retry: false,
  });
}
