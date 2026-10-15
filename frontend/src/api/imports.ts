import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { apiBaseUrl } from './config';
import type { DataMode } from '@/domain/types';

/** Private import workflow (booklet 3.12). The server authorizes every call. */

export const versionStatus = z.enum(['draft', 'validated', 'approved', 'published', 'superseded', 'rejected']);
export type VersionStatus = z.infer<typeof versionStatus>;

const versionSchema = z.object({
  id: z.string(),
  label: z.string(),
  status: versionStatus,
  checksum_sha256: z.string(),
  created_at: z.string(),
  published_at: z.string().nullable(),
});

const sourceSchema = z.object({
  id: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  dataset_title: z.string(),
  publisher: z.string().nullable(),
  url: z.string().nullable(),
  locator_kind: z.string().nullable(),
  access_date: z.string().nullable(),
  reference_period: z.string().nullable(),
  geographic_coverage: z.string(),
  reuse_conditions: z.string().nullable(),
  versions: z.array(versionSchema),
  verification_note: z.string(),
});
export type SourceRecord = z.infer<typeof sourceSchema>;

const importSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  source_title: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  version: versionSchema,
  original_filename: z.string(),
  file_size: z.number(),
  header: z.array(z.string()),
  column_mapping: z.record(z.string(), z.string()).nullable(),
  required_fields: z.array(z.string()),
  optional_fields: z.array(z.string()),
  row_count: z.number().nullable(),
  valid_row_count: z.number().nullable(),
  warning_row_count: z.number().nullable(),
  rejected_row_count: z.number().nullable(),
  created_at: z.string(),
  approval_note: z.string().nullable(),
  rejection_reason: z.string().nullable(),
  last_error_code: z.string().nullable(),
});
export type ImportRecord = z.infer<typeof importSchema>;

const issueSchema = z.object({
  code: z.string(),
  severity: z.enum(['error', 'warning']),
  field: z.string().nullable(),
  value: z.string().nullable(),
  message: z.string(),
});
export type ImportIssue = z.infer<typeof issueSchema>;

const rowsSchema = z.object({
  total: z.number(),
  rows: z.array(
    z.object({
      row_number: z.number(),
      outcome: z.enum(['valid', 'warning', 'rejected']),
      raw: z.record(z.string(), z.string()),
      issues: z.array(issueSchema),
    }),
  ),
});
export type ImportRows = z.infer<typeof rowsSchema>;

const publishSchema = z.object({
  import: importSchema,
  already_published: z.boolean(),
  observations_inserted: z.number(),
  superseded_version_id: z.string().nullable(),
});
export type PublishResult = z.infer<typeof publishSchema>;

export const importKeys = {
  all: ['imports'] as const,
  list: () => ['imports', 'list'] as const,
  detail: (id: string) => ['imports', 'detail', id] as const,
  rows: (id: string, outcome: string) => ['imports', 'rows', id, outcome] as const,
  sources: (mode: DataMode) => ['imports', 'sources', mode] as const,
};

export function errorReportUrl(id: string): string {
  return `${apiBaseUrl}/imports/${id}/errors.csv`;
}

export function useSources(mode: DataMode, enabled = true) {
  return useQuery({
    queryKey: importKeys.sources(mode),
    queryFn: () => apiJson(`/sources?data_mode=${mode}`, z.array(sourceSchema)),
    enabled,
  });
}

export function useImports(enabled = true) {
  return useQuery({ queryKey: importKeys.list(), queryFn: () => apiJson('/imports', z.array(importSchema)), enabled });
}

export function useImport(id: string | null) {
  return useQuery({
    queryKey: importKeys.detail(id ?? ''),
    queryFn: () => apiJson(`/imports/${id}`, importSchema),
    enabled: Boolean(id),
  });
}

export function useImportRows(id: string, outcome: 'rejected' | 'warning' | 'all', enabled: boolean) {
  const query = outcome === 'all' ? '' : `&outcome=${outcome}`;
  return useQuery({
    queryKey: importKeys.rows(id, outcome),
    queryFn: () => apiJson(`/imports/${id}/rows?limit=200${query}`, rowsSchema),
    enabled,
  });
}

function useImportMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => void client.invalidateQueries({ queryKey: importKeys.all }),
  });
}

export function useRegisterSource() {
  return useImportMutation((body: Record<string, string | null>) =>
    apiJson('/sources', sourceSchema, jsonBody('POST', body)),
  );
}

export function useUpload() {
  return useImportMutation((vars: { sourceId: string; versionLabel: string; file: File }) => {
    const form = new FormData();
    form.set('source_id', vars.sourceId);
    form.set('version_label', vars.versionLabel);
    form.set('file', vars.file);
    return apiJson('/imports', importSchema, { method: 'POST', body: form });
  });
}

export function useSaveMapping(id: string) {
  return useImportMutation((mapping: Record<string, string>) =>
    apiJson(`/imports/${id}/mapping`, importSchema, jsonBody('PUT', { mapping })),
  );
}

export function useValidate(id: string) {
  return useImportMutation(() => apiJson(`/imports/${id}/validate`, importSchema, { method: 'POST' }));
}

export function useApprove(id: string) {
  return useImportMutation((vars: { acknowledged: number; note: string }) =>
    apiJson(`/imports/${id}/approve`, importSchema,
      jsonBody('POST', { acknowledged_rejected_rows: vars.acknowledged, note: vars.note || null })),
  );
}

export function usePublish(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiJson(`/imports/${id}/publish`, publishSchema, { method: 'POST' }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: importKeys.all });
      void client.invalidateQueries({ queryKey: ['series'] }); // dashboards show the new snapshot
      void client.invalidateQueries({ queryKey: ['commodities'] });
    },
  });
}

export function useReject(id: string) {
  return useImportMutation((reason: string) =>
    apiJson(`/imports/${id}/reject`, importSchema, jsonBody('POST', { reason })),
  );
}
