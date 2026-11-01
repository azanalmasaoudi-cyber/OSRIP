import { BarChart3, BookOpen, Bot, EyeOff, FlaskConical, ListChecks, Scale, Table2 } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { SectionFilters } from '@/api/analysis';
import { adapterKind } from '@/api/config';
import { useSectionSeries } from '@/api/queries';
import {
  useAvailability,
  useTimeline,
  VIEWS,
  type AvailabilitySeries,
  type AvailableIndicator,
  type SeriesView,
  type Timeline,
  type TimelineQuery,
  type TimelineSummary,
} from '@/api/series';
import { AnalysisPanel, ExportLinks } from '@/components/analysis/AnalysisPanel';
import { ReviewCards } from '@/components/analysis/ReviewCards';
import { SaveReportButton } from '@/components/analysis/SaveReportButton';
import { SectionInsights } from '@/components/analysis/SectionInsights';
import { SpokenSummary } from '@/components/sector/SpokenSummary';
import { DataQualityNotes } from '@/components/common/DataQualityNotes';
import { QualityBadges, qualityOf } from '@/components/common/QualityBadges';
import { WatchButton } from '@/components/common/WatchButton';
import { StatePanel } from '@/components/common/StatePanel';
import { HEADLINES, TimelineState } from '@/components/series/SectorSeries';
import { periodLabel, TimelineChart, TimelineRules, TimelineSources, TimelineTable } from '@/components/series/SeriesParts';
import { Button, buttonVariants } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import type { SectionCode, TradeFlow } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { sameSelection, useSectorSelection, type SectorSelection } from '@/state/sectorSelections';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * One sector, in steps: (1) the sector is chosen in the page header; here the person chooses
 * (2) an indicator, (3) its area (and breakdown, such as trade partners, where published) and
 * (4) a frequency and a start and end period, all offered from what is actually published (the
 * availability metadata), and presses (5) "Show results". Only then are the quality badges, the
 * summary and the table shown, for exactly that selection; (6) the chart stays hidden until
 * "Show chart" is pressed and can be hidden again. Editing the selection afterwards hides the
 * previous results until they are applied again, so they are never shown under the new dates.
 * Each sector keeps its own selection (state/sectorSelections).
 *
 * Layout: one column on phones; from 1280 px the selection is a column of its own beside the
 * results; from 1792 px (e.g. 4K) a third column holds the AI insights and the sources.
 */

const NO_CHOICE = '';
/** Food security's apparent availability needs a stock-change assumption (calculations only). */
const STOCK_OPTIONS = ['assumed_zero', 'unknown', 'known'] as const;
type StockAssumption = (typeof STOCK_OPTIONS)[number];

export function breakdownKey(s: AvailabilitySeries): string {
  return [s.commodity?.code ?? '', s.partner?.code ?? '', s.flow ?? ''].join('|');
}

const AREA_ORDER = (s: AvailabilitySeries) => (s.area.code === 'OM' ? 0 : s.area.level === 'governorate' ? 1 : 2);

function sortSeries(series: readonly AvailabilitySeries[]): AvailabilitySeries[] {
  return [...series].sort((a, b) => AREA_ORDER(a) - AREA_ORDER(b) || a.area.code.localeCompare(b.area.code)
    || Number(Boolean(a.partner)) - Number(Boolean(b.partner)) || breakdownKey(a).localeCompare(breakdownKey(b)));
}

function sortIndicators(section: SectionCode, indicators: readonly AvailableIndicator[], language: AppLanguage): AvailableIndicator[] {
  const headline = HEADLINES[section];
  const rank = (code: string) => (headline.includes(code) ? headline.indexOf(code) : headline.length);
  return [...indicators].sort((a, b) => rank(a.code) - rank(b.code) || a.name[language].localeCompare(b.name[language], language));
}

/** A period offered in the selectors; ``ytdOnly`` marks a year with only a year-to-date total. */
interface Period {
  start: string;
  end: string;
  ytdOnly: boolean;
}

interface Resolved {
  selection: SectorSelection;
  indicator: AvailableIndicator;
  entry: AvailabilitySeries;
  areas: AvailabilitySeries['area'][];
  breakdowns: AvailabilitySeries[];
  available: SeriesView[];
  periods: Period[];
}

