import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind } from './config';
import type { Sector } from './balance';
import type { DataMode } from '@/domain/types';

/**
 * Studies as background jobs (backend app/services/research/jobs.py): created at once (202),
 * then read until finished. Steps: discover, retrieve, extract, validate, calculate, build,
 * conclude, next steps; each with its state and outcome. Web documents are untrusted evidence
 * with their provenance; they are never added to OSRIP's data.
 */

const text = z.object({ en: z.string(), ar: z.string() });
export const JOB_STAGES = ['discover', 'retrieve', 'extract', 'validate', 'calculate', 'build', 'conclude', 'next_steps'] as const;
export const JOB_STATES = ['queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled'] as const;
export type JobState = (typeof JOB_STATES)[number];
export const SOURCE_SCOPES = ['none', 'official', 'official_international'] as const;
export type SourceScope = (typeof SOURCE_SCOPES)[number];

const step = z.object({
  stage: z.enum(JOB_STAGES),
  state: z.enum(['pending', 'running', 'done', 'skipped', 'failed', 'cancelled']),
  label: text,
  attempts: z.number().optional(),
  detail: text.nullable().optional(),
  count: z.number().nullable().optional(),
  code: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  cached: z.boolean().optional(),
});
export type JobStep = z.infer<typeof step>;

const action = z.object({ id: z.string(), action: text, priority: z.string() });
const result = z.object({
  cached: z.boolean().optional(),
  sources: z.array(z.object({ id: z.string(), title: z.string(), publisher: z.string().nullable().optional(), url: z.string().nullable().optional(),
    source_code: z.string().nullable().optional(), dataset_version: z.string().nullable().optional(),
    published_at: z.string().nullable().optional() })).optional(),
  discovered: z.array(z.object({ url: z.string(), title: z.string().optional(), via: z.string().optional() }).passthrough()).optional(),
  discovery_notes: z.array(text).optional(),
  documents: z.object({ retrieved: z.number(), attempted: z.number(), stopped: z.string().nullable().optional(),
    by_status: z.record(z.string(), z.number()) }).passthrough().optional(),
  excerpts: z.array(z.object({ document_id: z.string(), url: z.string(), publisher: z.string().nullable().optional(),
    source_class: z.string(), title: z.string().nullable().optional(), reporting_period: z.string().nullable().optional(),
    text: z.string(), status: z.string() })).optional(),
  validation: z.array(z.object({ indicator: z.string(), status: z.string() }).passthrough()).optional(),
  analysis: z.object({ id: z.string(), status: z.string(), title: text,
    balances: z.array(z.object({ id: z.string(), title: text, status: z.string(), status_label: text })) }).passthrough().optional(),
  tables: z.array(z.object({ indicator: z.string(), name: text, view: z.string(), dataset_id: z.string(),
    unit: z.object({ code: z.string(), label: text }),
    params: z.object({ data_mode: z.string(), indicator: z.string(), area: z.string(), view: z.string(),
      period_from: z.string().nullable(), period_to: z.string().nullable() }) })).optional(),
  conclusion: z.object({
    main_findings: z.array(z.object({ text, evidence: z.array(z.string()) }).passthrough()),
    evidence_limitations: z.array(text),
    immediate_actions: z.array(action),
    medium_term_options: z.array(action),
    written_by: z.string(),
  }).optional(),
  next_steps: z.array(z.object({ question: text, data: text, where: text.nullable().optional() })).optional(),
}).passthrough();

export const jobSchema = z.object({
  id: z.string(),
  sector: z.string(),
  area: z.string(),
  period_from: z.string().nullable(),
  period_to: z.string().nullable(),
  question: z.string(),
  language: z.enum(['en', 'ar']),
  data_mode: z.string(),
  source_scope: z.enum(SOURCE_SCOPES),
  limits: z.record(z.string(), z.unknown()),
  state: z.enum(JOB_STATES),
  stage: z.string().nullable(),
  progress: z.number(),
  steps: z.array(step),
  attempts: z.number(),
  max_attempts: z.number(),
  cancel_requested: z.boolean(),
  error_code: z.string().nullable(),
  cached: z.boolean(),
  analysis_id: z.string().nullable(),
  result: result.optional(),
  credits_used: z.number(),
  created_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});
export type ResearchJob = z.infer<typeof jobSchema>;

const documentSchema = z.object({
  id: z.string(), url: z.string(), final_url: z.string().nullable(), host: z.string(), source_class: z.string(),
  publisher: z.string().nullable(), title: z.string().nullable(), retrieved_at: z.string().nullable(), published: z.string().nullable(),
  reporting_period: z.string().nullable(), content_type: z.string().nullable(), retriever: z.string(), status: z.string(),
  depth: z.number(), pages: z.number().nullable(), credits: z.number(), sha256: z.string().nullable(),
  duplicate_of: z.string().nullable(), revision_of: z.string().nullable(), excerpt: z.string().nullable(), untrusted: z.literal(true),
});
export type ResearchDocument = z.infer<typeof documentSchema>;

