import { z } from 'zod';

import { apiBaseUrl } from './config';

/**
 * Live study events (backend app/services/assistant/study_events.py). The server validates
 * every event before it is written; the interface validates each one again here, and a table
 * is drawn only after its schema and values pass the same checks as on the server (unique
 * columns, a unit on every numeric column, decimal strings or null in numeric cells, charts
 * that reference only the table's own columns, one row id per row).
 */

const text = z.object({ en: z.string(), ar: z.string() });
const unit = z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() });
const nature = z.enum(['observed', 'calculated', 'forecast', 'scenario']);
export const DATA_STATUSES = [
  'approved_official', 'synthetic_demonstration', 'unreviewed_external', 'calculated',
  'model_forecast', 'assumption_scenario', 'reference',
] as const;
const dataStatus = z.enum(DATA_STATUSES);
const evidenceId = z.string().regex(/^E\d{1,4}$/);

const column = z.object({
  key: z.string().regex(/^[a-z][a-z0-9_]*$/),
  label: text,
  kind: z.enum(['text', 'period', 'number', 'status']),
  unit: unit.nullable().optional(),
});
const chart = z.object({
  type: z.enum(['line', 'bar', 'heatmap']),
  title: text,
  x: z.string(),
  series: z.array(z.object({ column: z.string(), label: text, nature })).default([]),
  y: z.string().nullable().optional(),
  value: z.string().nullable().optional(),
  unit: unit.nullable().optional(),
});
const table = z.object({
  columns: z.array(column),
  rows: z.array(z.record(z.string(), z.string().nullable())),
});

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** The table and chart rules shared with the server (app/domain/study.py). */
export function checkTableAndCharts(t: z.infer<typeof table>, charts: z.infer<typeof chart>[]): string | null {
  const keys = new Set(t.columns.map((c) => c.key));
  if (keys.size !== t.columns.length) return 'duplicate column keys';
  const numeric = new Set(t.columns.filter((c) => c.kind === 'number').map((c) => c.key));
  if (t.columns.some((c) => c.kind === 'number' && !c.unit)) return 'numeric column without unit';
  for (const row of t.rows) {
    for (const [k, v] of Object.entries(row)) {
      if (!keys.has(k)) return `unknown column ${k}`;
      if (numeric.has(k) && v !== null && !DECIMAL.test(v)) return `${k} is not a decimal`;
    }
  }
  for (const c of charts) {
    for (const ref of [c.x, ...c.series.map((s) => s.column), c.y, c.value]) {
      if (ref != null && !keys.has(ref)) return `chart references unknown column ${ref}`;
    }
    if (c.type === 'heatmap' && !(c.y && c.value)) return 'heatmap needs y and value';
    if (c.type !== 'heatmap' && c.series.length === 0) return 'chart needs a series';
  }
  return null;
}

export const datasetSchema = z.object({
  dataset_id: z.string().regex(/^D\d{1,3}$/),
  origin: z.enum(['get_observations', 'latest_period', 'compare_areas', 'run_study', 'scenario_projection', 'workspace']),
  provisional: z.boolean(),
  data_status: dataStatus,
  title: text,
  subtitle: text.nullable().optional(),
  table,
  charts: z.array(chart),
  rows_meta: z.array(z.object({ row_id: z.string().regex(/^r\d{1,4}$/), evidence_id: evidenceId.nullable().optional() })),
  evidence_ids: z.array(z.string()),
  source_evidence_id: evidenceId.nullable().optional(),
  study: z.object({
    kind: z.string(),
    status: z.string(),
    reason: text.nullable().optional(),
    findings: z.array(text),
    method: text,
    assumptions: z.array(text),
    limitations: z.array(text),
  }).nullable().optional(),
}).superRefine((d, ctx) => {
  const problem = checkTableAndCharts(d.table, d.charts);
  if (problem) ctx.addIssue({ code: 'custom', message: problem });
  if (d.rows_meta.length !== d.table.rows.length) ctx.addIssue({ code: 'custom', message: 'row ids do not match rows' });
  if (new Set(d.rows_meta.map((m) => m.row_id)).size !== d.rows_meta.length) ctx.addIssue({ code: 'custom', message: 'duplicate row ids' });
  if (d.table.rows.length === 0) ctx.addIssue({ code: 'custom', message: 'empty table' });
});
export type Dataset = z.infer<typeof datasetSchema>;

