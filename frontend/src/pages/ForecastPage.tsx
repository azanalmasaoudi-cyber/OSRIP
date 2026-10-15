import { Ban, FlaskConical, LineChart, MessageSquareText, SlidersHorizontal, TriangleAlert } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { hasPermission, useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import {
  useForecastConditions,
  useForecastOverview,
  useForecastRun,
  useProjection,
  useRunForecast,
  useScenarioSeries,
  type DevelopmentConditions,
  type ForecastMethod,
  type ForecastOverview,
  type ForecastRun,
  type ForecastSeries,
} from '@/api/forecasting';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import {
  ConditionsPanel,
  DOMAIN_KEY,
  DOMAINS,
  ExplanationBlock,
  HistoryPanel,
  domainOf,
  evidenceNeeded,
  type Domain,
} from '@/components/forecast/DevelopmentConditions';
import { ForecastChart, ForecastTable } from '@/components/forecast/ForecastChart';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ProgressBar } from '@/components/ui/progress';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { useUrlFilter } from '@/state/useUrlFilter';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

function pick(text: { en: string; ar: string } | null | undefined, language: AppLanguage) {
  return text ? (language === 'ar' ? text.ar : text.en) : '';
}

const GROUP_KEY = {
  electricity: 'nav.electricity',
  water: 'nav.water',
  food_security: 'nav.foodSecurity',
  trade: 'nav.trade',
} as const;

function seriesLabel(s: ForecastSeries, language: AppLanguage, flowLabel: (f: string) => string) {
  return [
    language === 'ar' ? s.indicator.name_ar : s.indicator.name_en,
    language === 'ar' ? s.area.name_ar : s.area.name_en,
    s.commodity, s.flow ? flowLabel(s.flow) : null,
  ].filter(Boolean).join(' · ');
}

function useFlowLabel() {
  const { t } = useTranslation();
  return (flow: string) => (flow in FLOW_KEY ? t(FLOW_KEY[flow as keyof typeof FLOW_KEY]) : flow);
}

function DemonstrationBanner({ text }: { text: { en: string; ar: string } }) {
  const language = useAppLanguage();
  return (
    <p role="note" data-testid="forecast-demo-label"
      className="flex items-start gap-2 rounded-md border border-synthetic-border bg-synthetic px-3 py-2 text-sm font-semibold text-synthetic-foreground">
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{pick(text, language)}
    </p>
  );
}

