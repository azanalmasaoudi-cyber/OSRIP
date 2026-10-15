import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson, jsonBody } from './client';
import { adapterKind } from './config';
import type { DataMode } from '@/domain/types';

/** Forecast eligibility and recorded experiments. The API does every calculation. */

const text = z.object({ en: z.string(), ar: z.string() });
const reason = text.extend({ code: z.string() });

const seriesSchema = z.object({
  series_id: z.string(),
  indicator: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
  unit: z.object({ code: z.string(), label_en: z.string(), label_ar: z.string() }),
  frequency: z.string(),
  area: z.object({ code: z.string(), name_en: z.string(), name_ar: z.string() }),
  commodity: z.string().nullable(),
  partner: z.string().nullable(),
  flow: z.string().nullable(),
  dataset_version: z.object({ id: z.string(), label: z.string() }),
  source_title: z.string(),
});
export type ForecastSeries = z.infer<typeof seriesSchema>;

const methodSchema = z.object({
  code: z.string(),
  version: z.string(),
  policies: z.record(z.string(), z.object({ min_training: z.number(), test_size: z.number(), horizon: z.number() })),
  baseline: reason,
  candidate: reason,
  splits: text,
  interval: reason,
  metrics: text,
});
export type ForecastMethod = z.infer<typeof methodSchema>;

const eligibilitySchema = z.object({
  data_mode: z.enum(['verified_source', 'synthetic']),
  label: z.string(),
  status: z.enum(['available', 'unavailable']),
  summary: reason.nullable(),
  demonstration_only: z.boolean(),
  demonstration_label: text.nullable(),
  method: methodSchema,
  series: z.array(
    seriesSchema.extend({
      usable_observations: z.number(),
      first_period: z.string().nullable(),
      last_period: z.string().nullable(),
      eligible: z.boolean(),
      reasons: z.array(reason),
      notes: z.array(reason),
    }),
  ),
});
export type ForecastEligibility = z.infer<typeof eligibilitySchema>;

const runSummary = z.object({
  id: z.string(),
  data_mode: z.enum(['verified_source', 'synthetic']),
  status: z.enum(['succeeded', 'withheld', 'failed']),
  status_reason: z.string().nullable(),
  method_code: z.string(),
  method_version: z.string(),
  series: seriesSchema.nullable(),
  demonstration_only: z.boolean(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
});
export type ForecastRunSummary = z.infer<typeof runSummary>;

const prediction = z.object({
  model: z.enum(['baseline_last_value', 'candidate_linear_trend', 'candidate_seasonal_naive']),
  fold: z.number(),
  horizon_steps: z.number(),
  training_start: z.string(),
  training_end: z.string(),
  training_size: z.number(),
  target_period_start: z.string(),
  target_period_end: z.string(),
  predicted: z.string(),
  actual: z.string(),
  error: z.string(),
  interval_lower: z.string().nullable(),
  interval_upper: z.string().nullable(),
});
export type ForecastPrediction = z.infer<typeof prediction>;

const runDetail = runSummary.extend({
  label: z.string(),
  demonstration_label: text.nullable(),
  definition: z.record(z.string(), z.unknown()),
  method: methodSchema,
  predictions: z.array(prediction),
  metrics: z.record(z.string(), z.object({ n: z.number(), mae: z.string(), rmse: z.string() })),
  comparison: z
    .object({ same_dates: z.boolean(), n: z.number(), candidate_improves_mae: z.boolean(), en: z.string(), ar: z.string() })
    .nullable(),
});
export type ForecastRun = z.infer<typeof runDetailFull>;

export function useForecastEligibility(mode: DataMode) {
  return useQuery({
    queryKey: ['forecast-eligibility', mode],
    queryFn: () => apiJson(`/forecast/eligibility?data_mode=${mode}`, eligibilitySchema),
    enabled: adapterKind === 'http',
  });
}

export function useForecastRuns(mode: DataMode) {
  return useQuery({
    queryKey: ['forecast-runs', mode],
    queryFn: () => apiJson(`/forecast-runs?data_mode=${mode}`, z.array(runSummary)),
    enabled: adapterKind === 'http',
  });
}

export function useForecastRun(id: string | null) {
  return useQuery({
    queryKey: ['forecast-run', id],
    queryFn: () => apiJson(`/forecast-runs/${id}`, runDetailFull),
    enabled: adapterKind === 'http' && id !== null,
    retry: false,
  });
}

export function useRunForecast() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { data_mode: DataMode; series_id: string }) =>
      apiJson('/forecast-runs', runDetailFull, jsonBody('POST', body)),
    onSuccess: (run) => client.setQueryData(['forecast-run', run.id], run),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['forecast-runs'] });
      void client.invalidateQueries({ queryKey: ['forecast-overview'] });
    },
  });
}

// ------------------------------------------------------------------ overview, future estimates, scenarios

const outputSchema = z.object({
  step: z.number(),
  period_start: z.string(),
  period_end: z.string(),
  estimate: z.string(),
  lower80: z.string().nullable(),
  upper80: z.string().nullable(),
  lower95: z.string().nullable(),
  upper95: z.string().nullable(),
});
export type ForecastOutput = z.infer<typeof outputSchema>;

