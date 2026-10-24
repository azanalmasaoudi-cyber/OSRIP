import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson } from './client';
import { adapterKind, apiBaseUrl } from './config';
import type { DataMode } from '@/domain/types';

/**
 * Chronological series of one indicator (backend app/domain/timeline.py): rows in time order
 * for a monthly, quarterly or annual view. Published values are shown as published; a quarter
 * or year is derived from its months only by the indicator's value type and only when every
 * component is published; missing periods stay empty (never zero); year-to-date totals are
 * kept apart. The table, the chart and the CSV download are all drawn from these rows.
 */

export const VIEWS = ['annual', 'quarterly', 'monthly'] as const;
export type SeriesView = (typeof VIEWS)[number];

const text = z.object({ en: z.string(), ar: z.string() });
const reason = z.object({ code: z.string(), en: z.string(), ar: z.string() }).nullable();
const source = z.object({
  id: z.string().nullable().optional(),
  dataset_title: z.string().nullable().optional(),
  publisher: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  source_code: z.string().nullable().optional(),
  access_date: z.string().nullable().optional(),
  reference_period: z.string().nullable().optional(),
}).passthrough();
const change = z.object({
  basis: z.enum(['month_on_month', 'quarter_on_quarter', 'year_on_year']),
  against: z.string().nullable(),
  absolute: z.string().nullable(),
  percent: z.string().nullable(),
  status: z.string(),
  reason: reason.optional(),
});
export type SeriesChange = z.infer<typeof change>;

export const NATURES = ['observed', 'provisional', 'estimate', 'derived', 'missing', 'forecast'] as const;
const row = z.object({
  period_start: z.string(),
  period_end: z.string(),
  frequency: z.string(),
  value: z.string().nullable(),
  value_operator: z.string().nullable(),
  nature: z.enum(NATURES),
  status: z.string(),
  basis: z.string().nullable(),
  revision_status: z.string().nullable(),
  source: source.nullable(),
  dataset_version: z.object({ id: z.string().nullable().optional(), label: z.string().nullable().optional(),
    published_at: z.string().nullable().optional() }).passthrough().nullable(),
  record_ref: z.string().nullable(),
  locator: z.string().nullable(),
  components: z.array(z.string()),
  other_publications: z.array(z.object({ value: z.string().nullable(), revision_status: z.string().nullable().optional(),
    source: source.nullable().optional() }).passthrough()),
  revised: z.boolean(),
  reason,
  changes: z.array(change),
  interval: z.record(z.string(), z.string().nullable()).nullable(),
});
export type SeriesRow = z.infer<typeof row>;

const point = z.object({ period_start: z.string(), period_end: z.string(), value: z.string().nullable(),
  value_operator: z.string().nullable(), nature: z.string() });
/** The selected range in a few figures, calculated by the server from the table's own rows. */
const summarySchema = z.object({
  periods: z.number(),
  with_value: z.number(),
  missing: z.number(),
  first: point.nullable(),
  last: point.nullable(),
  change: change.extend({ basis: z.string() }).nullable(),
  highest: point.nullable(),
  lowest: point.nullable(),
  total: z.string().nullable(),
  total_reason: reason,
});
export type TimelineSummary = z.infer<typeof summarySchema>;

const timelineSchema = z.object({
  status: z.enum(['ok', 'no_published_data', 'needs_selection']),
  indicator: z.object({ code: z.string(), section: z.string(), value_type: z.string(), name: text, definition: text, limitation: text }),
  sector: z.string(),
  area: z.string(),
  view: z.enum(VIEWS),
  data_mode: z.string(),
  unit: z.object({ code: z.string(), label: text }).optional(),
  other_units: z.array(z.string()).optional(),
  options: z.array(z.object({ commodity: z.string().nullable(), partner: z.string().nullable(), flow: z.string().nullable() })).optional(),
  available_views: z.array(z.enum(VIEWS)),
  rows: z.array(row),
  year_to_date: z.array(row),
  forecast: z.object({ run_id: z.string(), model: z.string().nullable().optional(), training_cutoff: z.string().nullable().optional(),
    label: z.unknown().optional() }).passthrough().nullable().optional(),
  rules: z.array(z.object({ code: z.string(), en: z.string(), ar: z.string() })),
  sources: z.array(source),
  summary: summarySchema.optional(),
  dataset_id: z.string().optional(),
  label: z.string().nullable().optional(),
});
export type Timeline = z.infer<typeof timelineSchema>;