function MethodCard({ method }: { method: ForecastMethod }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <details className="group rounded-lg border border-border bg-card p-5" data-testid="forecast-method">
      <summary className="cursor-pointer font-semibold">{t('forecasts.methodHeading')}</summary>
      <div className="expand-content mt-3 flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">{t('forecasts.methodIntro')}</p>
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]">
          <dt className="font-medium">{t('pages.forecast.splits')}</dt><dd>{pick(method.splits, language)}</dd>
          <dt className="font-medium">{t('pages.forecast.baseline')}</dt><dd>{pick(method.baseline, language)}</dd>
          <dt className="font-medium">{t('pages.forecast.candidate')}</dt><dd>{pick(method.candidate, language)}</dd>
          <dt className="font-medium">{t('forecasts.seasonal')}</dt><dd>{t('forecasts.seasonalText')}</dd>
          <dt className="font-medium">{t('forecasts.selection')}</dt><dd>{t('forecasts.selectionText')}</dd>
          <dt className="font-medium">{t('pages.forecast.interval')}</dt><dd>{pick(method.interval, language)}</dd>
          <dt className="font-medium">{t('pages.forecast.metrics')}</dt><dd>{pick(method.metrics, language)}</dd>
          <dt className="font-medium">{t('pages.forecast.missing')}</dt><dd>{t('pages.forecast.missingText')}</dd>
        </dl>
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[22rem] text-sm">
            <caption className="mb-1 text-start text-xs font-semibold">{t('pages.forecast.policyCaption')}</caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-1 text-start font-medium">{t('table.frequency')}</th>
                <th scope="col" className="py-1 text-end font-medium">{t('pages.forecast.minTraining')}</th>
                <th scope="col" className="py-1 text-end font-medium">{t('pages.forecast.heldOut')}</th>
                <th scope="col" className="py-1 text-end font-medium">{t('pages.forecast.minimum')}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(method.policies).map(([freq, p]) => (
                <tr key={freq} className="border-b border-border last:border-0">
                  <th scope="row" className="py-1 text-start font-normal">{t(`frequency.${freq as 'annual'}`)}</th>
                  <td className="py-1 text-end tabular-nums">{p.min_training}</td>
                  <td className="py-1 text-end tabular-nums">{p.test_size}</td>
                  <td className="py-1 text-end tabular-nums">{p.min_training + p.test_size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">{t('forecasts.scopeNote')} <span dir="ltr">{method.code} {method.version}</span></p>
      </div>
    </details>
  );
}

function TargetCards({ data, canRun, running, onRun, onShow, shown }: {
  data: ForecastOverview; canRun: boolean; running: string | null;
  onRun: (id: string) => void; onShow: (runId: string) => void; shown: string | null;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const flowLabel = useFlowLabel();
  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="forecast-targets">
      {data.targets.map((target) => {
        const first = target.series[0];
        const name = first ? (language === 'ar' ? first.indicator.name_ar : first.indicator.name_en) : t(`forecasts.indicator.${target.indicator as 'ELEC_CONSUMPTION'}`);
        return (
          <li key={`${target.indicator}-${target.flow ?? ''}`} className="enter-rise">
            <Card className="flex h-full flex-col gap-3 p-4" data-testid="forecast-target" data-indicator={target.indicator}
              data-flow={target.flow ?? ''} data-status={target.status}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-muted-foreground">{t(GROUP_KEY[target.group])}</p>
                  <h3 className="font-semibold">{name}{target.flow ? ` · ${flowLabel(target.flow)}` : ''}</h3>
                </div>
                {target.status === 'available'
                  ? <Badge variant="verified">{t('forecasts.enoughData')}</Badge>
                  : <Badge variant="muted">{t('forecasts.notEnough')}</Badge>}
              </div>
              {target.status === 'insufficient_data' ? (
                <div className="flex flex-col gap-1 text-sm" data-testid="insufficient">
                  <p className="flex items-center gap-1.5 font-semibold"><Ban aria-hidden="true" className="size-4 text-muted-foreground" />{pick(data.insufficient_label, language)}</p>
                  <p className="text-xs text-muted-foreground">
                    {first?.reasons[0] ? pick(first.reasons[0], language) : t('forecasts.noSeries')}
                  </p>
                </div>
              ) : null}
              <ul className="flex flex-col gap-2">
                {target.series.filter((s) => s.eligible).map((s) => (
                  <li key={s.series_id} className="flex flex-col gap-2 rounded-md border border-border p-2 text-xs">
                    <span>{seriesLabel(s, language, flowLabel)} · {t(`frequency.${s.frequency as 'annual'}`)} · {t('forecasts.observationsCount', { n: s.usable_observations })}</span>
                    <div className="flex flex-wrap gap-2">
                      {s.latest_run_id ? (
                        <Button size="sm" variant={shown === s.latest_run_id ? 'default' : 'outline'} onClick={() => onShow(s.latest_run_id ?? '')}
                          aria-pressed={shown === s.latest_run_id} data-testid="show-forecast">
                          <LineChart aria-hidden="true" />{t('forecasts.show')}
                        </Button>
                      ) : null}
                      {canRun ? (
                        <Button size="sm" variant="outline" disabled={running !== null} onClick={() => onRun(s.series_id)} data-testid="run-forecast">
                          <FlaskConical aria-hidden="true" />{s.latest_run_id ? t('forecasts.rerun') : t('forecasts.run')}
                        </Button>
                      ) : null}
                    </div>
                    {running === s.series_id ? <ProgressBar label={t('forecasts.running')} /> : null}
                  </li>
                ))}
              </ul>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function RunView({ run, conditions }: { run: ForecastRun; conditions: DevelopmentConditions | undefined }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const flowLabel = useFlowLabel();
  const s = run.series;
  const def = run.definition as { history?: { first_period: string; training_cutoff: string; observations: number }; future_horizon_steps?: number };
  const unit = s ? (language === 'ar' ? s.unit.label_ar : s.unit.label_en) : '';
  const title = s ? seriesLabel(s, language, flowLabel) : run.id;
  const modelName = (m: string) => pick(run.model_names[m], language) || m;
  const question = t('forecasts.askQuestion', { title });

  if (run.status !== 'succeeded') {
    return (
      <Card className="p-5" data-testid="forecast-run" data-status={run.status}>
        <p className="font-semibold">{title}</p>
        <p className="text-sm" data-testid="forecast-withheld-reason"><span className="font-semibold">{t('pages.forecast.withheldReason')}: </span>{run.status_reason}</p>
      </Card>
    );
  }
  return (
    <Card className="flex flex-col gap-5 p-5 enter-rise" data-testid="forecast-run" data-status={run.status}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">{title}</h3>
          <p className="text-sm font-semibold text-accent" data-testid="estimate-label">{pick(run.estimate_label, language)}</p>
        </div>
        <DataModeBadge mode={run.data_mode} />
      </div>
      {run.demonstration_label ? <DemonstrationBanner text={run.demonstration_label} /> : null}
      <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]" data-testid="forecast-meta">
        <dt className="text-muted-foreground">{t('forecasts.indicatorUnitArea')}</dt>
        <dd>{s ? `${language === 'ar' ? s.indicator.name_ar : s.indicator.name_en} · ${unit} · ${language === 'ar' ? s.area.name_ar : s.area.name_en}` : '—'}</dd>
        <dt className="text-muted-foreground">{t('forecasts.historicalPeriod')}</dt>
        <dd dir="ltr" className="text-start">{def.history ? `${def.history.first_period} → ${def.history.training_cutoff} (${def.history.observations})` : '—'}</dd>
        <dt className="text-muted-foreground">{t('forecasts.trainingCutoff')}</dt>
        <dd dir="ltr" className="text-start">{run.training_cutoff}</dd>
        <dt className="text-muted-foreground">{t('forecasts.horizon')}</dt>
        <dd>{t('forecasts.horizonValue', { n: run.outputs.length, frequency: s ? t(`frequency.${s.frequency as 'annual'}`) : '' })}</dd>
        <dt className="text-muted-foreground">{t('analysis.version')}</dt>
        <dd dir="ltr" className="text-start">{s?.dataset_version.label} · {s?.source_title}</dd>
        <dt className="text-muted-foreground">{t('forecasts.model')}</dt>
        <dd data-testid="selected-model">{run.selected_model ? modelName(run.selected_model) : '—'}</dd>
      </dl>
      <ForecastChart title={title} unit={unit} history={run.history} estimates={run.outputs} />
      {run.explanation ? <p className="rounded-md bg-sand-subtle/60 p-3 text-sm" data-testid="forecast-explanation">{pick(run.explanation, language)}</p> : null}
      <ExplanationBlock testId="forecast-explained" explanation={{
        change: t('explain.forecastChange', { n: run.outputs.length, indicator: s ? (language === 'ar' ? s.indicator.name_ar : s.indicator.name_en) : '' }),
        factors: t('explain.forecastFactors', { model: run.selected_model ? modelName(run.selected_model) : '—' }),
        uncertainty: t('explain.forecastUncertainty', {
          mae: formatDecimal(run.selected_model ? run.metrics[run.selected_model]?.mae ?? null : null, language, 3) ?? '—', unit,
        }),
        evidence: [t('explain.longerHistory'), ...evidenceNeeded(conditions, s ? domainOf(s.indicator.code) : 'electricity', language)],
        followUp: t('explain.forecastFollowUp'),
      }} />
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[24rem] text-sm" data-testid="forecast-metrics">
          <caption className="mb-1 text-start text-xs font-semibold">{t('forecasts.metricsCaption', { unit, n: Object.values(run.metrics)[0]?.n ?? 0 })}</caption>
          <thead>
            <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
              <th scope="col" className="py-1 text-start font-medium">{t('pages.forecast.model')}</th>
              <th scope="col" className="py-1 text-end font-medium">MAE</th>
              <th scope="col" className="py-1 text-end font-medium">RMSE</th>
              <th scope="col" className="py-1 text-end font-medium">{t('forecasts.chosen')}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(run.metrics).map(([model, m]) => (
              <tr key={model} className="border-b border-border last:border-0">
                <th scope="row" className="py-1 text-start font-normal">{modelName(model)}{model === 'baseline_last_value' ? ` (${t('forecasts.baselineTag')})` : ''}</th>
                <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(m.mae, language, 3)}</td>
                <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(m.rmse, language, 3)}</td>
                <td className="py-1 text-end">{model === run.selected_model ? '✓' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="rounded-md border border-border p-3 text-sm">
        <summary className="cursor-pointer font-semibold">{t('forecasts.valuesTable')}</summary>
        <div className="expand-content mt-2"><ForecastTable history={run.history} estimates={run.outputs} unit={unit} /></div>
      </details>
      <details className="rounded-md border border-border p-3 text-sm" data-testid="forecast-assumptions">
        <summary className="cursor-pointer font-semibold">{t('forecasts.assumptions')}</summary>
        <div className="expand-content mt-2 flex flex-col gap-2">
          {run.interval_method ? <p>{pick(run.interval_method, language)}</p> : null}
          <ul className="list-disc ps-5">{(language === 'ar' ? run.assumptions.ar : run.assumptions.en).map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      </details>
      <Link to={{ ...to('/assistant'), search: `${to('/assistant').search ? `${to('/assistant').search}&` : '?'}q=${encodeURIComponent(question)}` }}
        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'w-fit')} data-testid="explain-with-assistant">
        <MessageSquareText aria-hidden="true" />{t('forecasts.explainWithAssistant')}
      </Link>
    </Card>
  );
}

function ScenarioExplorer({ domains, conditions }: { domains: readonly Domain[]; conditions: DevelopmentConditions | undefined }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const flowLabel = useFlowLabel();
  const allSeries = useScenarioSeries(mode);
  const series = { ...allSeries, data: allSeries.data?.filter((s) => domains.includes(domainOf(s.indicator.code))) };
  const [seriesId, setSeriesId] = useState<string | null>(null);
  const [growth, setGrowth] = useState(3);
  const [years, setYears] = useState(5);
  const [oneOff, setOneOff] = useState(0);
  const selected = (seriesId && series.data?.some((s) => s.series_id === seriesId) ? seriesId : null) ?? series.data?.[0]?.series_id ?? null;
  const projection = useProjection(mode, selected, growth, years, oneOff);
  const growthId = useId();
  const yearsId = useId();
  const oneOffId = useId();
  const p = projection.data;
  const unit = p ? (language === 'ar' ? p.series.unit.label_ar : p.series.unit.label_en) : '';

  if (allSeries.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (!series.data?.length) {
    return <StatePanel kind="empty"><p className="text-sm text-muted-foreground" data-testid="scenario-unavailable">{t('forecasts.scenarioNoBase')}</p></StatePanel>;
  }
  const slider = (id: string, label: string, value: number, set: (v: number) => void, min: number, max: number, step: number, suffix: string, testid: string) => (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="flex justify-between gap-2 text-xs font-medium text-muted-foreground">
        <span>{label}</span><span className="tabular-nums text-foreground" dir="ltr">{value}{suffix}</span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => set(Number(e.target.value))}
        className="h-11 w-full accent-[var(--color-primary)]" data-testid={testid} />
    </div>
  );
  return (
    <div className="flex flex-col gap-4 rounded-lg border-2 border-dashed border-sand/60 bg-card p-5" data-testid="scenario-explorer">
      <p className="flex items-start gap-2 text-sm font-semibold text-sand-foreground" data-testid="scenario-label">
        <SlidersHorizontal aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{p ? pick(p.label, language) : t('forecasts.scenarioIntro')}
      </p>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SelectField label={t('forecasts.scenarioSeries')} value={selected ?? ''} onValueChange={setSeriesId} className="lg:col-span-1"
          options={series.data.map((s) => ({ value: s.series_id, label: seriesLabel(s, language, flowLabel) }))} data-testid="scenario-series" />
        {slider(growthId, t('forecasts.growth'), growth, setGrowth, -10, 15, 0.5, '%', 'scenario-growth')}
        {slider(yearsId, t('forecasts.years'), years, setYears, 1, 10, 1, '', 'scenario-years')}
        {slider(oneOffId, t('forecasts.oneOff'), oneOff, setOneOff, -50, 50, 1, '%', 'scenario-oneoff')}
      </div>
      {projection.isFetching ? <ProgressBar label={t('forecasts.calculating')} /> : null}
      {projection.isError ? <StatePanel kind="error" detail={projection.error.message} /> : null}
      {p ? (
        <>
          <ForecastChart title={seriesLabel(p.series, language, flowLabel)} unit={unit}
            history={[{ period_start: p.base.period_start, period_end: p.base.period_end, value: p.base.value }]}
            scenario={p.points.map((pt) => ({ label: `${pt.year}-01-01`, value: pt.value }))} />
          <p className="text-sm" data-testid="scenario-summary">
            {t('forecasts.scenarioSummary', {
              base: formatDecimal(p.base.value, language, 2) ?? '—', unit, period: formatPeriod(p.base.period_start, p.base.period_end, language),
              growth, oneOff, years, value: formatDecimal(p.points.at(-1)?.value ?? null, language, 2) ?? '—', year: p.points.at(-1)?.year ?? '',
            })}
          </p>
          <p className="text-xs text-muted-foreground">{t('forecasts.formula')}: <span dir="ltr">{pick(p.formula, language)}</span> · {t('forecasts.baseSource')}: {p.base.source.title} · {t('analysis.version')} <span dir="ltr">{p.base.dataset_version}</span></p>
          <ExplanationBlock testId="scenario-explained" explanation={{
            change: t('explain.scenarioChange', { indicator: language === 'ar' ? p.series.indicator.name_ar : p.series.indicator.name_en, years }),
            factors: t('explain.scenarioFactors', { growth, oneOff, period: formatPeriod(p.base.period_start, p.base.period_end, language) }),
            uncertainty: t('explain.scenarioUncertainty'),
            evidence: evidenceNeeded(conditions, domainOf(p.series.indicator.code), language),
            followUp: t('explain.scenarioFollowUp', { indicator: language === 'ar' ? p.series.indicator.name_ar : p.series.indicator.name_en }),
          }} />
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[18rem] text-sm" data-testid="scenario-table">
              <thead><tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-1 text-start font-medium">{t('forecasts.year')}</th>
                <th scope="col" className="py-1 text-end font-medium">{t('forecasts.scenarioValue', { unit })}</th>
              </tr></thead>
              <tbody>{p.points.map((pt) => (
                <tr key={pt.year} className="border-b border-border last:border-0">
                  <td className="py-1" dir="ltr">{pt.year}</td>
                  <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(pt.value, language, 2)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function ForecastPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const me = useMe();
  const canRun = hasPermission(me.data, 'analysis.run');
  const overview = useForecastOverview(mode);
  const conditions = useForecastConditions(mode);
  const runForecast = useRunForecast();
  const [shown, setShown] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const run = useForecastRun(shown);
  const [domain, setDomain] = useUrlFilter<'all' | Domain>('domain', ['all', ...DOMAINS], 'all');
  const domains: readonly Domain[] = domain === 'all' ? DOMAINS : [domain];

  if (adapterKind !== 'http') {
    return (
      <>
        <PageHeader title={t('forecasts.title')} intro={t('forecasts.intro')} />
        <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('pages.forecast.requiresApi')}</p></StatePanel>
      </>
    );
  }
  const onRun = (seriesId: string) => {
    setRunning(seriesId);
    runForecast.mutate({ data_mode: mode, series_id: seriesId }, {
      onSuccess: (r) => setShown(r.id),
      onSettled: () => setRunning(null),
    });
  };
  const filtered = overview.data ? { ...overview.data, targets: overview.data.targets.filter((x) => domains.includes(x.group)) } : null;
  const anyAvailable = filtered?.targets.some((x) => x.status === 'available');

  return (
    <>
      <PageHeader title={t('forecasts.title')} intro={t('forecasts.intro')} />
      <div className="flex flex-col gap-10">
        <Segmented
          label={t('forecasts.domain')}
          value={domain}
          onChange={setDomain}
          options={[{ value: 'all', label: t('forecasts.allDomains') }, ...DOMAINS.map((d) => ({ value: d, label: t(DOMAIN_KEY[d]) }))]}
          className="w-full max-w-3xl overflow-x-auto"
          testId="forecast-domain"
        />

        <section aria-labelledby="history" className="flex flex-col gap-4">
          <h2 id="history" className="text-xl font-semibold">{t('forecasts.historyHeading')}</h2>
          <p className="max-w-3xl text-sm text-muted-foreground">{t('forecasts.historyIntro')}</p>
          {filtered ? <HistoryPanel data={filtered} domains={domains} /> : null}
        </section>

        <section aria-labelledby="stat-forecasts" className="flex flex-col gap-4">
          <h2 id="stat-forecasts" className="flex items-center gap-2 text-xl font-semibold"><LineChart aria-hidden="true" className="size-5 text-accent" />{t('forecasts.statHeading')}</h2>
          <p className="max-w-3xl text-sm text-muted-foreground">{t('forecasts.statIntro')}</p>
          {overview.isPending ? <StatePanel kind="loading" /> : null}
          {overview.isError ? <StatePanel kind="error" detail={overview.error.message} onRetry={() => void overview.refetch()} /> : null}
          {filtered ? (
            <>
              {filtered.demonstration_label ? <DemonstrationBanner text={filtered.demonstration_label} /> : null}
              {!anyAvailable ? (
                <p role="status" className="rounded-lg border-2 border-sand/60 bg-card p-4 text-sm font-semibold" data-testid="forecast-unavailable">
                  {pick(filtered.insufficient_label, language)} {t('forecasts.noneAvailableDetail')}
                </p>
              ) : null}
              <TargetCards data={filtered} canRun={canRun} running={running} onRun={onRun} onShow={setShown} shown={shown} />
              {!canRun ? <p className="text-xs text-muted-foreground">{t('pages.forecast.analystsOnly')}</p> : null}
              {runForecast.isError ? <StatePanel kind="error" detail={runForecast.error.message} /> : null}
              {run.isPending && shown ? <StatePanel kind="loading" skeleton="lines" /> : null}
              {run.data ? <RunView run={run.data} conditions={conditions.data} /> : null}
              <MethodCard method={filtered.method} />
            </>
          ) : null}
        </section>

        <section aria-labelledby="conditions" className="flex flex-col gap-4">
          <h2 id="conditions" className="text-xl font-semibold">{t('forecasts.conditionsHeading')}</h2>
          {conditions.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
          {conditions.isError ? <StatePanel kind="error" detail={conditions.error.message} /> : null}
          {conditions.data ? <ConditionsPanel data={conditions.data} domains={domains} /> : null}
        </section>

        <section aria-labelledby="scenarios" className="flex flex-col gap-4">
          <h2 id="scenarios" className="flex items-center gap-2 text-xl font-semibold"><SlidersHorizontal aria-hidden="true" className="size-5 text-sand-foreground" />{t('forecasts.scenarioHeading')}</h2>
          <p className="max-w-3xl text-sm text-muted-foreground">{t('forecasts.scenarioIntro')}</p>
          <ScenarioExplorer domains={domains} conditions={conditions.data} />
        </section>
      </div>
    </>
  );
}
