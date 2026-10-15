import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind } from './config';
import type { DataMode } from '@/domain/types';

/** Research library: source library, saved research with briefs, watchlist and alerts, and
 * governorate comparisons. Every figure comes from the server; nothing is computed here. */

const bilingual = z.object({ en: z.string(), ar: z.string() });

// ------------------------------------------------------------------ source library

const librarySourceSchema = z.object({
  kind: z.enum(['reference_pack', 'dataset', 'web_found']),
  code: z.string().nullable().optional(),
  title: z.string(),
  publisher: z.string().nullable().optional(),
  publication: z.string().optional(),
  source_class: z.string(),
  role: z.string().optional(),
  url: z.string().nullable(),
  accessed_on: z.string().nullable().optional(),
  research_cutoff: z.string().optional(),
  reference_period: z.string().nullable().optional(),
  published_records: z.number().optional(),
  publication_date: z.string().nullable().optional(),
  retrieved_at: z.string().nullable().optional(),
  domain: z.string().nullable().optional(),
  figures_found: z.number().optional(),
  figures_accepted: z.number().optional(),
  figures_pending: z.number().nullable().optional(),
});
export type LibrarySource = z.infer<typeof librarySourceSchema>;

const sourceLibrarySchema = z.object({ sources: z.array(librarySourceSchema), note: bilingual });

export const SOURCE_FILTERS = ['official', 'international', 'research', 'secondary', 'reference_pack', 'dataset'] as const;
export type SourceFilter = (typeof SOURCE_FILTERS)[number];

export function useSourceLibrary(q: string, sourceClass: SourceFilter | '') {
  const params = new URLSearchParams();
  if (q.trim()) params.set('q', q.trim());
  if (sourceClass) params.set('source_class', sourceClass);
  return useQuery({
    queryKey: ['library', 'sources', q.trim(), sourceClass],
    queryFn: () => apiJson(`/library/sources?${params.toString()}`, sourceLibrarySchema),
    enabled: adapterKind === 'http',
    placeholderData: keepPreviousData,
  });
}

// ------------------------------------------------------------------ saved research

const savedSchema = z.object({
  id: z.string(),
  title: z.string(),
  note: z.string().nullable(),
  question: z.string(),
  mode: z.string().nullable(),
  language: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  message_id: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  source_count: z.number(),
  recommendation_count: z.number(),
});
export type SavedResearch = z.infer<typeof savedSchema>;

export function useSavedResearch(enabled: boolean) {
  return useQuery({
    queryKey: ['library', 'saved'],
    queryFn: () => apiJson('/library/saved', z.array(savedSchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useSaveResearch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { message_id: number; title?: string }) =>
      apiJson('/library/saved', savedSchema, jsonBody('POST', body)),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'saved'] }),
  });
}

export function useUpdateSaved() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; title?: string; note?: string }) =>
      apiJson(`/library/saved/${id}`, savedSchema, jsonBody('PATCH', body)),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'saved'] }),
  });
}

export function useDeleteSaved() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/library/saved/${id}`, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'saved'] }),
  });
}

/** Downloads a brief through the session (the browser keeps the cookie; nothing is cached). */
export async function downloadBrief(id: string, format: 'html' | 'md'): Promise<void> {
  const response = await apiFetch(`/library/saved/${id}/brief?format=${format}`);
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `osrip-brief.${format}`;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------------ watchlist and alerts

const ruleSchema = z.object({
  id: z.number(),
  kind: z.enum(['new_data', 'above', 'below']),
  threshold: z.string().nullable(),
  enabled: z.boolean(),
  channel: z.enum(['in_app', 'email']),
  created_at: z.string().nullable(),
  last_triggered_at: z.string().nullable(),
});
export type AlertRule = z.infer<typeof ruleSchema>;

const watchItemSchema = z.object({
  id: z.number(),
  indicator: z.object({ code: z.string(), name: bilingual.nullable() }),
  area: z.object({ code: z.string(), name: bilingual.nullable() }),
  period_kind: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  unit: z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() }).passthrough().nullable(),
  latest: z.object({
    period_start: z.string(),
    period_end: z.string(),
    value: z.string().nullable(),
    value_operator: z.string().nullable().optional(),
    revision_status: z.string().nullable().optional(),
    source: z.string(),
  }).nullable(),
  change: z.object({
    status: z.string(),
    percent: z.string().nullable(),
    previous_period_start: z.string(),
    previous_value: z.string().nullable(),
  }).nullable(),
  rules: z.array(ruleSchema),
});
export type WatchItem = z.infer<typeof watchItemSchema>;

export function useWatchlist(enabled: boolean) {
  return useQuery({
    queryKey: ['library', 'watchlist'],
    queryFn: () => apiJson('/watchlist', z.array(watchItemSchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useWatch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { indicator: string; area: string; period_kind: string; data_mode: DataMode }) =>
      apiJson('/watchlist', watchItemSchema, jsonBody('POST', body)),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'watchlist'] }),
  });
}

export function useUnwatch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/watchlist/${id}`, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'watchlist'] }),
  });
}

