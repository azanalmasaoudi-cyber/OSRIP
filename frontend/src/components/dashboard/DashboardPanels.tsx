import { ArrowRight, Bot, Droplets, FileText, Lightbulb, MapPinned, ShieldAlert, SlidersHorizontal, ThumbsDown, ThumbsUp, Wheat, Ship, Zap } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useDecisionBrief } from '@/api/decision';
import { useSeries } from '@/api/queries';
import { KpiCard, type KpiChange } from '@/components/dashboard/KpiCard';
import { TrendChart, type TrendPoint } from '@/components/dashboard/TrendChart';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Segmented } from '@/components/ui/segmented';
import { HEADLINE, latestOf, type SeriesQuery } from '@/domain/headline';
import type { ObservationRecord, SectionCode, Series } from '@/domain/types';
import { formatDate, formatDecimal, formatPeriodShort, type AppLanguage } from '@/lib/format';
import { useProvenance } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const AXES: readonly { section: SectionCode; path: string; title: 'pages.electricity.title' | 'pages.water.title' | 'pages.food.title' | 'pages.trade.title'; icon: typeof Zap }[] = [
  { section: 'electricity', path: '/energy/electricity', title: 'pages.electricity.title', icon: Zap },
  { section: 'water', path: '/energy/water', title: 'pages.water.title', icon: Droplets },
  { section: 'food_security', path: '/food-security', title: 'pages.food.title', icon: Wheat },
  { section: 'trade', path: '/trade', title: 'pages.trade.title', icon: Ship },
];

/** The same months one year earlier ("2025-01-01" → "2024-01-01"). */
function yearEarlier(date: string): string {
  return `${Number(date.slice(0, 4)) - 1}${date.slice(4)}`;
}

/** The previous comparable value in the same series: the same period one year earlier. */
function previousOf(series: Series, obs: ObservationRecord): ObservationRecord | undefined {
  const start = yearEarlier(obs.periodStart);
  const end = yearEarlier(obs.periodEnd);
  return series.observations.find((o) => o.value !== null && !o.valueOperator && o.periodStart === start && (o.periodEnd === end || o.periodEnd.slice(0, 7) === end.slice(0, 7)));
}

export function kpiOf(queries: readonly SeriesQuery[], indicators: readonly string[], language: AppLanguage) {
  const found = latestOf(queries, indicators);
  if (!found) return null;
  const { series, obs } = found;
  const prev = obs.valueOperator ? undefined : previousOf(series, obs);
  const now = Number(obs.value);
  const before = prev ? Number(prev.value) : NaN;
  const change: KpiChange | null = prev && Number.isFinite(before) && before !== 0
    ? { pct: ((now - before) / Math.abs(before)) * 100, periods: `${formatPeriodShort(prev.periodStart, prev.periodEnd, language)} → ${formatPeriodShort(obs.periodStart, obs.periodEnd, language)}` }
    : null;
  // The same kind of period only (full years with full years, January-July with January-July).
  const sameKind = series.observations
    .filter((o) => o.value !== null && !o.valueOperator && o.periodStart.slice(5) === obs.periodStart.slice(5) && o.periodEnd.slice(5, 7) === obs.periodEnd.slice(5, 7))
    .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd))
    .slice(-8);
  return { series, obs, change, trend: sameKind.map((o) => Number(o.value)) };
}

