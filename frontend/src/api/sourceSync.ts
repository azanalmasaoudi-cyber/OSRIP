import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { adapterKind } from './config';

/**
 * Official statistics feeds (backend app/services/sync): each feed's last successful check,
 * latest release (the publisher's own date) and latest observation period, kept apart; and
 * for administrators the schedule, a manual check, a hand upload, the releases and the log.
 * Checks themselves run in the sync worker, never in the browser.
 */

const text = z.object({ en: z.string(), ar: z.string() });

const feedSchema = z.object({
  code: z.string(),
  publisher: z.string(),
  title: text,
  access: z.enum(['public_listing', 'requires_access']),
  enabled: z.boolean(),
  check_interval_hours: z.number(),
  auto_publish: z.boolean().optional(),
  last_checked_at: z.string().nullable(),
  last_success_at: z.string().nullable(),
  next_check_at: z.string().nullable(),
  last_status: z.string().nullable(),
  last_error: z.string().nullable().optional(),
  latest_release: z.object({
    title_en: z.string(), title_ar: z.string().nullable(), published_at: z.string().nullable(),
    status: z.string(), file_url: z.string().nullable(),
  }).nullable(),
  latest_observation: z.object({ period_end: z.string(), indicator: z.string() }).nullable(),
  indicators: z.array(z.string()),
  tables: z.array(z.string()),
  notes: text.nullable(),
  verified: z.record(z.string(), z.string()),
});
export type SourceFeed = z.infer<typeof feedSchema>;

const runSchema = z.object({
  id: z.string(),
  trigger: z.string(),
  status: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  attempts: z.number(),
  http_status: z.number().nullable(),
  releases_seen: z.number(),
  release_id: z.string().nullable(),
  message: z.string().nullable(),
});
export type SyncRun = z.infer<typeof runSchema>;

const releaseSchema = z.object({
  id: z.string(),
  external_id: z.string(),
  title_en: z.string(),
  title_ar: z.string().nullable(),
  published_at: z.string().nullable(),
  file_url: z.string().nullable(),
  status: z.string(),
  rows_read: z.number(),
  rows_new: z.number(),
  rows_revised: z.number(),
  rows_unchanged: z.number(),
  import_id: z.string().nullable(),
  message: z.string().nullable(),
  detected_at: z.string().nullable(),
  processed_at: z.string().nullable(),
});
export type SyncRelease = z.infer<typeof releaseSchema>;

const KEY = ['source-feeds'] as const;

/** Public status (no error text), or the administrators' view. */
export function useSourceFeeds(admin = false) {
  return useQuery({
    queryKey: [...KEY, admin ? 'admin' : 'public'],
    queryFn: () => apiJson(admin ? '/admin/source-feeds' : '/source-feeds', z.array(feedSchema)),
    enabled: adapterKind === 'http',
  });
}

export function useFeedRuns(code: string, enabled = true) {
  return useQuery({
    queryKey: [...KEY, code, 'runs'],
    queryFn: () => apiJson(`/admin/source-feeds/${code}/runs`, z.array(runSchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useFeedReleases(code: string, enabled = true) {
  return useQuery({
    queryKey: [...KEY, code, 'releases'],
    queryFn: () => apiJson(`/admin/source-feeds/${code}/releases`, z.array(releaseSchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

function useFeedMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSettled: () => void client.invalidateQueries({ queryKey: KEY }) });
}

export function useUpdateFeed(code: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { enabled?: boolean; check_interval_hours?: number; auto_publish?: boolean }) =>
      apiJson(`/admin/source-feeds/${code}`, feedSchema, jsonBody('PATCH', body)),
    // The saved state is shown at once (no flicker back to the old value before the refetch).
    onSuccess: (saved) => client.setQueryData<SourceFeed[]>([...KEY, 'admin'],
      (old) => old?.map((f) => (f.code === code ? saved : f))),
    onSettled: () => void client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useCheckFeed(code: string) {
  return useFeedMutation(() => apiJson(`/admin/source-feeds/${code}/check`, runSchema, { method: 'POST' }));
}

export function useUploadWorkbook(code: string) {
  return useFeedMutation((vars: { file: File; title: string; fileUrl: string; publishedOn: string }) => {
    const form = new FormData();
    form.set('file', vars.file);
    form.set('title', vars.title);
    form.set('file_url', vars.fileUrl);
    if (vars.publishedOn) form.set('published_on', vars.publishedOn);
    return apiJson(`/admin/source-feeds/${code}/upload`, runSchema, { method: 'POST', body: form });
  });
}