export function useAddRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, ...body }: { itemId: number; kind: AlertRule['kind']; threshold?: string; channel: AlertRule['channel'] }) =>
      apiJson(`/watchlist/${itemId}/rules`, ruleSchema, jsonBody('POST', body)),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'watchlist'] }),
  });
}

export function useUpdateRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; enabled?: boolean; channel?: AlertRule['channel']; threshold?: string }) =>
      apiJson(`/alerts/rules/${id}`, ruleSchema, jsonBody('PATCH', body)),
    // The saved rule replaces the cached one at once, so the list never flickers back.
    onSuccess: (saved) => client.setQueryData<WatchItem[]>(['library', 'watchlist'], (old) =>
      old?.map((item) => ({ ...item, rules: item.rules.map((r) => (r.id === saved.id ? saved : r)) }))),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'watchlist'] }),
  });
}

export function useDeleteRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/alerts/rules/${id}`, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'watchlist'] }),
  });
}

const eventSchema = z.object({
  id: z.number(),
  rule_id: z.number(),
  kind: z.enum(['new_data', 'above', 'below']),
  indicator_code: z.string(),
  area_code: z.string(),
  value: z.string().nullable(),
  unit: z.string().nullable(),
  period_start: z.string(),
  period_end: z.string(),
  threshold: z.string().nullable(),
  message: bilingual,
  delivery: z.enum(['in_app', 'email_pending', 'email_sent', 'email_failed', 'email_unavailable']),
  created_at: z.string(),
  read_at: z.string().nullable(),
});
export type AlertEvent = z.infer<typeof eventSchema>;

export function useAlerts(enabled: boolean) {
  return useQuery({
    queryKey: ['library', 'alerts'],
    queryFn: () => apiJson('/alerts', z.object({ unread: z.number(), events: z.array(eventSchema) })),
    enabled: adapterKind === 'http' && enabled,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkAlertsRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (eventId?: number) => apiJson('/alerts/read', z.object({ marked: z.number() }), jsonBody('POST', { event_id: eventId ?? null })),
    onSettled: () => void client.invalidateQueries({ queryKey: ['library', 'alerts'] }),
  });
}

// ------------------------------------------------------------------ governorate comparison

const compareRowSchema = z.object({
  area: z.string(),
  name: bilingual,
  status: z.enum(['published', 'missing_in_source', 'no_published_value']),
  value: z.string().nullable(),
  value_operator: z.string().nullable().optional(),
  period_end: z.string().optional(),
  record_ref: z.string().nullable().optional(),
  revision_status: z.string().nullable().optional(),
  source: z.string().optional(),
  source_url: z.string().nullable().optional(),
});
export type CompareRow = z.infer<typeof compareRowSchema>;

const compareSchema = z.object({
  status: z.enum(['ok', 'not_comparable', 'no_data', 'choose_flow']),
  reason: z.enum(['different_units', 'different_period_lengths']).nullable().optional(),
  indicator: z.string().optional(),
  indicator_name: bilingual.nullable().optional(),
  unit: z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() }).passthrough().nullable().optional(),
  period_kind: z.string().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  level: z.string().optional(),
  flow: z.string().nullable().optional(),
  flows: z.array(z.string()).optional(),
  rows: z.array(compareRowSchema).optional(),
  areas_without_value: z.number().optional(),
  national: compareRowSchema.nullable().optional(),
  reporting_groups: z.array(z.object({
    area: z.string(), name: bilingual, value: z.string().nullable(), period_end: z.string(), record_ref: z.string().nullable().optional(), note: bilingual,
  })).optional(),
  available_periods: z.array(z.string()).optional(),
  notes: z.unknown().optional(),
});
export type AreaComparison = z.infer<typeof compareSchema>;

const COMPARE_PERIOD_KINDS = ['annual', 'year_to_date', 'quarterly', 'monthly', 'statement'];

export function useAreaComparison(
  mode: DataMode, indicator: string | null, periodStart: string | null, flow: string | null, periodKind = 'annual',
) {
  const params = new URLSearchParams({ data_mode: mode, indicator: indicator ?? '' });
  if (COMPARE_PERIOD_KINDS.includes(periodKind)) params.set('period_kind', periodKind);
  if (periodStart) params.set('period_start', periodStart);
  if (flow) params.set('flow', flow);
  return useQuery({
    queryKey: ['areas', 'compare', mode, indicator, periodKind, periodStart, flow],
    queryFn: () => apiJson(`/areas/compare?${params.toString()}`, compareSchema),
    enabled: adapterKind === 'http' && Boolean(indicator),
    placeholderData: keepPreviousData,
    retry: false,
  });
}