/** Headline figures for the four axes (the home page's KPI row). */
export function LatestFigures() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const provenance = useProvenance();
  const queries = {
    electricity: [useSeries('electricity', mode, 'annual'), useSeries('electricity', mode, 'year_to_date')],
    water: [useSeries('water', mode, 'annual'), useSeries('water', mode, 'year_to_date')],
    food_security: [useSeries('food_security', mode, 'annual'), useSeries('food_security', mode, 'year_to_date')],
    trade: [useSeries('trade', mode, 'annual'), useSeries('trade', mode, 'year_to_date')],
  } satisfies Record<SectionCode, SeriesQuery[]>;
  return (
    <section aria-labelledby="latest-heading" className="flex flex-col gap-3" data-testid="latest-figures">
      <h2 id="latest-heading" className="gold-rule flex flex-wrap items-center gap-2 text-xl font-semibold sm:text-2xl">
        {t('pages.home.latestHeading')} <DataModeBadge mode={mode} />
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {HEADLINE.map(({ section, indicators }) => {
          const qs = queries[section];
          const kpi = kpiOf(qs, indicators, language);
          const shown = kpi ? provenance.value(kpi.obs, language, 1) : null;
          const axis = AXES.find((a) => a.section === section);
          const Icon = axis?.icon ?? Zap;
          const source = kpi?.series.source;
          const freshness = source?.publishedAt ? t('dashboard.published', { date: formatDate(source.publishedAt, language) })
            : source?.accessDate ? t('dashboard.read', { date: formatDate(source.accessDate, language) }) : null;
          return (
            <KpiCard key={section} testId="latest-card" data-section={section} data-indicator={kpi?.series.indicatorCode ?? indicators[0]}
              title={kpi ? kpi.series.name[language] : t(`pages.home.headline.${section}`)} icon={<Icon className="size-4" />}
              state={qs.some((q) => q.isPending) ? 'loading' : 'ready'}
              value={kpi && shown ? shown.text : null} unit={kpi?.series.unit.label[language]}
              period={kpi ? `${formatPeriodShort(kpi.obs.periodStart, kpi.obs.periodEnd, language)}${kpi.series.frequency === 'year_to_date' ? ` · ${t('frequency.year_to_date')}` : ''}` : undefined}
              change={kpi?.change} trend={kpi?.trend} freshness={freshness} />
          );
        })}
      </ul>
    </section>
  );
}

function useAxisTrend(section: SectionCode, indicators: readonly string[]): { points: TrendPoint[]; title: string; unit: string } | null {
  const [mode] = useDataMode();
  const language = useAppLanguage();
  const annual = useSeries(section, mode, 'annual');
  if (annual.data?.status !== 'ok') return null;
  for (const code of indicators) {
    const series = annual.data.series.find((s) => s.indicatorCode === code && (s.area?.code ?? 'OM') === 'OM' && s.partnerCode === null && (s.flow === null || s.flow === 'domestic_export'));
    if (!series) continue;
    const points = series.observations
      .filter((o) => o.value !== null && !o.valueOperator && o.periodComplete)
      .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd))
      .map((o) => ({ label: formatPeriodShort(o.periodStart, o.periodEnd, language), value: Number(o.value) }));
    if (points.length) return { points, title: series.name[language], unit: series.unit.label[language] };
  }
  return null;
}

/**
 * The dashboard's analysis area for one chosen axis: its headline series over full years, the
 * regional distribution, rule-based insights and data-quality notices from the decision brief,
 * and quick links. Nothing here is AI-written; every figure is published data.
 */