export const evidenceSchema = z.object({
  evidence_id: evidenceId,
  kind: z.enum(['observation', 'web', 'note', 'calculation', 'method', 'forecast', 'scenario', 'study']),
  data_status: dataStatus,
  title: text,
  area: text.nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  value: z.string().nullable().optional(),
  value_operator: z.string().nullable().optional(),
  unit: text.nullable().optional(),
  source: z.object({
    title: z.string().nullable().optional(),
    publisher: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    dataset_version: z.string().nullable().optional(),
    record_ref: z.string().nullable().optional(),
  }).nullable().optional(),
  source_class: z.string().nullable().optional(),
  published: z.string().nullable().optional(),
  retrieved_at: z.string().nullable().optional(),
  freshness: z.string().nullable().optional(),
  content_kind: z.string().nullable().optional(),
  summary_by: z.string().nullable().optional(),
  excerpt: z.string().nullable().optional(),
  inputs: z.array(z.string()).default([]),
  status: z.string().nullable().optional(),
});
export type StudyEvidence = z.infer<typeof evidenceSchema>;

const segment = z.object({
  narration_segment_id: z.string().regex(/^N\d{1,3}$/),
  finding_id: z.string().nullable().optional(),
  text: z.string(),
  evidence_ids: z.array(z.string()),
  targets: z.array(z.object({ dataset_id: z.string(), row_ids: z.array(z.string()) })),
  section: z.enum(['findings', 'status']),
});
export type NarrationSegment = z.infer<typeof segment>;

export const completedSchema = z.object({
  status: z.string(),
  message_id: z.number().nullable().optional(),
  language: z.enum(['en', 'ar']),
  findings: z.array(z.object({ finding_id: z.string(), text: z.string(), evidence_ids: z.array(z.string()) })),
  narration: z.array(segment),
  final_datasets: z.array(z.string()),
  provisional_datasets: z.array(z.string()),
  recommendations: z.array(z.object({
    finding: z.string(), action: z.string(), expected_benefit: z.string(), uncertainty: z.string(),
    citations: z.array(z.string()).nullable().optional(),
  })).default([]),
  assumptions: z.array(z.string()).default([]),
  method: z.record(z.string(), z.unknown()).default({}),
});
export type StudyCompletion = z.infer<typeof completedSchema>;

const envelope = z.object({
  study_id: z.string(),
  seq: z.number().int().positive(),
  type: z.string(),
  result_version: z.number().int().nonnegative(),
  at: z.string().nullable().optional(),
  payload: z.record(z.string(), z.unknown()),
});

export const eventSchema = z.discriminatedUnion('type', [
  envelope.extend({ type: z.literal('study.started'), payload: z.object({ attempt: z.number(), mode: z.string(), language: z.enum(['en', 'ar']), data_mode: z.string() }) }),
  envelope.extend({ type: z.literal('stage'), payload: z.object({ stage: z.string(), label: text }) }),
  envelope.extend({
    type: z.literal('search'),
    payload: z.object({
      evidence_id: evidenceId, status: z.string(), query: z.string().nullable().optional(), provider: z.string().nullable().optional(),
      role: z.string(), display_only: z.boolean(), result_count: z.number().nullable().optional(), error: z.string().nullable().optional(),
    }),
  }),
  envelope.extend({ type: z.literal('evidence'), payload: evidenceSchema }),
  // A dataset's payload is checked separately (datasetSchema), so a table that fails is
  // reported instead of silently breaking the whole stream.
  envelope.extend({ type: z.literal('dataset'), payload: z.record(z.string(), z.unknown()) }),
  envelope.extend({ type: z.literal('warning'), payload: z.object({ code: z.string(), detail: text, evidence_id: z.string().nullable().optional() }) }),
  envelope.extend({ type: z.literal('study.completed'), payload: completedSchema }),
  envelope.extend({ type: z.literal('study.cancelled'), payload: z.object({ reason: z.string() }) }),
  envelope.extend({ type: z.literal('study.failed'), payload: z.object({ code: z.string() }) }),
]);
export type StudyEvent = z.infer<typeof eventSchema>;
export const TERMINAL = new Set(['study.completed', 'study.cancelled', 'study.failed']);

export function studyEventsUrl(studyId: string, guest: boolean, after = 0): string {
  return `${apiBaseUrl}/assistant/${guest ? 'guest/' : ''}requests/${studyId}/events${after ? `?after=${after}` : ''}`;
}
