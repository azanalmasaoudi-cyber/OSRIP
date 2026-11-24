import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { adapterKind } from './config';
import type { DataMode, SectionCode } from '@/domain/types';
import { OBJECTIVES, type Objective } from '@/lib/guideSteps';

/**
 * The guided analysis's last step: rule-based recommendations for the applied selection once its
 * objectives are known (POST /analysis/{section}/guidance). The server quotes only figures from
 * the selection's published timeline; nothing is stored and no AI is used.
 */

export { OBJECTIVES, type Objective };

const text = z.object({ en: z.string(), ar: z.string() });
const named = z.object({ code: z.enum(OBJECTIVES), name: text });

const guidanceSchema = z.object({
  status: z.enum(['ok', 'no_data', 'needs_objectives']),
  rules_version: z.string(),
  objectives: z.array(named),
  note_recognised: z.boolean(),
  facts: z.array(z.object({ id: z.string(), kind: z.string(), text })),
  actions: z.array(z.object({
    rank: z.number(),
    objective: named.nullable(),
    title: text,
    rationale: text,
    facts: z.array(z.string()),
    prerequisites: z.array(text),
    risks: z.array(text),
    missing_evidence: z.array(text),
    evidence: z.enum(['trend', 'single_value', 'gap']),
  })),
  missing_evidence: z.array(text),
  limitations: z.array(text),
});
export type Guidance = z.infer<typeof guidanceSchema>;

export interface GuidanceRequest {
  section: SectionCode;
  mode: DataMode;
  indicator: string;
  area: string;
  view: 'annual' | 'quarterly' | 'monthly';
  commodity?: string;
  partner?: string;
  flow?: string;
  periodFrom: string;
  periodTo: string;
  objectives: readonly Objective[];
  note: string;
}

/** Fetched once per selection and objectives; going back and forth reuses the answer. */
export function useGuidance(request: GuidanceRequest | null) {
  return useQuery({
    queryKey: ['guidance', request],
    queryFn: () => {
      const r = request!;
      return apiJson(`/analysis/${r.section}/guidance`, guidanceSchema, jsonBody('POST', {
        data_mode: r.mode, indicator: r.indicator, area: r.area, view: r.view,
        commodity: r.commodity || null, partner: r.partner || null, flow: r.flow || null,
        period_from: r.periodFrom || null, period_to: r.periodTo || null, objectives: r.objectives, note: r.note,
      }));
    },
    enabled: adapterKind === 'http' && request !== null,
    staleTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}