/** The periods of a view that have a value. In the annual view a year that so far has only
 * a year-to-date total is offered too (marked as such): the table then lists that partial
 * year apart from the complete years, and it is never shown as a full year. */
function periodsOf(entry: AvailabilitySeries, view: SeriesView): Period[] {
  const own = entry.views[view].map((p) => ({ ...p, ytdOnly: false }));
  if (view !== 'annual') return own;
  const years = new Set(own.map((p) => p.start.slice(0, 4)));
  const partial = [...new Set(entry.year_to_date.map((p) => p.start.slice(0, 4)))].filter((y) => !years.has(y))
    .map((y) => ({ start: `${y}-01-01`, end: `${y}-12-31`, ytdOnly: true }));
  return [...own, ...partial].sort((a, b) => a.start.localeCompare(b.start));
}

/** The selection as it can actually be made: unknown or unavailable choices fall back to
 * the first available one (national before areas; total before partners); a period that is
 * not published in the chosen view is cleared, never guessed. */
function resolve(input: Partial<SectorSelection> | null, indicators: readonly AvailableIndicator[]): Resolved | null {
  const indicator = indicators.find((i) => i.code === input?.indicator) ?? indicators[0];
  if (!indicator) return null;
  const series = sortSeries(indicator.series);
  const areas = [...new Map(series.map((s) => [s.area.code, s.area])).values()];
  const area = areas.find((a) => a.code === input?.area)?.code ?? areas[0]?.code ?? 'OM';
  const breakdowns = series.filter((s) => s.area.code === area);
  const entry = breakdowns.find((s) => breakdownKey(s) === input?.breakdown) ?? breakdowns[0];
  if (!entry) return null;
  const available = VIEWS.filter((v) => periodsOf(entry, v).length > 0);
  const view: SeriesView = input?.view && (VIEWS as readonly string[]).includes(input.view) ? input.view : (available[0] ?? 'annual');
  const periods = periodsOf(entry, view);
  const starts = periods.map((p) => p.start);
  const from = input?.from && starts.includes(input.from) ? input.from : NO_CHOICE;
  const to = input?.to && starts.includes(input.to) ? input.to : NO_CHOICE;
  return {
    selection: { indicator: indicator.code, area, breakdown: breakdownKey(entry), view, from, to },
    indicator, entry, areas, breakdowns, available, periods,
  };
}

function breakdownName(s: AvailabilitySeries, language: AppLanguage, t: TFunction): string {
  const parts = [
    s.partner ? s.partner.name[language] : s.flow && !s.commodity ? t('sectorFlow.breakdownTotal') : null,
    s.commodity ? s.commodity.name[language] : null,
    s.flow ? (s.flow in FLOW_KEY ? t(FLOW_KEY[s.flow as TradeFlow]) : s.flow) : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : t('sectorFlow.breakdownTotal');
}

/** One numbered step of the selection. */
function Step({ n, title, children, testId }: { n: number; title: string; children: ReactNode; testId?: string }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2.5 border-t border-border pt-4 first:border-t-0 first:pt-0" data-testid={testId}>
      <legend className="float-start mb-2.5 flex w-full items-center gap-2 text-sm font-semibold">
        <span aria-hidden="true" className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background">{n}</span>
        {title}
      </legend>
      <div className="clear-both flex min-w-0 flex-col gap-2.5">{children}</div>
    </fieldset>
  );
}