export const runFutureSchema = z.object({
  selected_model: z.string().nullable(),
  model_names: z.record(z.string(), text),
  outputs: z.array(outputSchema),
  interval_method: reason.nullable(),
  history: z.array(z.object({ period_start: z.string(), period_end: z.string(), value: z.string().nullable() })),
  training_cutoff: z.string().nullable(),
  explanation: text.nullable(),
  assumptions: z.object({ en: z.array(z.string()), ar: z.array(z.string()) }),
  estimate_label: text,
});
export type RunFuture = z.infer<typeof runFutureSchema>;
// Declared after its parts; used only inside hooks, which run after the module has loaded.
const runDetailFull = runDetail.extend(runFutureSchema.shape);

const overviewSeries = seriesSchema.extend({
  usable_observations: z.number(),
  first_period: z.string().nullable(),
  last_period: z.string().nullable(),
  eligible: z.boolean(),
  reasons: z.array(reason),
  latest_run_id: z.string().nullable(),
});
export type OverviewSeries = z.infer<typeof overviewSeries>;

const overviewSchema = z.object({
  data_mode: z.enum(['verified_source', 'synthetic']),
  label: z.string(),
  demonstration_label: text.nullable(),
  insufficient_label: text,
  method: methodSchema,
  targets: z.array(z.object({
    group: z.enum(['electricity', 'water', 'food_security', 'trade']),
    indicator: z.string(),
    flow: z.string().nullable(),
    status: z.enum(['available', 'insufficient_data']),
    series: z.array(overviewSeries),
  })),
});
export type ForecastOverview = z.infer<typeof overviewSchema>;

export function useForecastOverview(mode: DataMode) {
  return useQuery({
    queryKey: ['forecast-overview', mode],
    queryFn: () => apiJson(`/forecast/overview?data_mode=${mode}`, overviewSchema),
    enabled: adapterKind === 'http',
  });
}

const conditionSchema = z.object({
  code: z.string(),
  name: text,
  evidence_needed: text,
  note: text.nullable(),
  candidate_indicators: z.array(z.string()),
  // measured: a published compatible series exists; otherwise only a stated scenario assumption.
  status: z.enum(['measured', 'scenario_assumption']),
  measured_by: z.array(z.object({ indicator: z.string(), observations: z.number(), last_period: z.string() })),
});
export type DevelopmentCondition = z.infer<typeof conditionSchema>;

const conditionsSchema = z.object({
  data_mode: z.enum(['verified_source', 'synthetic']),
  explanation: text,
  insufficient_label: text,
  domains: z.record(z.enum(['electricity', 'water', 'food_security', 'trade']), z.array(conditionSchema)),
});
export type DevelopmentConditions = z.infer<typeof conditionsSchema>;

/** Candidate development conditions per domain (research candidates, not proven causes). */
export function useForecastConditions(mode: DataMode) {
  return useQuery({
    queryKey: ['forecast-conditions', mode],
    queryFn: () => apiJson(`/forecast/conditions?data_mode=${mode}`, conditionsSchema),
    enabled: adapterKind === 'http',
    staleTime: 5 * 60 * 1000,
  });
}

const scenarioSeries = seriesSchema.extend({
  base: z.object({ period_start: z.string(), period_end: z.string(), value: z.string().nullable() }).passthrough(),
});
export type ScenarioSeries = z.infer<typeof scenarioSeries>;

const projectionSchema = z.object({
  kind: z.literal('hypothetical_scenario'),
  label: text,
  data_mode: z.enum(['verified_source', 'synthetic']),
  series: seriesSchema,
  base: z.object({
    period_start: z.string(), period_end: z.string(), value: z.string(),
    source: z.object({ title: z.string(), publisher: z.string().nullable(), url: z.string().nullable() }),
    dataset_version: z.string(),
  }).passthrough(),
  assumptions: z.object({ growth_pct: z.string(), years: z.number(), one_off_pct: z.string() }),
  formula: text,
  points: z.array(z.object({ step: z.number(), year: z.number(), value: z.string() })),
});
export type Projection = z.infer<typeof projectionSchema>;

export function useScenarioSeries(mode: DataMode) {
  return useQuery({
    queryKey: ['scenario-series', mode],
    queryFn: () => apiJson(`/scenarios/series?data_mode=${mode}`, z.array(scenarioSeries)),
    enabled: adapterKind === 'http',
  });
}

export function useProjection(mode: DataMode, seriesId: string | null, growth: number, years: number, oneOff: number) {
  const params = new URLSearchParams({
    data_mode: mode, series_id: seriesId ?? '', growth_pct: String(growth), years: String(years), one_off_pct: String(oneOff),
  });
  return useQuery({
    queryKey: ['projection', mode, seriesId, growth, years, oneOff],
    queryFn: () => apiJson(`/scenarios/projection?${params.toString()}`, projectionSchema),
    enabled: adapterKind === 'http' && seriesId !== null,
    placeholderData: (previous) => previous,
  });
}
