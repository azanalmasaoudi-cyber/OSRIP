import { FlaskConical, LineChart, SlidersHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { ForecastBlock, ScenarioBlock, StructuredReply } from '@/api/assistant';
import { useStudy } from '@/api/studies';
import { ReplyOutlook } from '@/components/assistant/ReplyOutlook';
import { ReplyReport } from '@/components/assistant/ReplyReport';
import { ForecastChart, ForecastTable } from '@/components/forecast/ForecastChart';
import { StatePanel } from '@/components/common/StatePanel';
import { StudyView } from '@/components/studies/StudyView';
import { Badge } from '@/components/ui/badge';
import { formatDate, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/*
 * What Al Mulhim ran for a reply, shown in the conversation itself: the study (its title,
 * method, findings, table, chart and limitations, as stored), the forecasting engine's result
 * (estimates with their intervals, or why none is given) and a hypothetical scenario (its
 * assumptions and resulting values). Every number here comes from the backend's own tools;
 * the reply text around them is checked against the same evidence.
 */

function Card({ title, icon, badge, children, testId, data }: {
  title: ReactNode;
  icon: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
  testId: string;
  data?: Record<`data-${string}`, string | undefined>;
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-card/70 p-3 sm:p-4" data-testid={testId} {...data}>
      <header className="flex flex-wrap items-center gap-2">
        <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-lg bg-primary-soft text-brand">{icon}</span>
        <h4 className="min-w-0 flex-1 text-base font-semibold">{title}</h4>
        {badge}
      </header>
      {children}
    </section>
  );
}

/** A study cited by the reply, loaded from where it is stored and shown in full. */
function ReplyStudy({ id, title }: { id: string; title: { en: string; ar: string } }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const study = useStudy(id);
  return (
    <Card title={title[language]} icon={<FlaskConical className="size-4" />} testId="reply-study" data={{ 'data-study': id }}
      badge={<Badge variant="outline">{t('assistant.intent.study')}</Badge>}>
      {study.isPending ? <StatePanel kind="loading" skeleton="lines" />
        : study.isError ? <StatePanel kind="error" error={study.error} onRetry={() => void study.refetch()} />
          : <StudyView stored={study.data} headingLevel={3} />}
      <Link to={to(`/studies/${id}`)} className="w-fit text-sm text-primary underline underline-offset-2" data-testid="reply-study-link">
        {t('chat.results.openStudy')}
      </Link>
    </Card>
  );
}

function ReplyForecast({ forecast }: { forecast: ForecastBlock }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const name = forecast.indicator_name?.[language] ?? forecast.indicator;
  const unit = forecast.unit_label?.[language] ?? forecast.unit ?? '';
  const history = (forecast.history ?? []).map((h) => ({ period_start: h.period_start, period_end: h.period_end ?? h.period_start, value: h.value }));
  const outputs = forecast.outputs ?? [];
  const ok = forecast.status === 'ok' && outputs.length > 0;
  const model = forecast.selected_model ? forecast.model_names?.[forecast.selected_model]?.[language] ?? forecast.selected_model : null;
  const metric = forecast.selected_model ? forecast.metrics?.[forecast.selected_model] : null;
  const baseline = forecast.metrics?.baseline_last_value;
  const title = `${name} · ${forecast.area_name?.[language] ?? forecast.area}`;
  return (
    <Card title={title} icon={<LineChart className="size-4" />} testId="reply-forecast" data={{ 'data-status': forecast.status }}
      badge={<Badge variant={ok ? 'verified' : 'sand'}>{ok ? t('chat.results.forecastBadge') : t('chat.results.forecastWithheld')}</Badge>}>
      {forecast.demonstration_label ? <p className="rounded-md bg-synthetic px-2 py-1 text-sm text-synthetic-foreground">{forecast.demonstration_label[language]}</p> : null}
      {ok ? (
        <>
          <p className="text-sm font-medium" data-testid="reply-forecast-label">{forecast.label?.[language] ?? t('chat.results.estimateLabel')}</p>
          <ForecastChart history={history} estimates={outputs} unit={unit} title={name} />
          <ForecastTable history={history.slice(-4)} estimates={outputs} unit={unit} />
          <p className="text-sm text-muted-foreground" data-testid="reply-forecast-method">
            {t(forecast.stored ? 'chat.results.storedRun' : 'chat.results.computedNow')}{' '}
            {model && metric ? t('chat.results.method', {
              model, n: metric.n, mae: formatDecimal(metric.mae ?? '', language, 2) ?? metric.mae ?? '—',
              baseline: baseline?.mae ? formatDecimal(baseline.mae, language, 2) ?? baseline.mae : '—',
            }) : null}{' '}
            {forecast.training_cutoff ? t('chat.results.cutoff', { date: formatDate(forecast.training_cutoff, language) }) : null}
          </p>
        </>
      ) : (
        <div className="flex flex-col gap-2 text-sm" data-testid="reply-forecast-reasons">
          {forecast.usable_observations != null && forecast.policy ? (
            <p className="font-medium">{t('chat.results.withheldCount', { usable: forecast.usable_observations, needed: forecast.policy.minimum_length })}</p>
          ) : null}
          <ul className="list-disc ps-5 text-muted-foreground">
            {(forecast.reasons ?? []).map((r, i) => <li key={r.code ?? i}>{r[language]}</li>)}
          </ul>
          <p className="text-muted-foreground">{t('chat.results.noValueGiven')}</p>
        </div>
      )}
    </Card>
  );
}

function ReplyScenario({ scenario }: { scenario: ScenarioBlock }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const base = scenario.base;
  const name = base?.indicator_name?.[language] ?? scenario.indicator ?? '';
  const unit = base?.unit_label?.[language] ?? scenario.unit ?? '';
  const a = scenario.assumptions ?? {};
  const history = base && base.value !== null && base.period_start
    ? [{ period_start: base.period_start, period_end: base.period_end ?? base.period_start, value: base.value }] : [];
  const points = scenario.points.filter((p) => p.value !== null && p.year != null)
    .map((p) => ({ label: `${p.year}-01-01`, value: p.value as string, year: p.year as number }));
  return (
    <Card title={`${name} · ${scenario.area ?? ''}`} icon={<SlidersHorizontal className="size-4" />} testId="reply-scenario"
      badge={<Badge variant="sand">{t('chat.results.scenarioBadge')}</Badge>}>
      <p className="text-sm font-medium" data-testid="reply-scenario-label">{scenario.label?.[language] ?? t('chat.results.scenarioBadge')}</p>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        {base ? (
          <>
            <dt className="text-muted-foreground">{t('chat.results.base')}</dt>
            <dd><bdi className="tabular-nums" dir="ltr">{formatDecimal(base.value ?? '', language, 2) ?? base.value}</bdi> {unit}
              {base.period_start ? ` · ${formatPeriod(base.period_start, base.period_end ?? base.period_start, language)}` : ''}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">{t('chat.results.assumptions')}</dt>
        <dd data-testid="reply-scenario-assumptions">
          {t('chat.results.growth', { pct: formatDecimal(String(a.growth_pct ?? '0'), language, 2) ?? String(a.growth_pct ?? '0'), years: a.years ?? points.length })}
          {a.one_off_pct && Number(a.one_off_pct) !== 0 ? ` · ${t('chat.results.oneOff', { pct: formatDecimal(String(a.one_off_pct), language, 2) ?? String(a.one_off_pct) })}` : ''}
        </dd>
        {scenario.formula ? (
          <>
            <dt className="text-muted-foreground">{t('chat.results.formula')}</dt>
            <dd dir="auto">{scenario.formula[language]}</dd>
          </>
        ) : null}
      </dl>
      <ForecastChart history={history} scenario={points} unit={unit} title={name} />
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[18rem] text-sm" data-testid="reply-scenario-table">
          <caption className="mb-1 text-start text-xs font-semibold">{t('chat.results.scenarioTable', { unit })}</caption>
          <thead>
            <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
              <th scope="col" className="py-1 text-start font-medium">{t('table.period')}</th>
              <th scope="col" className="py-1 text-end font-medium">{t('chat.results.hypotheticalValue')}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.year} className="border-b border-border">
                <td className="py-1">{p.year}</td>
                <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(p.value, language, 2) ?? p.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/** Everything the reply ran, in the order it was asked for. */
export function ReplyResults({ structured }: { structured: StructuredReply }) {
  const studies = (structured.studies ?? []).filter((s) => s.kind !== 'supply_balance');
  const forecasts = structured.forecasts ?? [];
  const scenarios = structured.scenarios ?? [];
  const report = structured.report;
  const outlook = structured.outlook;
  if (!report && !outlook && !studies.length && !forecasts.length && !scenarios.length) return null;
  return (
    <div className="flex flex-col gap-3" data-testid="reply-results">
      {report ? <ReplyReport report={report} /> : null}
      {outlook ? <ReplyOutlook outlook={outlook} /> : null}
      {studies.map((s) => <ReplyStudy key={s.id} id={s.id} title={s.title} />)}
      {forecasts.map((f) => <ReplyForecast key={f.evidence_id} forecast={f} />)}
      {scenarios.map((s) => <ReplyScenario key={s.evidence_id} scenario={s} />)}
    </div>
  );
}
