import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';
import type { DataMode } from '@/domain/types';

const text = z.object({ en: z.string(), ar: z.string() });

/**
 * Electricity's and water's annual indicators side by side (GET /series/annual-table): each row a
 * separate published series with the platform's own year-on-year change; empty years stay empty.
 */
const cell = z.object({
  value: z.string().nullable(),
  value_operator: z.string().nullable(),
  nature: z.string(),
  revision_status: z.string().nullable(),
  provisional: z.boolean(),
  change_percent: z.string().nullable(),
  change_absolute: z.string().nullable(),
  source: z.string().nullable(),
  locator: z.string().nullable(),
}).nullable();
const annualSchema = z.object({
  section: z.string(),
  data_mode: z.string(),
  years: z.array(z.string()),
  groups: z.array(z.object({
    code: z.string(),
    label: text,
    rows: z.array(z.object({
      indicator: z.object({ code: z.string(), name: text }),
      area: z.string(),
      unit: text.nullable(),
      status: z.string().nullable(),
      limitation: text,
      cells: z.array(cell),
    })),
  })),
  notes: z.array(text),
});
export type AnnualTable = z.infer<typeof annualSchema>;

/** The same cells as CSV, with provenance (GET /series/annual-table.csv). */
export function annualTableCsvUrl(section: 'electricity' | 'water', mode: DataMode, language: 'en' | 'ar', from = 2022, to = 2025): string {
  return `${apiBaseUrl}/series/annual-table.csv?${new URLSearchParams({ section, data_mode: mode, year_from: String(from), year_to: String(to), language }).toString()}`;
}

export function useAnnualTable(section: 'electricity' | 'water', mode: DataMode, from = 2022, to = 2025) {
  return useQuery({
    queryKey: ['annual-table', section, mode, from, to],
    queryFn: () => apiJson(`/series/annual-table?${new URLSearchParams({ section, data_mode: mode, year_from: String(from), year_to: String(to) }).toString()}`, annualSchema),
    enabled: adapterKind === 'http',
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * The official outlook (GET /outlook): forecasts, targets, plans and options from official
 * statements, each with its evidence class, kept apart from observed statistics.
 */
export const OUTLOOK_CLASSES = ['observed', 'estimate', 'forecast', 'policy_target', 'planned', 'under_consideration'] as const;
export type OutlookClass = (typeof OUTLOOK_CLASSES)[number];

export const outlookItem = z.object({
  id: z.string(),
  section: z.string(),
  metric: z.object({ code: z.string(), en: z.string(), ar: z.string() }),
  year: z.number(),
  value: z.string().nullable(),
  unit: z.object({ code: z.string(), en: z.string(), ar: z.string() }),
  scope: text,
  evidence_class: z.enum(OUTLOOK_CLASSES),
  class_label: text,
  achieved: z.boolean(),
  status_note: text.nullable(),
  source: z.object({
    title: z.string(), publisher: z.string(), url: z.string(), locator: z.string(),
    sha256: z.string().nullable(), retrieved_on: z.string(), issue_year: z.number(),
  }),
  batch: z.string(),
  review_status: z.enum(['pending', 'approved', 'rejected']),
  // Reviewers only (GET /outlook/review): when and why an item was decided; never public.
  reviewed_at: z.string().nullable().optional(),
  review_note: z.string().nullable().optional(),
});
export type OutlookItem = z.infer<typeof outlookItem>;
export type OutlookReviewStatus = OutlookItem['review_status'];
const outlookSchema = z.object({
  items: z.array(outlookItem),
  classes: z.array(z.object({ code: z.enum(OUTLOOK_CLASSES), label: text, achieved: z.boolean() })),
  note: text,
});
export type Outlook = z.infer<typeof outlookSchema>;

export function useOutlook(section: 'electricity' | 'water', enabled = true) {
  return useQuery({
    queryKey: ['outlook', section],
    queryFn: () => apiJson(`/outlook?section=${section}`, outlookSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 10 * 60 * 1000,
  });
}

/** Every staged item, pending ones included (people allowed to approve imports). */
export function useOutlookReview(enabled = true) {
  return useQuery({
    queryKey: ['outlook', 'review'],
    queryFn: () => apiJson('/outlook/review', outlookSchema),
    enabled: adapterKind === 'http' && enabled,
  });
}

/** Approve or reject one pending item (audited by the server; an item is decided once). */
export function useReviewOutlookItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: 'approved' | 'rejected'; note: string }) =>
      apiJson(`/outlook/${id}/review`, outlookItem, jsonBody('POST', { decision, note })),
    // The sectors and Al Mulhim read the approved items: refresh every outlook view.
    onSettled: () => void client.invalidateQueries({ queryKey: ['outlook'] }),
  });
}
