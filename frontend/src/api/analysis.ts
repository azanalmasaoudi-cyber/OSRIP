import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { apiBaseUrl, adapterKind } from './config';
import type { DataMode, SectionCode } from '@/domain/types';

/**
 * Calculations, review cards and reports. The API does every calculation; the
 * interface only displays results with their inputs, reasons and caveats.
 */

const text = z.object({ en: z.string(), ar: z.string() });
const explained = text.extend({ code: z.string() });
const unit = z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() });

const inputSchema = z.object({
  role: z.string(),
  indicator: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
  value: z.string().nullable(),
  unit,
  period_start: z.string(),
  period_end: z.string(),
  period_complete: z.boolean(),
  frequency: z.string(),
  // Reference-pack provenance (absent on older servers).
  period_kind: z.string().nullish(),
  record_ref: z.string().nullish(),
  source_code: z.string().nullish(),
  source_locator: z.string().nullish(),
  revision_status: z.string().nullish(),
  value_operator: z.string().nullish(),
  area: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
  commodity: z.string().nullable(),
  partner: z.string().nullable(),
  flow: z.string().nullable(),
  quality_status: z.string(),
  dataset_version: z.object({ id: z.string(), label: z.string() }),
  source_title: z.string(),
  source_row: z.string(),
});
export type CalcInput = z.infer<typeof inputSchema>;

export const calculationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  section: z.string(),
  title: text,
  formula: text,
  inputs: z.array(inputSchema),
  result: z.object({
    status: z.enum(['ok', 'missing', 'undefined', 'incompatible', 'not_calculated', 'unavailable']),
    value: z.string().nullable(),
    unit: unit.nullable(),
  }),
  reason: explained.nullable(),
  caveats: z.array(explained),
  notes: z.array(text.extend({ code: z.string().optional() })),
  breakdown: z.array(z.object({ partner: z.string(), status: z.string(), value: z.string().nullable() })),
});
export type Calculation = z.infer<typeof calculationSchema>;

const analysisSchema = z.object({
  section: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  label: z.string(),
  filters: z.record(z.string(), z.string()),
  assumptions: z.object({ stock_assumption: z.string() }),
  calculations: z.array(calculationSchema),
});
export type Analysis = z.infer<typeof analysisSchema>;

export const cardSchema = z.object({
  id: z.string(),
  rule_code: z.string(),
  section: z.string().nullable(),
  data_mode: z.string(),
  observation: text,
  next_steps: text,
  evidence: z.object({
    calculation_title: text,
    formula: text,
    result: calculationSchema.shape.result,
    inputs: z.array(inputSchema),
    rule: z.object({
      code: z.string(),
      name: text,
      version: z.string(),
      threshold: z.string().nullable(),
      eligibility: text,
      threshold_note: text.nullable(),
    }),
    limitations: z.array(explained),
  }),
  status: z.enum(['open', 'under_review', 'explained', 'dismissed']),
  review_count: z.number(),
  created_at: z.string(),
});
export type ReviewCard = z.infer<typeof cardSchema>;

const cardsSchema = z.object({
  run: z
    .object({ id: z.string(), status: z.string(), method_version: z.string(), finished_at: z.string().nullable() })
    .nullable(),
  cards: z.array(cardSchema),
});

const reviewSchema = z.object({
  id: z.number(),
  status: z.string(),
  reason: z.string(),
  reviewer: z.string(),
  created_at: z.string(),
});
export type Review = z.infer<typeof reviewSchema>;

/** Filters shared by tables, charts, calculations and exports on a section page. */
export interface SectionFilters {
  frequency?: string;
  area?: string;
  commodity?: string;
  indicator?: string;
  flow?: string;
  partner?: string;
  period_from?: string;
  period_to?: string;
  stock_assumption?: string;
}

function params(mode: DataMode, filters: SectionFilters, keys: readonly (keyof SectionFilters)[]): string {
  const p = new URLSearchParams({ data_mode: mode });
  for (const key of keys) {
    const value = filters[key];
    // The frequency filter holds a period kind (year to date is an annual-frequency partial year).
    if (value && value !== 'all') p.set(key === 'frequency' ? 'period_kind' : key, value);
  }
  return p.toString();
}

const ANALYSIS_KEYS = ['frequency', 'area', 'commodity', 'period_from', 'period_to', 'stock_assumption'] as const;
const OBSERVATION_KEYS = ['frequency', 'area', 'indicator', 'flow', 'partner', 'commodity', 'period_from', 'period_to'] as const;

export function analysisExportUrl(section: SectionCode, mode: DataMode, filters: SectionFilters): string {
  return `${apiBaseUrl}/analysis/${section}/export.csv?${params(mode, filters, ANALYSIS_KEYS)}`;
}

