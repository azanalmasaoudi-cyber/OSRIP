import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';
import { checkTableAndCharts } from './studyEvents';
import type { DataMode } from '@/domain/types';

/**
 * Shortage and surplus analysis (backend app/services/analysis/balance.py, osrip.balance/1).
 * The server does every calculation and validates the document; the interface checks the
 * tables and charts again with the same rules and only displays them. Missing values are null,
 * never zero.
 */

export const SECTORS = ['electricity', 'water', 'food_security', 'trade'] as const;
export type Sector = (typeof SECTORS)[number];

const text = z.object({ en: z.string(), ar: z.string() });
const unit = z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() });
const nature = z.enum(['observed', 'calculated', 'forecast', 'scenario']);
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
const table = z.object({ columns: z.array(column), rows: z.array(z.record(z.string(), z.string().nullable())) });

export const BALANCE_STATUSES = ['surplus', 'shortfall', 'balanced', 'not_determinable'] as const;

const balance = z.object({
  id: z.string(),
  code: z.string(),
  title: text,
  status: z.enum(BALANCE_STATUSES),
  status_label: text,
  reason: text,
  interpretation: text,
  period: z.string().nullable().optional(),
  period_kind: z.string().nullable().optional(),
  gap: z.string().nullable().optional(),
  gap_unit: unit.nullable().optional(),
  gap_share: z.string().nullable().optional(),
  supply_label: text.nullable().optional(),
  demand_label: text.nullable().optional(),
  table,
  charts: z.array(chart),
  evidence: z.array(z.string()),
  constraints: z.array(text),
  notes: z.array(text),
}).superRefine((b, ctx) => {
  const problem = checkTableAndCharts(b.table, b.charts);
  if (problem) ctx.addIssue({ code: 'custom', message: problem });
});
export type Balance = z.infer<typeof balance>;

export const PRIORITIES = ['high', 'medium', 'low', 'conditional'] as const;
/** What kind of response a recommendation is (shortfall: efficiency, loss reduction,
 * redistribution, storage, capacity, suppliers; surplus: storage, local use, redistribution,
 * processing, exports only where feasible; and data improvement or monitoring). */
export const OPTION_KINDS = [
  'efficiency', 'loss_reduction', 'redistribution', 'storage', 'capacity_expansion', 'supplier_diversification',
  'local_use', 'processing', 'export', 'data_improvement', 'monitoring',
] as const;
export type OptionKind = (typeof OPTION_KINDS)[number];
const recommendation = z.object({
  id: z.string(),
  balance: z.string().nullable().optional(),
  problem: text,
  evidence: text,
  evidence_ids: z.array(z.string()),
  action: text,
  quantity: z.string().nullable().optional(),
  quantity_unit: unit.nullable().optional(),
  quantity_note: text,
  horizon: z.enum(['short', 'medium', 'long']),
  constraints: text,
  cost: text,
  cost_known: z.literal(false),
  outcome: text,
  priority: z.enum(PRIORITIES),
  priority_basis: text,
  kpi: text,
  nature: z.enum(['recommendation', 'data_improvement', 'conditional_option']),
  option: z.enum(OPTION_KINDS).nullable().optional(),
});
export type BalanceRecommendation = z.infer<typeof recommendation>;

const source = z.object({
  id: z.string(),
  indicator: z.string(),
  indicator_name: text,
  area: z.string(),
  area_name: text,
  period_start: z.string(),
  period_end: z.string(),
  period_label: z.string(),
  period_kind: z.string(),
  value: z.string().nullable(),
  value_operator: z.string().nullable().optional(),
  unit,
  publisher: z.string().nullable().optional(),
  title: z.string(),
  url: z.string().nullable().optional(),
  publication: z.string().nullable().optional(),
  accessed: z.string().nullable().optional(),
  dataset_version: z.string(),
  record_ref: z.string().nullable().optional(),
  data_status: z.enum(['approved_official', 'synthetic_demonstration']),
  older_context: z.boolean(),
});
export type BalanceSource = z.infer<typeof source>;

export const analysisSchema = z.object({
  schema: z.literal('osrip.balance/1'),
  kind: z.literal('supply_balance'),
  sector: z.enum(SECTORS),
  status: z.enum(['ok', 'partial', 'not_available']),
  title: text,
  question: text,
  params: z.record(z.string(), z.unknown()),
  data_mode: z.enum(['verified_source', 'synthetic']),
  dataset_versions: z.array(z.string()),
  summary: z.array(text),
  balances: z.array(balance),
  recommendations: z.array(recommendation),
  prioritization: text,
  data_gaps: z.array(z.object({
    id: z.string(), balance: z.string().nullable().optional(), missing: text, blocks: text, where: text.nullable().optional(),
  })),
  scenario: z.object({
    status: z.enum(['ok', 'not_applicable', 'not_requested']),
    reason: text.nullable().optional(),
    assumptions: z.array(text).default([]),
    balance: z.string().nullable().optional(),
    table: table.nullable().optional(),
    charts: z.array(chart).default([]),
  }),
  forecast: z.object({ status: z.enum(['eligible', 'withheld', 'not_available']), indicator: z.string().nullable().optional(), text }),
  sources: z.array(source),
  method: text,
  assumptions: z.array(text),
  limitations: z.array(text),
  // How every study ends (analyses stored before 2026-10-21 have none).
  conclusion: z.object({
    main_findings: z.array(z.object({ text, evidence: z.array(z.string()), balance: z.string().nullable().optional() })),
    evidence_limitations: z.array(text),
    immediate_actions: z.array(z.string()),
    medium_term_options: z.array(z.string()),
    next_study: z.array(z.object({ question: text, data: text, where: text.nullable().optional() })),
  }).nullable().optional(),
  generated_by: z.literal('deterministic'),
});
export type BalanceAnalysis = z.infer<typeof analysisSchema>;

const storedSchema = z.object({ id: z.string(), created_at: z.string().nullable(), sha256: z.string(), analysis: analysisSchema });
export type StoredBalance = z.infer<typeof storedSchema>;

export interface BalanceParams {
  sector: Sector;
  period_kind?: 'annual' | 'year_to_date';
  supply_growth_pct?: string;
  demand_growth_pct?: string;
  years?: number;
}

export function useRunBalance() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { data_mode: DataMode; params: BalanceParams }) =>
      apiJson('/analysis/balance', storedSchema, jsonBody('POST', body)),
    onSuccess: (stored) => client.setQueryData(['balance', stored.id], stored),
  });
}

export function useBalance(id: string | null) {
  return useQuery({
    queryKey: ['balance', id],
    queryFn: () => apiJson(`/analysis/balance/${id ?? ''}`, storedSchema),
    enabled: adapterKind === 'http' && Boolean(id),
    retry: false,
  });
}

/** The exact words the voice reads for an analysis (shown as its transcript). */
export async function spokenText(id: string, language: 'en' | 'ar'): Promise<string> {
  const out = await apiJson(`/analysis/balance/${id}/spoken?language=${language}`, z.object({ text: z.string() }));
  return out.text;
}

/** Downloads are plain GET links served with Content-Disposition by the API. */
export function balanceExportUrl(id: string, format: 'csv' | 'html', language: 'en' | 'ar'): string {
  return `${apiBaseUrl}/analysis/balance/${id}/${format === 'csv' ? 'export.csv' : 'report.html'}?language=${language}`;
}