/** Periods of each view that have a value, per indicator, area and breakdown (backend
 * app/services/timeline.availability): the period selectors offer only these. */
const span = z.object({ start: z.string(), end: z.string() });
const named = z.object({ code: z.string(), name: text }).nullable();
const availabilitySeries = z.object({
  area: z.object({ code: z.string(), level: z.string().nullable().optional(), name: text }),
  commodity: named,
  partner: named,
  flow: z.string().nullable(),
  unit: z.object({ code: z.string(), label: text }),
  views: z.object({ annual: z.array(span), quarterly: z.array(span), monthly: z.array(span) }),
  year_to_date: z.array(span),
});
export type AvailabilitySeries = z.infer<typeof availabilitySeries>;
const availabilitySchema = z.object({
  section: z.string(),
  data_mode: z.string(),
  indicators: z.array(z.object({
    code: z.string(),
    name: text,
    definition: text,
    value_type: z.string(),
    series: z.array(availabilitySeries),
  })),
  label: z.string().nullable().optional(),
});
export type Availability = z.infer<typeof availabilitySchema>;
export type AvailableIndicator = Availability['indicators'][number];

export function useAvailability(section: string, mode: DataMode) {
  return useQuery({
    queryKey: ['series-availability', section, mode],
    queryFn: () => apiJson(`/series/availability?${new URLSearchParams({ data_mode: mode, section }).toString()}`, availabilitySchema),
    enabled: adapterKind === 'http',
    retry: 1,
    staleTime: 5 * 60_000,
  });
}

export interface TimelineQuery {
  dataMode: DataMode;
  indicator: string;
  area?: string;
  view: SeriesView;
  periodFrom?: string | null;
  periodTo?: string | null;
  commodity?: string | null;
  partner?: string | null;
  flow?: string | null;
  includeForecast?: boolean;
}

function search(q: TimelineQuery, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ data_mode: q.dataMode, indicator: q.indicator, area: q.area ?? 'OM', view: q.view, ...extra });
  if (q.periodFrom) params.set('period_from', q.periodFrom);
  if (q.periodTo) params.set('period_to', q.periodTo);
  if (q.commodity) params.set('commodity', q.commodity);
  if (q.partner) params.set('partner', q.partner);
  if (q.flow) params.set('flow', q.flow);
  return params.toString();
}

export function useTimeline(q: TimelineQuery | null) {
  return useQuery({
    queryKey: ['timeline', q],
    queryFn: () => apiJson(`/series/timeline?${search(q as TimelineQuery, q?.includeForecast ? { include_forecast: 'true' } : {})}`, timelineSchema),
    enabled: adapterKind === 'http' && q !== null && Boolean(q.indicator),
    retry: false,
  });
}

/** The CSV with the same rows as the table and chart (a plain download link). */
export function timelineCsvUrl(q: TimelineQuery, language: 'en' | 'ar'): string {
  return `${apiBaseUrl}/series/timeline.csv?${search(q, { language })}`;
}

/** The previous-period change of a row, and the change on the same period a year earlier. */
export function changesOf(r: SeriesRow): { previous: SeriesChange | null; yearAgo: SeriesChange | null } {
  const previous = r.changes.find((c) => c.basis === 'month_on_month' || c.basis === 'quarter_on_quarter') ?? null;
  const yearAgo = r.changes.find((c) => c.basis === 'year_on_year') ?? null;
  return { previous, yearAgo };
}