export function observationsExportUrl(section: SectionCode, mode: DataMode, filters: SectionFilters): string {
  return `${apiBaseUrl}/observations/export.csv?section=${section}&${params(mode, filters, OBSERVATION_KEYS)}`;
}

export function useAnalysis(section: SectionCode, mode: DataMode, filters: SectionFilters) {
  const query = params(mode, filters, ANALYSIS_KEYS);
  return useQuery({
    queryKey: ['analysis', section, query],
    queryFn: () => apiJson(`/analysis/${section}?${query}`, analysisSchema),
    enabled: adapterKind === 'http',
  });
}

export function useReviewCards(mode: DataMode, section?: SectionCode) {
  const query = new URLSearchParams({ data_mode: mode, ...(section ? { section } : {}) }).toString();
  return useQuery({
    queryKey: ['cards', mode, section ?? 'all'],
    queryFn: () => apiJson(`/recommendations?${query}`, cardsSchema),
    enabled: adapterKind === 'http',
  });
}

export function useRunRules() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (mode: DataMode) => apiJson('/analysis-runs', cardsSchema, jsonBody('POST', { data_mode: mode })),
    onSettled: () => void client.invalidateQueries({ queryKey: ['cards'] }),
  });
}

export function useReviews(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['reviews', id],
    queryFn: () => apiJson(`/recommendations/${id}/reviews`, z.array(reviewSchema)),
    enabled,
    retry: false,
  });
}

export function useAddReview(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { status: string; reason: string }) =>
      apiJson(`/recommendations/${id}/reviews`, z.array(reviewSchema), jsonBody('POST', body)),
    onSuccess: (history) => client.setQueryData(['reviews', id], history),
    onSettled: () => void client.invalidateQueries({ queryKey: ['cards'] }),
  });
}

// ------------------------------------------------------------------ reports

const reportSummary = z.object({
  id: z.string(),
  title: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  section: z.string().nullable(),
  visibility: z.enum(['private', 'published']),
  filters: z.record(z.string(), z.string()),
  assumptions: z.record(z.string(), z.string()),
  generated_at: z.string().nullable(),
  owned: z.boolean(),
});
export type ReportSummary = z.infer<typeof reportSummary>;

const seriesInReport = z.object({
  indicator: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string(),
    definition_en: z.string(), definition_ar: z.string(), limitation_en: z.string(), limitation_ar: z.string() }),
  unit,
  frequency: z.string(),
  area: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
  commodity: z.object({ code: z.string() }).nullable(),
  partner: z.object({ code: z.string() }).nullable(),
  flow: z.string().nullable(),
  dataset_version: z.object({ id: z.string(), label: z.string() }),
  source: z.object({ dataset_title: z.string(), publisher: z.string().nullable() }),
  observations: z.array(z.object({ period_start: z.string(), period_end: z.string(), value: z.string().nullable(),
    quality_status: z.string(), source_row: z.string() })),
});

const reportContent = z.object({
  title: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  label: z.string(),
  section: z.string(),
  filters: z.record(z.string(), z.string()),
  assumptions: z.record(z.string(), z.string()),
  generated_at: z.string(),
  series: z.array(seriesInReport),
  calculations: z.array(calculationSchema),
  review_cards: z.array(cardSchema),
  sources: z.array(z.object({ id: z.string(), label: z.string(),
    source: z.object({ dataset_title: z.string().optional(), publisher: z.string().nullable().optional() }) })),
});
export type ReportContent = z.infer<typeof reportContent>;

const reportDetail = reportSummary.extend({ content: reportContent });

export function reportExportUrl(id: string): string {
  return `${apiBaseUrl}/reports/${id}/export.csv`;
}

export function useReports() {
  return useQuery({
    queryKey: ['reports'],
    queryFn: () => apiJson('/reports', z.array(reportSummary)),
    enabled: adapterKind === 'http',
  });
}

export function useReport(id: string) {
  return useQuery({
    queryKey: ['reports', id],
    queryFn: () => apiJson(`/reports/${id}`, reportDetail),
    enabled: adapterKind === 'http',
    retry: false,
  });
}

export function useCreateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      title: string; data_mode: DataMode; section: SectionCode; filters: Record<string, string>;
      stock_assumption: string; visibility: 'private' | 'published';
    }) => apiJson('/reports', reportSummary, jsonBody('POST', body)),
    onSettled: () => void client.invalidateQueries({ queryKey: ['reports'] }),
  });
}

export function useSetReportVisibility(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (visibility: 'private' | 'published') =>
      apiJson(`/reports/${id}/visibility`, reportSummary, jsonBody('PUT', { visibility })),
    onSettled: () => void client.invalidateQueries({ queryKey: ['reports'] }),
  });
}