/** A card in the results or the insights column. */
function Panel({ id, title, icon, children, className, testId, action }: {
  id: string; title: string; icon?: ReactNode; children: ReactNode; className?: string; testId?: string; action?: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className={cn('flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5', className)}
      data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={id} className="flex items-center gap-2 text-base font-semibold">{icon}{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SectorWorkflow({ section, title }: { section: SectionCode; title: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const formId = useId();
  const availability = useAvailability(section, mode);
  const { state, setDraft, apply } = useSectorSelection(section, mode);
  const [error, setError] = useState<'no_period' | 'order' | null>(null);
  // Not stored: a chart is drawn only after "Show chart" on this visit.
  const [chart, setChart] = useState(false);

  if (adapterKind !== 'http') {
    return <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('sectorFlow.requiresApi')}</p></StatePanel>;
  }
  if (availability.isPending) {
    return <p role="status" className="text-sm text-muted-foreground" data-testid="sector-availability-loading">{t('sectorFlow.loadingAvailability')}</p>;
  }
  if (availability.isError) {
    return (
      <StatePanel kind="error" detail={availability.error.message} onRetry={() => void availability.refetch()}>
        <p className="text-sm">{t('sectorFlow.availabilityFailed')}</p>
      </StatePanel>
    );
  }
  const indicators = sortIndicators(section, availability.data.indicators, language);
  const draft = resolve(state.draft, indicators);
  if (!draft) {
    return (
      <StatePanel kind={mode === 'verified_source' ? 'no_verified_data' : 'empty'}>
        <p className="text-sm text-muted-foreground" data-testid="sector-no-data">{t('sectorFlow.noData')}</p>
      </StatePanel>
    );
  }
  const applied = state.applied ? resolve(state.applied, indicators) : null;
  const appliedValid = Boolean(state.applied && applied && sameSelection(applied.selection, state.applied));
  const stale = appliedValid && !sameSelection(draft.selection, state.applied);

  const change = (next: Partial<SectorSelection>) => {
    setError(null);
    const resolved = resolve({ ...draft.selection, ...next }, indicators);
    if (resolved) setDraft(resolved.selection);
  };
  const submit = () => {
    const { from, to } = draft.selection;
    if (!from || !to) return setError('no_period');
    if (from > to) return setError('order');
    setError(null);
    setChart(false);
    apply(draft.selection);
  };
  const label = (start: string, view: string) => periodLabel(start, view, language);
  const periodOptions = [{ value: NO_CHOICE, label: t('sectorFlow.choosePeriod') },
    ...draft.periods.map((p) => ({ value: p.start,
      label: p.ytdOnly ? t('sectorFlow.ytdOnly', { period: label(p.start, draft.selection.view) }) : label(p.start, draft.selection.view) }))];
  const noPeriods = draft.periods.length === 0;
  const complete = draft.periods.filter((p) => !p.ytdOnly);
  const showing = appliedValid && !stale && applied;

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[19rem_minmax(0,1fr)] 3xl:grid-cols-[20rem_minmax(0,1fr)_22rem]"
      data-testid="sector-workflow" data-section={section}>
      <form className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5 xl:row-span-2 3xl:sticky 3xl:top-20 3xl:row-span-1"
        data-testid="sector-form" aria-labelledby={`${formId}-h`} onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <h2 id={`${formId}-h`} className="flex items-center gap-2 text-base font-semibold">
          <ListChecks aria-hidden="true" className="size-5 text-primary" />{t('sectorFlow.chooseHeading')}
        </h2>
        <Step n={1} title={t('sectorFlow.stepSector')}>
          <p className="text-sm font-medium" data-testid="sector-current">{title}</p>
        </Step>
        <Step n={2} title={t('sectorFlow.indicator')}>
          <SelectField label={t('sectorFlow.indicator')} labelClassName="sr-only" value={draft.selection.indicator}
            onValueChange={(v) => change({ indicator: v, area: draft.selection.area, breakdown: NO_CHOICE, view: undefined })}
            options={indicators.map((i) => ({ value: i.code, label: i.name[language] }))} data-testid="sector-indicator" />
          <p className="text-xs text-muted-foreground" data-testid="sector-definition">{draft.indicator.definition[language]}</p>
        </Step>
        <Step n={3} title={t('sectorFlow.area')}>
          {draft.areas.length > 1 ? (
            <SelectField label={t('sectorFlow.area')} labelClassName="sr-only" value={draft.selection.area}
              onValueChange={(v) => change({ area: v, breakdown: NO_CHOICE, view: undefined })}
              options={draft.areas.map((a) => ({ value: a.code, label: a.name[language] }))} data-testid="sector-area" />
          ) : (
            <p className="text-sm" data-testid="sector-area-fixed">{draft.areas[0]?.name[language]}</p>
          )}
          {draft.breakdowns.length > 1 ? (
            <SelectField label={t('sectorFlow.breakdown')} value={draft.selection.breakdown}
              onValueChange={(v) => change({ breakdown: v, view: undefined })}
              options={draft.breakdowns.map((s) => ({ value: breakdownKey(s), label: breakdownName(s, language, t) }))}
              data-testid="sector-breakdown" />
          ) : null}
        </Step>
        <Step n={4} title={t('sectorFlow.stepPeriod')}>
          <span className="text-xs font-medium text-muted-foreground" aria-hidden="true">{t('sectorFlow.frequency')}</span>
          <Segmented label={t('sectorFlow.frequency')} value={draft.selection.view} testId="sector-frequency" className="w-full"
            onChange={(v) => change({ view: v })}
            options={VIEWS.map((v) => ({ value: v, label: t(`series.views.${v}`),
              note: draft.available.includes(v) ? undefined : t('series.viewUnavailable') }))} />
          {draft.entry.year_to_date.length ? (
            <p className="text-xs text-muted-foreground">{t('sectorFlow.ytdApart')}</p>
          ) : null}
          {noPeriods ? (
            <p role="status" className="text-sm" data-testid="sector-no-periods">{t('sectorFlow.noPeriods')}</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-1 2xl:grid-cols-2">
              <SelectField label={t('sectorFlow.from')} value={draft.selection.from} onValueChange={(v) => change({ from: v })}
                options={periodOptions} data-testid="sector-from" aria-invalid={error !== null} />
              <SelectField label={t('sectorFlow.to')} value={draft.selection.to} onValueChange={(v) => change({ to: v })}
                options={periodOptions} data-testid="sector-to" aria-invalid={error !== null} />
            </div>
          )}
          {complete.length ? (
            <p className="text-xs text-muted-foreground" data-testid="sector-coverage">
              {t('sectorFlow.coverage', {
                first: label(complete[0]!.start, draft.selection.view),
                last: label(complete[complete.length - 1]!.start, draft.selection.view),
                count: complete.length,
              })}
            </p>
          ) : null}
        </Step>
        {error ? <p role="alert" className="text-sm font-medium text-destructive" data-testid="sector-error">{t(`sectorFlow.errors.${error}`)}</p> : null}
        <Button type="submit" size="lg" className="w-full" disabled={noPeriods} data-testid="sector-show-results">
          <Table2 aria-hidden="true" />{t('sectorFlow.showResults')}
        </Button>
        {stale ? <p role="status" className="text-sm" data-testid="sector-stale">{t('sectorFlow.stale')}</p> : null}
      </form>

      {showing ? (
        <Results key={JSON.stringify(applied.selection)} section={section} title={title} resolved={applied}
          chart={chart} onChart={setChart} />
      ) : (
        <div className="flex flex-col gap-3 xl:col-start-2 3xl:row-start-1">
          {state.applied && !appliedValid ? (
            <p role="status" className="text-sm" data-testid="sector-applied-gone">{t('sectorFlow.appliedGone')}</p>
          ) : null}
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border-strong/50 bg-card/60 px-6 py-12 text-center"
            data-testid="sector-empty-results">
            <Table2 aria-hidden="true" className="size-8 text-muted-foreground" />
            <p className="max-w-md text-base text-muted-foreground">{t('sectorFlow.emptyResults')}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function Results({ section, title, resolved, chart, onChart }: {
  section: SectionCode;
  title: string;
  resolved: Resolved;
  chart: boolean;
  onChart: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const link = usePreservedSearch();
  const chartId = useId();
  const [stock, setStock] = useState<StockAssumption>('assumed_zero');
  const { selection, indicator, entry, periods } = resolved;
  const [commodity, partner, flow] = selection.breakdown.split('|');
  const toEnd = periods.find((p) => p.start === selection.to)?.end ?? selection.to;
  const query: TimelineQuery = {
    dataMode: mode, indicator: selection.indicator, area: selection.area, view: selection.view,
    periodFrom: selection.from, periodTo: toEnd, commodity: commodity || null, partner: partner || null, flow: flow || null,
  };
  const timeline = useTimeline(query);
  const loaded = timeline.data?.status === 'ok' ? timeline.data : null;
  // The published series of exactly this selection and range, for the questions below.
  const sectionSeries = useSectionSeries(section, mode, selection.view);
  const scoped = (sectionSeries.data?.status === 'ok' ? sectionSeries.data.series : [])
    .filter((s) => s.indicatorCode === selection.indicator && (s.area?.code ?? 'OM') === selection.area
      && (s.commodityCode ?? '') === commodity && (s.partnerCode ?? '') === partner && (s.flow ?? '') === flow)
    .map((s) => ({ ...s, observations: s.observations.filter((o) => o.periodEnd >= selection.from && o.periodStart <= toEnd) }));
  const filters: SectionFilters = {
    frequency: selection.view, area: selection.area, indicator: selection.indicator, commodity: commodity || undefined,
    partner: partner || 'total', flow: flow || undefined, period_from: selection.from, period_to: toEnd,
    stock_assumption: section === 'food_security' ? stock : undefined,
  };
  const fromLabel = periodLabel(selection.from, selection.view, language);
  const toLabel = periodLabel(selection.to, selection.view, language);
  const range = selection.from === selection.to ? fromLabel : `${fromLabel} – ${toLabel}`;
  const details = [
    indicator.name[language],
    entry.area.name[language],
    t(`series.views.${selection.view}`),
    entry.partner || entry.commodity || entry.flow ? breakdownName(entry, language, t) : null,
    `${t('series.unit')}: ${entry.unit.label[language]}`,
  ].filter(Boolean).join(' · ');
  const question = t('sectorFlow.analysisQuestion', {
    indicator: indicator.name[language], area: entry.area.name[language], frequency: t(`series.views.${selection.view}`), range,
  });
  const ask = link(`/assistant?${new URLSearchParams({
    sector: section, q: question, ind: selection.indicator, area: selection.area, view: selection.view,
    from: selection.from, to: toEnd, sl: `${indicator.name[language]} · ${entry.area.name[language]} · ${range}`,
    ...(commodity ? { cm: commodity } : {}), ...(partner ? { pt: partner } : {}), ...(flow ? { fl: flow } : {}),
  }).toString()}`);

  return (
    <>
      {/* The results: what was chosen, its quality, the summary, the table and (on request) the chart. */}
      <section aria-labelledby={`${section}-results-h`} className="flex min-w-0 flex-col gap-5 xl:col-start-2 3xl:row-start-1" data-testid="sector-results"
        data-from={selection.from} data-to={selection.to} data-view={selection.view} data-indicator={selection.indicator}>
        <div className="flex flex-col gap-3 rounded-lg border border-border border-s-4 border-s-primary bg-card px-4 py-4 shadow-card sm:px-5" data-testid="applied-period">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">{t('sectorFlow.resultsFor')}</p>
              <h2 id={`${section}-results-h`} className="text-2xl font-semibold" data-testid="applied-range">{range}</h2>
              <p className="text-sm" data-testid="applied-details">{details}</p>
            </div>
            {scoped[0] ? <WatchButton series={scoped[0]} /> : null}
          </div>
          {loaded ? <QualityBadges quality={qualityOf(loaded, mode)} /> : null}
        </div>

        <TimelineState query={timeline}>{(data) => (
          <>
            <Summary timeline={data} from={selection.from} />
            <Panel id={`${section}-table-h`} title={t('sectorFlow.tableHeading')} icon={<Table2 aria-hidden="true" className="size-4 text-primary" />}>
              <TimelineTable timeline={data} query={query} />
            </Panel>
            <Panel id={`${section}-chart-h`} title={t('sectorFlow.chartHeading')} icon={<BarChart3 aria-hidden="true" className="size-4 text-primary" />}
              action={
                <Button variant="outline" size="sm" aria-expanded={chart} aria-controls={chartId} onClick={() => onChart(!chart)}
                  data-testid={chart ? 'sector-hide-chart' : 'sector-show-chart'}>
                  {chart ? <EyeOff aria-hidden="true" /> : <BarChart3 aria-hidden="true" />}
                  {chart ? t('sectorFlow.hideChart') : t('sectorFlow.showChart')}
                </Button>
              }>
              <div id={chartId} hidden={!chart}>
                {chart ? (
                  <div className="flex flex-col gap-3" data-testid="sector-chart">
                    <TimelineChart timeline={data} />
                    <p className="text-xs text-muted-foreground">{t('sectorFlow.chartNote')}</p>
                  </div>
                ) : null}
              </div>
            </Panel>
            <TimelineRules timeline={data} />
          </>
        )}</TimelineState>

        <details className="group rounded-lg border border-border bg-card p-4 shadow-card" data-testid="sector-calculations">
          <summary className="cursor-pointer text-base font-semibold">{t('sectorFlow.calcHeading')}</summary>
          <div className="mt-3 flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">{t('sectorFlow.calcNote', { range })}</p>
            {section === 'food_security' ? (
              <SelectField label={t('analysis.stockAssumption')} value={stock} className="max-w-xs"
                onValueChange={(v) => setStock(STOCK_OPTIONS.find((o) => o === v) ?? 'assumed_zero')}
                options={STOCK_OPTIONS.map((o) => ({ value: o, label: t(`analysis.stock.${o}`) }))} data-testid="filter-stock" />
            ) : null}
            {mode === 'verified_source' ? <DataQualityNotes section={section} /> : null}
            <AnalysisPanel section={section} mode={mode} filters={filters} headingLevel={3} />
          </div>
        </details>
        <details className="group rounded-lg border border-border bg-card p-4 shadow-card" data-testid="sector-reviews">
          <summary className="cursor-pointer text-base font-semibold">{t('sectorFlow.reviewHeading')}</summary>
          <div className="mt-3 flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">{t('sectorFlow.reviewNote')}</p>
            <ReviewCards mode={mode} section={section} headingLevel={3} />
          </div>
        </details>
      </section>

      {/* AI insights and sources: beside the results on wide screens, under them otherwise. */}
      <aside aria-label={t('sectorFlow.insightsLabel')} className="flex min-w-0 flex-col gap-5 xl:col-start-2 3xl:col-start-3 3xl:row-start-1"
        data-testid="sector-insights-panel">
        <Panel id={`${section}-ai-h`} title={t('sectorFlow.aiHeading')} icon={<Bot aria-hidden="true" className="size-4 text-primary" />}
          className="border-t-4 border-t-copper" testId="sector-next">
          <p className="text-sm text-muted-foreground">{t('sectorFlow.aiLead')}</p>
          <Link to={ask} className={cn(buttonVariants(), 'w-full')} data-testid="sector-request-analysis">
            <Bot aria-hidden="true" />{t('sectorFlow.requestAnalysis')}
          </Link>
          {loaded ? (
            <SpokenSummary selection={{
              data_mode: mode, indicator: selection.indicator, area: selection.area, view: selection.view,
              period_from: selection.from, period_to: toEnd,
              ...(commodity ? { commodity } : {}), ...(partner ? { partner } : {}), ...(flow ? { flow } : {}),
            }} />
          ) : null}
          <div className="flex flex-wrap gap-2 border-t border-border pt-3">
            <SaveReportButton section={section} mode={mode} filters={filters} defaultTitle={`${title} · ${range}`} />
            <Link to={link(`/studies?create=${section}`)} className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="sector-create-study">
              <FlaskConical aria-hidden="true" />{t('jobs.create')}
            </Link>
            <Link to={link('/assistant')} className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="sector-balance-link">
              <Scale aria-hidden="true" />{t('sector.balanceLink')}
            </Link>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{t('sectorFlow.exportsNote')}</span>
            <ExportLinks section={section} mode={mode} filters={filters} only="observations" />
          </div>
        </Panel>

        <Panel id={`${section}-questions-h`} title={t('sectorFlow.questionsHeading')}>
          <SectionInsights section={section} mode={mode} filters={filters} series={scoped} columns={1} />
        </Panel>

        <Panel id={`${section}-sources-h`} title={t('sector.parts.sources')} icon={<BookOpen aria-hidden="true" className="size-4 text-primary" />}>
          {loaded ? <TimelineSources timeline={loaded} /> : null}
          <p className="text-sm">
            <Link to={link('/sources')} className="text-primary underline underline-offset-2">{t('sector.allSources')}</Link>
          </p>
        </Panel>
      </aside>
    </>
  );
}

/** One summary figure: the number (and a percentage) kept left-to-right, the unit in the
 * page's own direction, so an Arabic unit never scrambles the number. */
function Figure({ label, number, unit, extra, text, note, testId }: {
  label: string;
  number?: string | null;
  unit?: string;
  extra?: string | null;
  text?: string | null;
  note?: string;
  testId: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-card p-4 shadow-card" data-testid={testId}>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold tabular-nums">
        {number != null ? (
          <>
            <bdi dir="ltr">{number}</bdi> <span className="text-sm font-medium text-muted-foreground">{unit}</span>
            {extra ? <> <bdi dir="ltr" className="text-sm">{extra}</bdi></> : null}
          </>
        ) : <span className="text-sm font-normal">{text ?? '—'}</span>}
      </dd>
      {note ? <dd className="text-xs text-muted-foreground">{note}</dd> : null}
    </div>
  );
}

function Summary({ timeline, from }: { timeline: Timeline; from: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const s: TimelineSummary | undefined = timeline.summary;
  const unit = timeline.unit?.label[language] ?? '';
  const view = timeline.view;
  if (!s) return null;
  const value = (p: { value: string | null; value_operator: string | null } | null) =>
    p?.value != null ? `${p.value_operator ?? ''}${formatDecimal(p.value, language, 3) ?? ''}` : null;
  const at = (p: { period_start: string } | null) => (p ? periodLabel(p.period_start, view, language) : undefined);
  // Year-on-year changes in the table may compare with a period before the selected range.
  const outside = [...new Set(timeline.rows.flatMap((r) => r.changes)
    .map((c) => c.against).filter((a): a is string => Boolean(a) && (a as string) < from))].sort();
  const c = s.change;
  const signed = (v: string, digits: number) => {
    const n = Number(v);
    return `${n > 0 ? '+' : n < 0 ? '−' : ''}${formatDecimal(v.replace('-', ''), language, digits) ?? ''}`;
  };
  const changeNumber = c?.absolute != null ? signed(c.absolute, 3) : null;
  const changePercent = c?.percent != null ? `(${signed(c.percent, 1)}%)` : null;
  const changeReason = c && c.absolute === null ? (c.reason?.[language] ?? t('series.notCalculated')) : null;

  return (
    <section aria-labelledby="sector-summary-h" className="flex flex-col gap-3" data-testid="sector-summary">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id="sector-summary-h" className="text-base font-semibold">{t('sectorFlow.summaryHeading')}</h3>
        <p className="text-xs text-muted-foreground" data-testid="sector-summary-note">{t('sectorFlow.summaryNote')}</p>
      </div>
      <p className="text-sm" data-testid="sector-summary-counts">
        {t('sectorFlow.periodsShown', { count: s.periods, withValue: s.with_value, missing: s.missing })}
      </p>
      {s.with_value === 0 ? (
        <p role="status" className="text-sm font-medium" data-testid="sector-summary-empty">
          {timeline.year_to_date.length ? t('sectorFlow.onlyYtdInRange') : t('sectorFlow.noValuesInRange')}
        </p>
      ) : (
        <dl className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <Figure label={t('sectorFlow.latest')} number={value(s.last)} unit={unit} note={at(s.last)} testId="summary-latest" />
          {s.first && s.last && s.first.period_start !== s.last.period_start ? (
            <Figure label={t('sectorFlow.changeFirstLatest', { first: at(s.first) ?? '', last: at(s.last) ?? '' })}
              number={changeNumber} unit={unit} extra={changePercent} text={changeReason} testId="summary-change" />
          ) : null}
          {s.highest ? <Figure label={t('sectorFlow.highest')} number={value(s.highest)} unit={unit} note={at(s.highest)} testId="summary-highest" /> : null}
          {s.lowest ? <Figure label={t('sectorFlow.lowest')} number={value(s.lowest)} unit={unit} note={at(s.lowest)} testId="summary-lowest" /> : null}
          {s.total !== null ? (
            <Figure label={t('sectorFlow.total')} number={formatDecimal(s.total, language, 3)} unit={unit} testId="summary-total" />
          ) : null}
        </dl>
      )}
      {s.total_reason && s.with_value > 1 ? (
        <p className="text-xs text-muted-foreground" data-testid="summary-total-reason" data-reason={s.total_reason.code}>{s.total_reason[language]}</p>
      ) : null}
      {outside.length ? (
        <p className="text-xs text-muted-foreground" data-testid="summary-comparison-outside">
          {t('sectorFlow.comparisonOutside', { periods: outside.map((a) => periodLabel(a, view, language)).join(', ') })}
        </p>
      ) : null}
    </section>
  );
}