export function AxisAnalysis() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const to = usePreservedSearch();
  const [section, setSection] = useState<SectionCode>('electricity');
  const axis = AXES.find((a) => a.section === section) ?? AXES[0]!;
  const headline = HEADLINE.find((h) => h.section === section);
  const trend = useAxisTrend(section, headline?.indicators ?? []);
  const brief = useDecisionBrief(section, mode);
  const b = brief.data;
  const region = b?.regional[0];
  const insights = b ? [...b.strengths.slice(0, 2).map((f) => ({ ...f, tone: 'up' as const })), ...b.weaknesses.slice(0, 2).map((f) => ({ ...f, tone: 'down' as const }))] : [];
  const n = (v: string, places = 1) => formatDecimal(v, language, places) ?? '—';

  return (
    <section aria-labelledby="analysis-heading" className="flex flex-col gap-4" data-testid="dashboard-analysis">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="analysis-heading" className="gold-rule text-xl font-semibold sm:text-2xl">{t('dashboard.analysisHeading')}</h2>
          <p className="text-sm text-muted-foreground">{t('dashboard.analysisIntro')}</p>
        </div>
        <Segmented label={t('dashboard.axis')} value={section} onChange={setSection} testId="dashboard-axis" className="w-full max-w-xl"
          options={AXES.map((a) => ({ value: a.section, label: t(a.title) }))} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="surface-card flex min-w-0 flex-col gap-3 p-5">
          {trend ? <TrendChart points={trend.points} unit={trend.unit} title={trend.title} />
            : <p className="text-sm text-muted-foreground">{t('states.dataUnavailable')}</p>}
        </div>
        <div className="surface-card flex min-w-0 flex-col gap-3 p-5" data-testid="dashboard-regional">
          <h3 className="flex items-center gap-2 font-semibold"><MapPinned aria-hidden="true" className="size-4 text-brand" />{t('dashboard.regional')}</h3>
          {!region ? <p className="text-sm text-muted-foreground">{brief.isPending ? t('states.loading') : t('decision.noRegional')}</p> : (
            <>
              <p className="text-xs text-muted-foreground">{region.indicator.name[language]} · {region.period[language]} ({region.unit[language]})</p>
              <ul className="flex flex-col gap-2">
                {region.areas.slice(0, 6).map((a) => {
                  const pct = a.share_pct === null ? null : Math.max(0, Math.min(100, Number(a.share_pct)));
                  return (
                    <li key={a.area.code} className="flex flex-col gap-1">
                      <span className="flex justify-between gap-3 text-sm">
                        <span className="truncate">{a.area.name[language]}</span>
                        <span className="shrink-0 tabular-nums">{n(a.value)}{pct === null ? '' : ` · ${n(String(pct))}%`}</span>
                      </span>
                      {pct === null ? null : <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-gradient-to-r from-brand to-brand-2" style={{ width: `${pct}%` }} /></span>}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
          <Link to={to('/geography')} className="mt-auto inline-flex w-fit items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
            {t('decision.openMap')}<ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
          </Link>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="surface-card flex min-w-0 flex-col gap-3 p-5 lg:col-span-2" data-testid="dashboard-insights">
          <h3 className="flex items-center gap-2 font-semibold"><Lightbulb aria-hidden="true" className="size-4 text-brand" />{t('dashboard.insights')}</h3>
          <p className="text-xs text-muted-foreground">{t('dashboard.insightsNote')}</p>
          {insights.length === 0 ? <p className="text-sm text-muted-foreground">{brief.isPending ? t('states.loading') : t('dashboard.noInsights')}</p> : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {insights.map((f) => (
                <li key={f.id} className="flex gap-2.5 rounded-xl border border-border bg-card/60 p-3 text-sm">
                  {f.tone === 'up' ? <ThumbsUp aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-positive" /> : <ThumbsDown aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-critical" />}
                  <span><span className="sr-only">{f.tone === 'up' ? t('decision.strengths') : t('decision.weaknesses')}: </span>{f.text[language]}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to={{ ...to(axis.path), hash: '#decision-brief' }} className="inline-flex w-fit items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
            {t('dashboard.fullBrief', { axis: t(axis.title) })}<ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
          </Link>
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <div className="surface-card flex flex-col gap-2 p-5" data-testid="dashboard-quality">
            <h3 className="flex items-center gap-2 font-semibold"><ShieldAlert aria-hidden="true" className="size-4 text-brand" />{t('dashboard.quality')}</h3>
            <p className="text-sm text-muted-foreground">
              {b ? t('dashboard.qualityText', { gaps: b.gaps.filter((g) => g.kind !== 'regional').length, governorates: b.coverage.governorates.length, of: b.coverage.of })
                : brief.isPending ? t('states.loading') : t('states.dataUnavailable')}
            </p>
          </div>
          <nav aria-label={t('dashboard.quick')} className="surface-card flex flex-col gap-1 p-3" data-testid="dashboard-quick">
            {[
              { path: '/forecasts', hash: '#scenarios', label: t('nav.scenarios'), icon: SlidersHorizontal },
              { path: '/reports', hash: '', label: t('nav.reports'), icon: FileText },
              { path: '/assistant', hash: '', label: t('nav.aiAssistant'), icon: Bot },
            ].map((q) => (
              <Link key={q.path} to={{ ...to(q.path), hash: q.hash }} className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium hover:bg-primary-soft">
                <q.icon aria-hidden="true" className="size-4 text-brand" />{q.label}
                <ArrowRight aria-hidden="true" className="ms-auto size-4 text-muted-foreground rtl:-scale-x-100" />
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </section>
  );
}
