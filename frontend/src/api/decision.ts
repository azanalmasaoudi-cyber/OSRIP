import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson } from './client';
import { adapterKind } from './config';
import type { DataMode, SectionCode } from '@/domain/types';

const bi = z.object({ en: z.string(), ar: z.string() });
const named = z.object({ code: z.string(), name: bi });
const point = z.object({ value: z.string(), period: bi, end: z.string() });

const performance = z.object({
  id: z.string(), indicator: named, measure: z.string().nullable(), kind: z.string(), unit: bi,
  current: point, previous: point, change_pct: z.string(), direction: z.enum(['up', 'down', 'flat']),
  refs: z.array(z.string()),
});
const finding = z.object({ id: z.string(), kind: z.string(), text: bi, rule: bi, refs: z.array(z.string()) });
const balanceItem = z.object({
  indicator: named, value: z.string(), unit: bi, period: bi, gap: z.string(), refs: z.array(z.string()),
});
const tradeItem = z.object({
  kind: z.enum(['balance', 'group']), value: z.string().optional(), net: z.string().optional(),
  exports: z.object({ code: z.string(), name: bi, value: z.string() }).optional(),
  imports: z.object({ code: z.string(), name: bi, value: z.string() }).optional(),
  unit: bi, period: bi, refs: z.array(z.string()),
});
const composition = z.object({
  parent: named, total: z.string(), unit: bi, period: bi, refs: z.array(z.string()),
  parts: z.array(z.object({ indicator: named, value: z.string(), share_pct: z.string(), ref: z.string() })),
});
const regional = z.object({
  indicator: named, unit: bi, period: bi, national: z.string().nullable(), national_ref: z.string().nullable(),
  areas: z.array(z.object({
    area: z.object({ code: z.string(), level: z.string(), name: bi }),
    value: z.string(), share_pct: z.string().nullable(), ref: z.string(),
  })),
});
const gap = z.object({
  kind: z.enum(['not_published', 'stale', 'statement_only', 'regional']),
  indicator: named.optional(), latest: z.string().optional(), covered: z.number().optional(), of: z.number().optional(),
});
const provenance = z.object({
  ref: z.string(), indicator: z.string(), indicator_name: bi, area: z.string(),
  period_start: z.string(), period_end: z.string(), value: z.string().nullable(), unit: bi.nullable(),
  source_title: z.string(), source_url: z.string().nullable().optional(), source_locator: z.string().nullable().optional(),
  record_ref: z.string().nullable().optional(), dataset_version: z.string(), published_at: z.string().nullable(),
  quality_status: z.string().nullable().optional(), revision_status: z.string().nullable().optional(),
});

const briefSchema = z.object({
  section: z.string(), data_mode: z.string(), version: z.string(), generated_at: z.string(),
  performance: z.array(performance), movers: z.array(z.string()), composition: z.array(composition),
  strengths: z.array(finding), weaknesses: z.array(finding),
  balance: z.object({ surplus: z.array(balanceItem), shortage: z.array(balanceItem), assessable: z.boolean() }),
  trade: z.array(tradeItem), regional: z.array(regional),
  coverage: z.object({ governorates: z.array(z.string()), of: z.number() }),
  gaps: z.array(gap), risks: z.array(finding),
  scenarios: z.array(z.object({
    series_id: z.string(), indicator: named, area: bi, unit: bi, base: z.object({ value: z.string(), period: bi }),
  })),
  recommendations: z.array(z.object({ kind: z.string(), based_on: z.array(z.string()), text: bi })),
  provenance: z.array(provenance),
});
export type DecisionBrief = z.infer<typeof briefSchema>;
export type BriefFinding = z.infer<typeof finding>;

/** The decision brief of one axis, from published data only (server-built; no AI). */
export function useDecisionBrief(section: SectionCode, mode: DataMode) {
  return useQuery({
    queryKey: ['decision-brief', section, mode],
    queryFn: () => apiJson(`/analysis/${section}/brief?data_mode=${mode}`, briefSchema),
    enabled: adapterKind === 'http',
  });
}
