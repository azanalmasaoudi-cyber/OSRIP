import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';
import { bilingual, chartSchema, columnSchema } from './studies';

/**
 * Datasets people upload to analyse (CSV, Excel, JSON). Private to their owner and never part
 * of the published statistics. Every statistic, trend, chart table and finding is computed by
 * the server from the file's own values; the page only displays them. The AI summary is
 * written by the configured model from those computed results, and the server removes any
 * sentence whose numbers are not among them.
 */

const unit = z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() });
const point = z.object({ period: z.string(), value: z.string() });

const profileSchema = z.object({
  index: z.number(),
  name: z.string(),
  kind: z.enum(['number', 'period', 'text']),
  count: z.number(),
  missing: z.number(),
  distinct: z.number(),
  examples: z.array(z.string()),
  period_kind: z.enum(['year', 'quarter', 'month', 'date']).optional(),
  date_order: z.enum(['day_first', 'month_first']).optional(),
  unit: unit.optional(),
  unreadable: z.number().optional(),
  unreadable_rows: z.array(z.number()).optional(),
  category: z.boolean().optional(),
  top: z.array(z.object({ value: z.string(), count: z.number() })).optional(),
});
export type ColumnProfile = z.infer<typeof profileSchema>;

const statisticsSchema = z.object({
  column: z.string(),
  count: z.number(),
  sum: z.string(),
  mean: z.string(),
  median: z.string(),
  min: z.object({ value: z.string(), row: z.number() }),
  max: z.object({ value: z.string(), row: z.number() }),
  q1: z.string(),
  q3: z.string(),
  std: z.string().nullable(),
  all_non_negative: z.boolean(),
});
export type ColumnStatistics = z.infer<typeof statisticsSchema>;

const trendSchema = z.object({
  column: z.string(),
  period_column: z.string(),
  group: z.object({ column: z.string(), value: z.string() }).nullable(),
  points: z.number(),
  first: point,
  last: point,
  change: z.string(),
  change_pct: z.string().nullable(),
  direction: z.enum(['up', 'down', 'flat']),
  cagr_pct: z.string().nullable(),
  steady: z.boolean(),
  peak: point,
  trough: point,
  slope_per_period: z.string(),
  jumps: z.array(z.object({
    from: point,
    to: point.extend({ row: z.number() }),
    change: z.string(),
    score: z.string(),
  })),
});
export type Trend = z.infer<typeof trendSchema>;

const anomalySchema = z.object({
  column: z.string(),
  method: z.enum(['modified_z_score', 'iqr_fences']).nullable(),
  status: z.enum(['found', 'none', 'too_few_values']),
  count: z.number().optional(),
  median: z.string().optional(),
  items: z.array(z.object({ row: z.number(), value: z.string(), score: z.string().nullable(), period: z.string().optional() })),
});
export type AnomalyReport = z.infer<typeof anomalySchema>;

const comparisonSchema = z.object({
  category: z.string(),
  column: z.string(),
  groups: z.array(z.object({
    group: z.string(),
    count: z.number(),
    sum: z.string(),
    mean: z.string(),
    min: z.string(),
    max: z.string(),
    share_pct: z.string().nullable(),
  })),
  total: z.string(),
  one_row_per_group: z.boolean(),
});
export type Comparison = z.infer<typeof comparisonSchema>;

export const CHART_TYPES = ['line', 'bar', 'pie', 'scatter', 'heatmap'] as const;
export type ChartType = (typeof CHART_TYPES)[number];

const viewSchema = z.object({
  id: z.string(),
  title: bilingual,
  table: z.object({ columns: z.array(columnSchema), rows: z.array(z.record(z.string(), z.string().nullable())) }),
  chart: chartSchema,
  alternatives: z.array(z.enum(CHART_TYPES)),
  note: bilingual.nullable(),
});
export type DatasetView = z.infer<typeof viewSchema>;

const analysisSchema = z.object({
  version: z.number(),
  rows: z.number(),
  columns: z.number(),
  duplicate_rows: z.number(),
  profile: z.array(profileSchema),
  statistics: z.array(statisticsSchema),
  trends: z.array(trendSchema),
  trend_notes: z.array(z.string()),
  anomalies: z.array(anomalySchema),
  comparisons: z.array(comparisonSchema),
  correlations: z.array(z.object({ x: z.string(), y: z.string(), r: z.string(), pairs: z.number(), strength: z.enum(['strong', 'moderate', 'weak']) })),
  findings: z.array(z.object({ kind: z.string(), text: bilingual })),
  views: z.array(viewSchema),
});
export type DatasetAnalysis = z.infer<typeof analysisSchema>;

const summarySchema = z.object({
  status: z.enum(['ok', 'withheld']),
  removed: z.number(),
  overview: z.string(),
  highlights: z.array(z.string()),
  caveats: z.array(z.string()),
  language: z.enum(['en', 'ar']),
  provider: z.string(),
  model: z.string(),
  created_at: z.string(),
});
export type DatasetSummary = z.infer<typeof summarySchema>;

const infoSchema = z.object({
  id: z.string(),
  name: z.string(),
  file_type: z.enum(['csv', 'xlsx', 'json']),
  file_size: z.number(),
  sheet: z.string().nullable(),
  columns: z.array(z.string()),
  row_count: z.number(),
  notes: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  summary_languages: z.array(z.string()),
});
export type DatasetInfo = z.infer<typeof infoSchema>;

const detailSchema = infoSchema.extend({
  analysis: analysisSchema,
  summary: z.record(z.string(), summarySchema),
  created: z.boolean().optional(),
});
export type DatasetDetail = z.infer<typeof detailSchema>;

const rowsSchema = z.object({
  columns: z.array(z.string()),
  rows: z.array(z.array(z.string().nullable())),
  row_count: z.number(),
  truncated: z.boolean(),
});
export type DatasetRows = z.infer<typeof rowsSchema>;

const KEY = ['datasets'] as const;
const enabled = adapterKind === 'http';

export function useDatasets(allowed: boolean) {
  return useQuery({ queryKey: KEY, queryFn: () => apiJson('/datasets', z.array(infoSchema)), enabled: enabled && allowed });
}

export function useDataset(id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiJson(`/datasets/${encodeURIComponent(id ?? '')}`, detailSchema),
    enabled: enabled && Boolean(id),
  });
}

export function useDatasetRows(id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, id, 'rows'],
    queryFn: () => apiJson(`/datasets/${encodeURIComponent(id ?? '')}/rows`, rowsSchema),
    enabled: enabled && Boolean(id),
    staleTime: Infinity, // an uploaded dataset never changes
  });
}

export function useUploadDataset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: { file: File; sheet?: string }) => {
      const form = new FormData();
      form.set('file', vars.file);
      if (vars.sheet) form.set('sheet', vars.sheet);
      return apiJson('/datasets', detailSchema, { method: 'POST', body: form });
    },
    onSuccess: (detail) => {
      client.setQueryData([...KEY, detail.id], detail);
      void client.invalidateQueries({ queryKey: KEY, exact: true });
    },
  });
}

export function useDeleteDataset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/datasets/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSummariseDataset(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (language: 'en' | 'ar') =>
      apiJson(`/datasets/${encodeURIComponent(id)}/summary`, summarySchema, jsonBody('POST', { language })),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...KEY, id], exact: true }),
  });
}

/** Server-built exports of a dataset with its computed analysis. */
export function datasetExportUrl(id: string, format: 'csv' | 'xlsx', language: 'en' | 'ar'): string {
  return `${apiBaseUrl}/datasets/${encodeURIComponent(id)}/export.${format}?language=${language}`;
}
