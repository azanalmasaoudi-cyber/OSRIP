import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';
import type { DataMode } from '@/domain/types';

/**
 * Studies: deterministic analyses run by the server from published observations. The page
 * renders the one validated study result (osrip.study/1) for its cards, table, chart and
 * exports, so they always agree; nothing is calculated here.
 */

const bilingual = z.object({ en: z.string(), ar: z.string() });
const unit = z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() });
const nature = z.enum(['observed', 'calculated', 'forecast', 'scenario']);

export const STUDY_KINDS = [
  'trend',
  'growth',
  'compare_regions',
  'seasonal_profile',
  'import_dependence',
  'partner_concentration',
  'data_quality',
  'scenario',
  'forecast_eligibility',
  'programme_assessment',
] as const;
export type StudyKind = (typeof STUDY_KINDS)[number];

const columnSchema = z.object({
  key: z.string(),
  label: bilingual,
  kind: z.enum(['text', 'period', 'number', 'status']),
  unit: unit.nullable().optional(),
});
export type StudyColumn = z.infer<typeof columnSchema>;

const chartSchema = z.object({
  type: z.enum(['line', 'bar', 'heatmap']),
  title: bilingual,
  x: z.string(),
  series: z.array(z.object({ column: z.string(), label: bilingual, nature })).default([]),
  y: z.string().nullable().optional(),
  value: z.string().nullable().optional(),
  unit: unit.nullable().optional(),
});
export type StudyChart = z.infer<typeof chartSchema>;

const evidenceSchema = z.object({
  id: z.string(),
  indicator: z.string(),
  area: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  value: z.string().nullable(),
  unit: z.string(),
  source_title: z.string(),
  source_url: z.string().nullable().optional(),
  dataset_version: z.string(),
  record_ref: z.string().nullable().optional(),
});
export type StudyEvidence = z.infer<typeof evidenceSchema>;

export const studyResultSchema = z.object({
  schema: z.literal('osrip.study/1'),
  kind: z.enum(STUDY_KINDS),
  status: z.enum(['ok', 'not_available', 'not_comparable']),
  title: bilingual,
  question: bilingual,
  params: z.record(z.string(), z.unknown()),
  data_mode: z.enum(['verified_source', 'synthetic']),
  dataset_versions: z.array(z.string()),
  periods: z.record(z.string(), z.string().nullable()),
  reason: bilingual.nullable().optional(),
  findings: z.array(z.object({ text: bilingual, evidence: z.array(z.string()) })),
  cards: z.array(z.object({
    label: bilingual,
    value: z.string().nullable(),
    unit: unit.nullable().optional(),
    period: z.string().nullable().optional(),
    nature,
  })),
  table: z.object({ columns: z.array(columnSchema), rows: z.array(z.record(z.string(), z.string().nullable())) }),
  charts: z.array(chartSchema),
  evidence: z.array(evidenceSchema),
  method: bilingual,
  assumptions: z.array(bilingual),
  limitations: z.array(bilingual),
  next_questions: z.array(bilingual),
  forecast_evaluation: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type StudyResult = z.infer<typeof studyResultSchema>;

const storedSchema = z.object({
  id: z.string(),
  created_at: z.string().nullable(),
  sha256: z.string(),
  study: studyResultSchema,
});
export type StoredStudy = z.infer<typeof storedSchema>;

const catalogSchema = z.object({
  kinds: z.array(z.object({ kind: z.enum(STUDY_KINDS), title: bilingual, params: z.record(z.string(), z.unknown()) })),
});

const mineSchema = z.array(z.object({
  id: z.string(),
  kind: z.enum(STUDY_KINDS),
  title: bilingual,
  status: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  created_at: z.string(),
}));
export type StudySummary = z.infer<typeof mineSchema>[number];

const reproduceSchema = z.object({
  id: z.string(),
  identical: z.boolean(),
  stored_versions: z.array(z.string()),
  current_versions: z.array(z.string()),
});

export function useStudyCatalog() {
  return useQuery({
    queryKey: ['studies', 'catalog'],
    queryFn: () => apiJson('/studies/catalog', catalogSchema),
    enabled: adapterKind === 'http',
    staleTime: 60 * 60 * 1000,
  });
}

export function useRunStudy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { kind: StudyKind; data_mode: DataMode; params: Record<string, unknown> }) =>
      apiJson('/studies', storedSchema, jsonBody('POST', body)),
    onSuccess: (stored) => {
      client.setQueryData(['studies', stored.id], stored);
      void client.invalidateQueries({ queryKey: ['studies', 'mine'] });
    },
  });
}

/** The validated study for the current selection, computed but not stored (workspace). */
export function useStudyPreview(kind: StudyKind, params: Record<string, unknown> | null, mode: DataMode) {
  return useQuery({
    queryKey: ['studies', 'preview', kind, params, mode],
    queryFn: () => apiJson('/studies/preview', z.object({ study: studyResultSchema }),
      jsonBody('POST', { kind, data_mode: mode, params })),
    enabled: adapterKind === 'http' && params !== null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useStudy(id: string | null) {
  return useQuery({
    queryKey: ['studies', id],
    queryFn: () => apiJson(`/studies/${id ?? ''}`, storedSchema),
    enabled: adapterKind === 'http' && Boolean(id),
    retry: false,
  });
}

export function useMyStudies(enabled: boolean) {
  return useQuery({
    queryKey: ['studies', 'mine'],
    queryFn: () => apiJson('/studies', mineSchema),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useDeleteStudy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/studies/${id}`, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['studies', 'mine'] }),
  });
}

export function useReproduceStudy() {
  return useMutation({
    mutationFn: (id: string) => apiJson(`/studies/${id}/reproduce`, reproduceSchema),
  });
}

/** Export links are plain GET downloads served with Content-Disposition by the API. */
export function studyExportUrl(id: string, format: 'csv' | 'json', language: 'en' | 'ar'): string {
  return format === 'csv'
    ? `${apiBaseUrl}/studies/${id}/export.csv?language=${language}`
    : `${apiBaseUrl}/studies/${id}/export.json`;
}
