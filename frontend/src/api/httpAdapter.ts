import { z } from 'zod';

import type { DataAdapter } from './adapter';
import { apiJson } from './client';
import {
  PERIOD_KINDS,
  REVISION_STATUSES,
  type Commodity,
  type DataMode,
  type SectionCode,
  type Series,
  type SeriesResponse,
} from '@/domain/types';

/**
 * Adapter for the OSRIP FastAPI service. Responses are validated at runtime
 * with zod so a contract drift fails loudly instead of rendering wrong labels.
 * Values stay decimal strings end to end; null stays null (never 0).
 */

const dataMode = z.enum(['verified_source', 'synthetic']);

const observationSchema = z.object({
  period_start: z.string(),
  period_end: z.string(),
  period_complete: z.boolean(),
  value: z.string().nullable(),
  quality_status: z.enum(['accepted', 'warning', 'withheld']),
  source_row: z.string(),
  record_ref: z.string().nullish(),
  revision_status: z.enum(REVISION_STATUSES).nullish(),
  value_operator: z.enum(['>', '>=', '<', '<=', '~']).nullish(),
  source_locator: z.string().nullish(),
  statement_date: z.string().nullish(),
  note: z.string().nullish(),
  original_value: z.string().nullish(),
  original_unit: z.string().nullish(),
  conversion_factor: z.string().nullish(),
});

const seriesSchema = z.object({
  indicator: z.object({
    code: z.string(),
    section: z.enum(['electricity', 'water', 'food_security', 'trade']),
    value_type: z.enum(['period_total', 'average', 'maximum', 'end_of_period', 'cumulative_to_date']),
    name_en: z.string(),
    name_ar: z.string(),
    definition_en: z.string(),
    definition_ar: z.string(),
    limitation_en: z.string(),
    limitation_ar: z.string(),
    parent_code: z.string().nullish(),
  }),
  area: z.object({
    code: z.string(),
    name_en: z.string(),
    name_ar: z.string(),
    level: z.string().optional(),
  }),
  unit: z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() }),
  frequency: z.enum(['annual', 'quarterly', 'monthly', 'statement']),
  period_kind: z.enum(PERIOD_KINDS).optional(),
  ytd_end_month: z.number().int().nullish(),
  commodity: z.object({ code: z.string() }).nullable(),
  partner: z
    .object({
      code: z.string(),
      is_fictional: z.boolean(),
      name_en: z.string().optional(),
      name_ar: z.string().optional(),
    })
    .nullable(),
  flow: z.enum(['import', 'domestic_export', 're_export']).nullable(),
  data_mode: dataMode,
  source: z.object({
    dataset_title: z.string(),
    publisher: z.string().nullable(),
    url: z.string().nullable(),
    access_date: z.string().nullable(),
    reference_period: z.string().nullable(),
    geographic_coverage: z.string(),
    reuse_conditions: z.string().nullable(),
    source_code: z.string().nullish(),
    source_role: z.string().nullish(),
  }),
  dataset_version: z.object({ label: z.string(), published_at: z.string().nullable() }),
  observations: z.array(observationSchema),
});

const observationsResponse = z.object({
  status: z.enum(['ok', 'no_published_data']),
  data_mode: dataMode,
  series: z.array(seriesSchema),
});

const commoditiesResponse = z.array(
  z.object({
    code: z.string(),
    name_en: z.string(),
    name_ar: z.string(),
    mapping_status: z.enum(['provisional', 'reviewed', 'withdrawn']),
    synthetic_only: z.boolean(),
  }),
);

function toSeries(s: z.infer<typeof seriesSchema>): Series {
  return {
    indicatorCode: s.indicator.code,
    section: s.indicator.section,
    name: { en: s.indicator.name_en, ar: s.indicator.name_ar },
    definition: { en: s.indicator.definition_en, ar: s.indicator.definition_ar },
    unit: { code: s.unit.code, label: { en: s.unit.label_en, ar: s.unit.label_ar } },
    valueType: s.indicator.value_type,
    // The period kind separates full years from year-to-date totals; older servers send
    // only the frequency.
    frequency: s.period_kind ?? s.frequency,
    ytdEndMonth: s.ytd_end_month ?? null,
    parentCode: s.indicator.parent_code ?? null,
    area: {
      code: s.area.code,
      name: { en: s.area.name_en, ar: s.area.name_ar },
      level: s.area.level,
    },
    limitation: s.indicator.limitation_en
      ? { en: s.indicator.limitation_en, ar: s.indicator.limitation_ar }
      : null,
    commodityCode: s.commodity?.code ?? null,
    flow: s.flow,
    partnerCode: s.partner?.code ?? null,
    partnerName:
      s.partner && !s.partner.is_fictional && s.partner.name_en
        ? { en: s.partner.name_en, ar: s.partner.name_ar ?? s.partner.name_en }
        : null,
    dataMode: s.data_mode,
    source: {
      title: s.source.dataset_title,
      publisher: s.source.publisher,
      url: s.source.url,
      versionLabel: s.dataset_version.label,
      accessDate: s.source.access_date,
      referencePeriod: s.source.reference_period,
      geographicCoverage: s.source.geographic_coverage,
      reuseConditions: s.source.reuse_conditions,
      publishedAt: s.dataset_version.published_at,
      sourceCode: s.source.source_code ?? null,
      sourceRole: s.source.source_role ?? null,
    },
    note: null,
    observations: s.observations.map((o) => ({
      periodStart: o.period_start,
      periodEnd: o.period_end,
      periodComplete: o.period_complete,
      value: o.value,
      qualityStatus: o.quality_status,
      sourceRow: o.source_row,
      recordRef: o.record_ref ?? null,
      revisionStatus: o.revision_status ?? null,
      valueOperator: o.value_operator ?? null,
      sourceLocator: o.source_locator ?? null,
      statementDate: o.statement_date ?? null,
      note: o.note ?? null,
      originalValue: o.original_value ?? null,
      originalUnit: o.original_unit ?? null,
      conversionFactor: o.conversion_factor ?? null,
    })),
  };
}

export function createHttpAdapter(): DataAdapter {
  return {
    kind: 'http',

    async getSeries(section: SectionCode, mode: DataMode, frequency?: string): Promise<SeriesResponse> {
      const params = new URLSearchParams({ data_mode: mode, section });
      // A period kind, so a year-to-date total is selectable apart from the full year.
      if (frequency) params.set('period_kind', frequency);
      const body = await apiJson(`/observations?${params.toString()}`, observationsResponse);
      if (body.status === 'no_published_data') {
        return { status: 'no_published_data', dataMode: mode, reason: 'no_verified_source_data' };
      }
      return { status: 'ok', dataMode: body.data_mode, series: body.series.map(toSeries) };
    },

    async getCommodities(mode: DataMode): Promise<readonly Commodity[]> {
      const body = await apiJson(`/commodities?data_mode=${mode}`, commoditiesResponse);
      return body.map((c) => ({
        code: c.code,
        name: { en: c.name_en, ar: c.name_ar },
        mappingStatus: c.mapping_status,
        syntheticOnly: c.synthetic_only,
      }));
    },
  };
}
