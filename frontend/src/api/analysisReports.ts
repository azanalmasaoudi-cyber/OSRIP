import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';
import { chartSchema, columnSchema } from './studies';

/**
 * Research and dataset reports (osrip.report/1): frozen by the server when created from a
 * dataset's computed analysis or from an answer that passed the evidence check, private to
 * their owner, and exported by the server as PDF, Excel or CSV. The page only displays them.
 */

const tableSchema = z.object({
  columns: z.array(columnSchema),
  rows: z.array(z.record(z.string(), z.string().nullable())),
});

const blockSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('paragraph'), text: z.string(), note: z.boolean() }),
  z.object({ type: z.literal('bullets'), items: z.array(z.string()) }),
  z.object({
    type: z.literal('table'),
    title: z.string().nullable(),
    columns: z.array(z.object({ label: z.string(), numeric: z.boolean() })),
    rows: z.array(z.array(z.string().nullable())),
    note: z.string().nullable(),
  }),
  z.object({ type: z.literal('chart'), title: z.string(), table: tableSchema, chart: chartSchema, note: z.string().nullable() }),
]);
export type ReportBlock = z.infer<typeof blockSchema>;

export const reportDocumentSchema = z.object({
  schema: z.literal('osrip.report/1'),
  kind: z.enum(['research', 'dataset', 'platform']),
  language: z.enum(['en', 'ar']),
  title: z.string(),
  subtitle: z.string().nullable(),
  created_at: z.string(),
  meta: z.array(z.tuple([z.string(), z.string()])),
  sections: z.array(z.object({ heading: z.string(), blocks: z.array(blockSchema) })),
  references: z.array(z.object({
    title: z.string(),
    url: z.string().nullable(),
    publisher: z.string().nullable(),
    published: z.string().nullable(),
    retrieved: z.string().nullable(),
    note: z.string().nullable(),
  })),
  notice: z.string().nullable(),
});
export type ReportDocument = z.infer<typeof reportDocumentSchema>;

const summarySchema = z.object({
  id: z.string(),
  kind: z.enum(['research', 'dataset']),
  title: z.string(),
  language: z.enum(['en', 'ar']),
  created_at: z.string(),
  dataset_id: z.string().nullable(),
  message_id: z.number().nullable(),
});
export type AnalysisReportSummary = z.infer<typeof summarySchema>;
const detailSchema = summarySchema.extend({ content: reportDocumentSchema });

const KEY = ['analysis-reports'] as const;
const enabled = adapterKind === 'http';

export function useAnalysisReports(signedIn: boolean) {
  return useQuery({ queryKey: KEY, queryFn: () => apiJson('/analysis-reports', z.array(summarySchema)), enabled: enabled && signedIn });
}

export function useAnalysisReport(id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiJson(`/analysis-reports/${encodeURIComponent(id ?? '')}`, detailSchema),
    enabled: enabled && Boolean(id),
    staleTime: Infinity, // a report is frozen
  });
}

export function useCreateDatasetReport(datasetId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { language: 'en' | 'ar'; title?: string; questions: string[] }) =>
      apiJson(`/datasets/${encodeURIComponent(datasetId)}/report`, summarySchema, jsonBody('POST', body)),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY, exact: true }),
  });
}

export function useCreateAnswerReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: { messageId: number; language: 'en' | 'ar' }) =>
      apiJson(`/assistant/messages/${vars.messageId}/report`, summarySchema, jsonBody('POST', { language: vars.language })),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY, exact: true }),
  });
}

export function useDeleteAnalysisReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/analysis-reports/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY }),
  });
}

export type ExportFormat = 'pdf' | 'xlsx' | 'csv';

export function analysisReportExportUrl(id: string, format: ExportFormat): string {
  return `${apiBaseUrl}/analysis-reports/${encodeURIComponent(id)}/export.${format}`;
}

/** A platform report as PDF or Excel, in the reader's language (its CSV export is unchanged). */
export function platformReportExportUrl(id: string, format: 'pdf' | 'xlsx', language: 'en' | 'ar'): string {
  return `${apiBaseUrl}/reports/${encodeURIComponent(id)}/export.${format}?language=${language}`;
}