export interface JobParams {
  sector: Sector;
  area?: string;
  period_from?: string | null;
  period_to?: string | null;
  question: string;
  language: 'en' | 'ar';
  data_mode: DataMode;
  source_scope: SourceScope;
}

export const FINISHED: readonly JobState[] = ['succeeded', 'partial', 'failed', 'cancelled'];

export function useCreateJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { params: JobParams; refresh?: boolean }) => apiJson('/research/jobs', jobSchema, jsonBody('POST', body)),
    onSuccess: (job) => {
      client.setQueryData(['research-job', job.id], job);
      void client.invalidateQueries({ queryKey: ['research-jobs'] });
    },
  });
}

/** One study, read every two seconds until it has finished (no request is held open). */
export function useJob(id: string | null) {
  return useQuery({
    queryKey: ['research-job', id],
    queryFn: () => apiJson(`/research/jobs/${id ?? ''}`, jobSchema),
    enabled: adapterKind === 'http' && Boolean(id),
    refetchInterval: (query) => (query.state.data && FINISHED.includes(query.state.data.state) ? false : 2000),
    retry: false,
  });
}

export function useMyJobs(enabled = true) {
  return useQuery({
    queryKey: ['research-jobs'],
    queryFn: () => apiJson('/research/jobs', z.array(jobSchema)),
    enabled: adapterKind === 'http' && enabled,
    retry: false,
  });
}

export function useJobDocuments(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['research-job-documents', id],
    queryFn: () => apiJson(`/research/jobs/${id ?? ''}/documents`, z.array(documentSchema)),
    enabled: adapterKind === 'http' && Boolean(id) && enabled,
    retry: false,
  });
}

export function useJobAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'cancel' | 'retry' }) =>
      apiJson(`/research/jobs/${id}/${action}`, jobSchema, jsonBody('POST', {})),
    onSuccess: (job) => {
      client.setQueryData(['research-job', job.id], job);
      void client.invalidateQueries({ queryKey: ['research-jobs'] });
    },
  });
}

// ------------------------------------------------------------------ scheduled reports (administrators)

const scheduleSchema = z.object({
  id: z.string(), name: z.string(), sector: z.string(), area: z.string(), data_mode: z.string(), question: z.string(),
  language: z.enum(['en', 'ar']), frequency: z.enum(['weekly', 'monthly', 'quarterly']), source_scope: z.enum(SOURCE_SCOPES),
  max_pages: z.number(), max_credits_per_run: z.number(), max_credits_per_month: z.number(), allow_paid: z.boolean(),
  enabled: z.boolean(), paid: z.boolean(), next_run_at: z.string().nullable(), last_run_at: z.string().nullable(),
  credits_this_month: z.number().nullable(),
});
export type ReportSchedule = z.infer<typeof scheduleSchema>;

const statusSchema = z.object({
  scheduler_enabled: z.boolean(),
  retrieval: z.object({ firecrawl: z.enum(['configured', 'not_configured']), search_route: z.string().nullable(), direct_fetch: z.boolean() }),
  limits: z.object({ max_pages: z.number(), max_depth: z.number(), max_runtime_seconds: z.number(), max_credits: z.number(),
    max_pdf_pages: z.number(), host_interval_seconds: z.number(), allowed_domains: z.array(z.string()) }),
  cache_hours: z.number(),
});
export type RetrievalStatus = z.infer<typeof statusSchema>;

export function useRetrievalStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['retrieval-status'],
    queryFn: () => apiJson('/admin/research/status', statusSchema),
    enabled: adapterKind === 'http' && enabled,
    retry: false,
  });
}

export function useSchedules(enabled: boolean) {
  return useQuery({
    queryKey: ['report-schedules'],
    queryFn: () => apiJson('/admin/report-schedules', z.array(scheduleSchema)),
    enabled: adapterKind === 'http' && enabled,
    retry: false,
  });
}

export type ScheduleInput = Omit<ReportSchedule, 'id' | 'paid' | 'next_run_at' | 'last_run_at' | 'credits_this_month'>;

export function useScheduleMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body, action }: { id?: string; body?: Partial<ScheduleInput>; action?: 'run' | 'delete' }) => {
      if (action === 'run' && id) return apiJson(`/admin/report-schedules/${id}/run`, z.unknown(), jsonBody('POST', {}));
      if (action === 'delete' && id) {
        await apiFetch(`/admin/report-schedules/${id}`, { method: 'DELETE' });
        return null;
      }
      return id
        ? apiJson(`/admin/report-schedules/${id}`, scheduleSchema, jsonBody('PUT', body))
        : apiJson('/admin/report-schedules', scheduleSchema, jsonBody('POST', body));
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ['report-schedules'] }),
  });
}
