import {
  ArrowLeft, ArrowRight, BarChart3, Bot, CheckCircle2, Download, EyeOff, FileText, ListChecks, RotateCcw, Sparkles, Table2, Target,
  TriangleAlert,
} from 'lucide-react';
import type { TFunction } from 'i18next';
import { useEffect, useId, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { SectionFilters } from '@/api/analysis';
import { adapterKind } from '@/api/config';
import { useAreaRegistry } from '@/api/geography';
import { OBJECTIVES, useGuidance, type Guidance, type GuidanceRequest, type Objective } from '@/api/guidance';
import { useAvailability, useTimeline, VIEWS, type AvailabilitySeries, type AvailableIndicator, type TimelineQuery } from '@/api/series';
import { AnalysisPanel } from '@/components/analysis/AnalysisPanel';
import { ReviewCards } from '@/components/analysis/ReviewCards';
import { SaveReportButton } from '@/components/analysis/SaveReportButton';
import { DataQualityNotes } from '@/components/common/DataQualityNotes';
import { QualityBadges, qualityOf } from '@/components/common/QualityBadges';
import { StatePanel } from '@/components/common/StatePanel';
import { AreaComparison } from '@/components/sector/AreaComparison';
import { AskMulhim } from '@/components/sector/AskMulhim';
import { DecisionBrief } from '@/components/sector/DecisionBrief';
import { SectorReports } from '@/components/sector/SectorReports';
import {
  breakdownKey, breakdownName, NO_CHOICE, Panel, resolve, sortIndicators, STOCK_OPTIONS, Summary, type Resolved, type StockAssumption,
} from '@/components/sector/SectorWorkflow';
import { TimelineState } from '@/components/series/SectorSeries';
import { periodLabel, TimelineChart, TimelineRules, TimelineSources, TimelineTable } from '@/components/series/SeriesParts';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { RecentStudies } from '@/components/workspace/DashboardPanels';
import { SelectionStudy } from '@/components/workspace/SelectionStudy';
import type { DataMode, SectionCode } from '@/domain/types';
import { csvField, download, safeCell } from '@/lib/exportResults';
import type { AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import {
  GUIDE_STEPS, governorateOf, hasObjectives, MAX_GOAL_LENGTH, P, parseGoal, parseObjectives, parseSelection, parseStep, reachableStep,
  stepIndex, writeSelection, type GuideStep,
} from '@/lib/guideSteps';
import { sameSelection, useSectorSelection, type SectorSelection } from '@/state/sectorSelections';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';
import { useUpdateSearch } from '@/state/useUpdateSearch';

/**
 * A sector's guided analysis, one task at a time (state/guide.ts): (1) choose the indicator,
 * governorate, wilayat where published, period and data mode; (2) see the published results;
 * (3) analyse them; (4) set objectives; (5) get recommendations for those objectives. Only the
 * current step is shown; each step appears after the person asks for it, and the heavier parts
 * (calculations, charts, the decision brief) load only in the step that shows them. The step,
 * the applied selection and the objectives live in the address, so Back, a reload or a shared
 * link return to the same place; the selection is shared with Tables and charts.
 *
 * One component for all four sectors. Every figure comes from published observations or the
 * server's calculations; the recommendations are rule-based (POST /analysis/{section}/guidance).
 */
export function SectorGuide({ section, title }: { section: SectionCode; title: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const availability = useAvailability(section, mode);
  if (adapterKind !== 'http') {
    return <StatePanel kind="not_implemented"><p className="text-base text-muted-foreground">{t('sectorFlow.requiresApi')}</p></StatePanel>;
  }
  if (availability.isPending) {
    return <p role="status" className="text-base text-muted-foreground" data-testid="sector-availability-loading">{t('sectorFlow.loadingAvailability')}</p>;
  }
  if (availability.isError) {
    return (
      <StatePanel kind="error" error={availability.error} onRetry={() => void availability.refetch()}>
        <p className="text-base">{t('sectorFlow.availabilityFailed')}</p>
      </StatePanel>
    );
  }
  const indicators = sortIndicators(section, availability.data.indicators, language);
  if (!indicators.length) {
    return (
      <div className="flex flex-col gap-6">
        <StatePanel kind={mode === 'verified_source' ? 'no_verified_data' : 'empty'}>
          <p className="text-base text-muted-foreground" data-testid="sector-no-data">{t('sectorFlow.noData')}</p>
        </StatePanel>
        <SectorReports section={section} />
      </div>
    );
  }
  return <Guide section={section} title={title} indicators={indicators} />;
}

/** The query, filters and labels of an applied selection (shared by results and analysis). */
function describe(resolved: Resolved, mode: DataMode, language: AppLanguage, t: TFunction) {
  const { selection, indicator, entry, periods } = resolved;
  const [commodity = '', partner = '', flow = ''] = selection.breakdown.split('|');
  const toEnd = periods.find((p) => p.start === selection.to)?.end ?? selection.to;
  const query: TimelineQuery = {
    dataMode: mode, indicator: selection.indicator, area: selection.area, view: selection.view,
    periodFrom: selection.from, periodTo: toEnd, commodity: commodity || null, partner: partner || null, flow: flow || null,
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
  return { query, commodity, partner, flow, toEnd, range, details };
}

function Guide({ section, title, indicators }: { section: SectionCode; title: string; indicators: AvailableIndicator[] }) {
  const [mode, setMode] = useDataMode();
  const [params] = useSearchParams();
  const update = useUpdateSearch();
  const { state, setDraft, apply } = useSectorSelection(section, mode);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [error, setError] = useState<'no_period' | 'order' | null>(null);

  // The applied selection: the address's, else the one this sector remembers.
  const urlSelection = useMemo(() => parseSelection(params), [params]);
  const appliedInput = urlSelection ?? state.applied;
  const applied = appliedInput ? resolve(appliedInput, indicators) : null;
  const appliedValid = Boolean(appliedInput && applied && sameSelection(applied.selection, appliedInput));
  const objectives = parseObjectives(params.get(P.goals));
  const goal = parseGoal(params.get(P.goal));
  const step = reachableStep(parseStep(params.get(P.step)), { applied: appliedValid, objectives, goal });

  // Tables and charts show the same selection: the remembered one follows the address.
  useEffect(() => {
    if (urlSelection && appliedValid && !sameSelection(state.applied, urlSelection)) apply(urlSelection);
  }, [urlSelection, appliedValid, state.applied, apply]);

  /** Moves to a step (a new history entry, so the browser's Back returns), focusing its heading. */
  const go = (next: GuideStep, mutate?: (p: URLSearchParams) => void) => {
    update((p) => {
      if (next === 'select') p.delete(P.step);
      else p.set(P.step, next);
      mutate?.(p);
    }, { replace: false });
    window.requestAnimationFrame(() => headingRef.current?.focus());
  };

  const draft = resolve(state.draft ?? appliedInput, indicators);
  const showing = appliedValid && applied ? applied : null;
  // What the page is about: the selection being made, or the applied one in the later steps.
  const current = step === 'select' ? draft : showing ?? draft;

  return (
    <div className="flex flex-col gap-5" data-testid="sector-guide" data-step={step} data-section={section}
      data-indicator={current?.selection.indicator} data-area={current?.selection.area} data-view={current?.selection.view}>
      <Stepper step={step} onGo={(s) => go(s)} />
      {step === 'select' && draft ? (
        <SelectStep section={section} title={title} draft={draft} indicators={indicators} error={error} headingRef={headingRef}
          mode={mode} onMode={setMode}
          onChange={(next) => {
            setError(null);
            const r = resolve({ ...draft.selection, ...next }, indicators);
            if (r) setDraft(r.selection);
          }}
          onSubmit={() => {
            const { from, to } = draft.selection;
            if (!from || !to) return setError('no_period');
            if (from > to) return setError('order');
            setError(null);
            apply(draft.selection);
            go('results', (p) => writeSelection(p, draft.selection));
          }}
          onCancel={showing ? () => { setDraft(showing.selection); go('results'); } : undefined} />
      ) : null}
      {step === 'results' && showing ? (
        <ResultsStep section={section} resolved={showing} headingRef={headingRef}
          onBack={() => go('select')} onNext={() => go('analysis')} />
      ) : null}
      {step === 'analysis' && showing ? (
        <AnalysisStep section={section} resolved={showing} headingRef={headingRef}
          onBack={() => go('results')} onNext={() => go('objectives')} />
      ) : null}
      {step === 'objectives' && showing ? (
        <ObjectivesStep initial={objectives} initialGoal={goal} headingRef={headingRef}
          onBack={() => go('analysis')}
          onNext={(chosen, written) => go('recommendations', (p) => {
            if (chosen.length) p.set(P.goals, chosen.join(','));
            else p.delete(P.goals);
            if (written.trim()) p.set(P.goal, written.trim().slice(0, MAX_GOAL_LENGTH));
            else p.delete(P.goal);
          })} />
      ) : null}
      {step === 'recommendations' && showing ? (
        <RecommendationsStep section={section} title={title} resolved={showing} objectives={objectives} goal={goal} headingRef={headingRef}
          onBack={() => go('objectives')}
          onRestart={() => go('select', (p) => { p.delete(P.goals); p.delete(P.goal); })} />
      ) : null}
    </div>
  );
}

/** Where the person is: the five steps, done ones reachable again, later ones not yet. */
function Stepper({ step, onGo }: { step: GuideStep; onGo: (step: GuideStep) => void }) {
  const { t } = useTranslation();
  const current = stepIndex(step);
  return (
    <nav aria-label={t('guide.stepsLabel')} data-testid="guide-steps">
      <ol className="flex flex-wrap gap-2">
        {GUIDE_STEPS.map((s, i) => {
          const done = i < current;
          const label = (
            <>
              <span aria-hidden="true" className={cn('flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                i === current ? 'bg-primary text-primary-foreground' : done ? 'bg-verified text-verified-foreground' : 'bg-muted text-muted-foreground')}>
                {done ? <CheckCircle2 className="size-4" /> : i + 1}
              </span>
              <span>{t(`guide.steps.${s}`)}</span>
            </>
          );
          return (
            <li key={s} data-testid={`guide-step-${s}`} data-state={i === current ? 'current' : done ? 'done' : 'upcoming'}>
              {done ? (
                <button type="button" onClick={() => onGo(s)}
                  className="inline-flex min-h-10 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm hover:bg-muted">
                  {label}<span className="sr-only">{t('guide.returnTo')}</span>
                </button>
              ) : (
                <span aria-current={i === current ? 'step' : undefined}
                  className={cn('inline-flex min-h-10 items-center gap-2 rounded-full border px-3 text-sm',
                    i === current ? 'border-primary bg-primary-soft font-semibold' : 'border-dashed border-border text-muted-foreground')}>
                  {label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function StepFrame({ id, step, heading, lead, headingRef, children, actions, testId }: {
  id: string; step: GuideStep; heading: string; lead: string; headingRef: RefObject<HTMLHeadingElement | null>;
  children: ReactNode; actions: ReactNode; testId: string;
}) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-5" data-testid={testId}>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-muted-foreground">{t('guide.stepOf', { n: stepIndex(step) + 1, total: GUIDE_STEPS.length })}</p>
        <h2 id={id} ref={headingRef} tabIndex={-1} className="text-2xl font-semibold outline-none">{heading}</h2>
        <p className="max-w-3xl text-base text-muted-foreground">{lead}</p>
      </div>
      {children}
      <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-2 border-t border-border bg-background/95 px-1 py-3 backdrop-blur"
        data-testid="guide-actions">
        {actions}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- step 1: selection

function SelectStep({ section, title, draft, indicators, error, headingRef, mode, onMode, onChange, onSubmit, onCancel }: {
  section: SectionCode; title: string; draft: Resolved; indicators: AvailableIndicator[]; error: 'no_period' | 'order' | null;
  headingRef: RefObject<HTMLHeadingElement | null>; mode: DataMode; onMode: (m: DataMode) => void;
  onChange: (next: Partial<SectorSelection>) => void; onSubmit: () => void; onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const formId = useId();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const registry = useAreaRegistry();
  const parents = useMemo(() => new Map((registry.data?.areas ?? []).map((a) => [a.code, a.parent_code])), [registry.data]);
  const regNames = useMemo(() => new Map((registry.data?.areas ?? []).map((a) => [a.code, language === 'ar' ? a.name_ar : a.name_en])), [registry.data, language]);
  const { selection } = draft;

  // Areas with this indicator published: Oman, governorates, and wilayats under their governorate.
  const isWilayat = (a: AvailabilitySeries['area']) => a.level === 'wilayat' || /^OM-[A-Z]{2}-\d+$/.test(a.code);
  const byName = (a: string, b: string) => a.localeCompare(b, language);
  const own = new Map(draft.areas.map((a) => [a.code, a.name[language]]));
  const governorates = [...new Set(draft.areas.filter((a) => a.code !== 'OM').map((a) => (isWilayat(a) ? governorateOf(a.code, parents) : a.code)))]
    .map((code) => ({ code, name: own.get(code) ?? regNames.get(code) ?? code }))
    .sort((a, b) => byName(a.name, b.name));
  const current = draft.areas.find((a) => a.code === selection.area);
  const gov = selection.area === 'OM' ? 'OM' : current && isWilayat(current) ? governorateOf(current.code, parents) : selection.area;
  const wilayats = draft.areas.filter((a) => isWilayat(a) && governorateOf(a.code, parents) === gov)
    .sort((a, b) => byName(a.name[language], b.name[language]));
  const govHasOwn = own.has(gov);
  const chooseGovernorate = (code: string) => {
    if (code === 'OM' || own.has(code)) return onChange({ area: code, breakdown: NO_CHOICE, view: undefined });
    const first = draft.areas.filter((a) => isWilayat(a) && governorateOf(a.code, parents) === code)
      .sort((a, b) => byName(a.name[language], b.name[language]))[0];
    if (first) onChange({ area: first.code, breakdown: NO_CHOICE, view: undefined });
  };

  const label = (start: string) => periodLabel(start, selection.view, language);
  const periodOptions = [{ value: NO_CHOICE, label: t('sectorFlow.choosePeriod') },
    ...draft.periods.map((p) => ({ value: p.start, label: p.ytdOnly ? t('sectorFlow.ytdOnly', { period: label(p.start) }) : label(p.start) }))];
  const noPeriods = draft.periods.length === 0;
  const complete = draft.periods.filter((p) => !p.ytdOnly);

  return (
    <StepFrame id={`${formId}-h`} step="select" heading={t('guide.selectHeading')} lead={t('guide.selectLead')} headingRef={headingRef}
      testId="guide-select"
      actions={(
        <>
          <Button type="submit" form={formId} size="lg" disabled={noPeriods} data-testid="sector-show-results">
            <Table2 aria-hidden="true" />{t('sectorFlow.showResults')}
          </Button>
          {onCancel ? (
            <Button type="button" variant="ghost" onClick={onCancel} data-testid="guide-cancel">{t('guide.keepResults')}</Button>
          ) : null}
        </>
      )}>
      <form id={formId} className="grid gap-5 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5 lg:grid-cols-2" data-testid="sector-form"
        aria-labelledby={`${formId}-h`} onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        <div className="flex flex-col gap-1.5 lg:col-span-2">
          <span className="text-sm font-medium">{t('sectorFlow.stepSector')}</span>
          <p className="text-base font-medium" data-testid="sector-current">{title}</p>
        </div>
        <div className="flex flex-col gap-2 lg:col-span-2">
          <SelectField label={t('sectorFlow.indicator')} value={selection.indicator}
            onValueChange={(v) => onChange({ indicator: v, area: selection.area, breakdown: NO_CHOICE, view: undefined })}
            options={indicators.map((i) => ({ value: i.code, label: i.name[language] }))} data-testid="sector-indicator" />
          <p className="text-sm text-muted-foreground" data-testid="sector-definition">{draft.indicator.definition[language]}</p>
        </div>
        <SelectField label={t('guide.governorate')} value={gov} onValueChange={chooseGovernorate} data-testid="guide-governorate"
          options={[
            ...(own.has('OM') ? [{ value: 'OM', label: own.get('OM')! }] : []),
            ...governorates.map((g) => ({ value: g.code, label: g.name })),
          ]} />
        {gov !== 'OM' && wilayats.length ? (
          <SelectField label={t('guide.wilayat')} value={isWilayat(current ?? { code: '', level: null, name: { en: '', ar: '' } }) ? selection.area : ''}
            onValueChange={(v) => onChange({ area: v || gov, breakdown: NO_CHOICE, view: undefined })} data-testid="guide-wilayat"
            options={[...(govHasOwn ? [{ value: '', label: t('guide.wholeGovernorate') }] : []),
              ...wilayats.map((w) => ({ value: w.code, label: w.name[language] }))]} />
        ) : gov !== 'OM' ? (
          <p role="status" className="self-end text-sm text-muted-foreground" data-testid="guide-no-wilayat-data">
            {t('guide.noWilayatData', { governorate: own.get(gov) ?? regNames.get(gov) ?? gov })}
          </p>
        ) : <span />}
        {draft.breakdowns.length > 1 ? (
          <SelectField label={t('sectorFlow.breakdown')} value={selection.breakdown} className="lg:col-span-2"
            onValueChange={(v) => onChange({ breakdown: v, view: undefined })}
            options={draft.breakdowns.map((s) => ({ value: breakdownKey(s), label: breakdownName(s, language, t) }))} data-testid="sector-breakdown" />
        ) : null}
        <div className="flex flex-col gap-2 lg:col-span-2">
          <span className="text-sm font-medium" aria-hidden="true">{t('sectorFlow.frequency')}</span>
          <Segmented label={t('sectorFlow.frequency')} value={selection.view} testId="sector-frequency" className="w-full"
            onChange={(v) => onChange({ view: v })}
            options={VIEWS.map((v) => ({ value: v, label: t(`series.views.${v}`), note: draft.available.includes(v) ? undefined : t('series.viewUnavailable') }))} />
          {draft.entry.year_to_date.length ? <p className="text-sm text-muted-foreground">{t('sectorFlow.ytdApart')}</p> : null}
        </div>
        {noPeriods ? (
          <p role="status" className="text-base lg:col-span-2" data-testid="sector-no-periods">{t('sectorFlow.noPeriods')}</p>
        ) : (
          <>
            <SelectField label={t('sectorFlow.from')} value={selection.from} onValueChange={(v) => onChange({ from: v })}
              options={periodOptions} data-testid="sector-from" aria-invalid={error !== null} />
            <SelectField label={t('sectorFlow.to')} value={selection.to} onValueChange={(v) => onChange({ to: v })}
              options={periodOptions} data-testid="sector-to" aria-invalid={error !== null} />
          </>
        )}
        {complete.length ? (
          <p className="text-sm text-muted-foreground lg:col-span-2" data-testid="sector-coverage">
            {t('sectorFlow.coverage', { first: label(complete[0]!.start), last: label(complete[complete.length - 1]!.start), count: complete.length })}
          </p>
        ) : null}
        <div className="flex flex-col gap-2 lg:col-span-2">
          <span className="text-sm font-medium" aria-hidden="true">{t('dataMode.label')}</span>
          <Segmented label={t('dataMode.label')} value={mode} onChange={onMode} testId="guide-data-mode" className="w-full max-w-md"
            options={[{ value: 'verified_source', label: t('dataMode.verified_source') }, { value: 'synthetic', label: t('dataMode.synthetic') }]} />
        </div>
        {error ? <p role="alert" className="text-base font-medium text-destructive lg:col-span-2" data-testid="sector-error">{t(`sectorFlow.errors.${error}`)}</p> : null}
      </form>
      {/* The sector's saved reports and this session's studies (no separate pages for them). */}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <SectorReports section={section} />
        <RecentStudies onOpen={(id) => void navigate(to(`/assistant?${new URLSearchParams({ study: id }).toString()}`))} />
      </div>
    </StepFrame>
  );
}

// ---------------------------------------------------------------- step 2: results

function AppliedHeader({ resolved, testId = 'applied-period' }: { resolved: Resolved; testId?: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const { query, range, details } = describe(resolved, mode, language, t);
  const timeline = useTimeline(query);
  const loaded = timeline.data?.status === 'ok' ? timeline.data : null;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border border-s-4 border-s-primary bg-card px-4 py-4 shadow-card sm:px-5" data-testid={testId}>
      <div className="min-w-0">
        <p className="text-sm font-medium text-muted-foreground">{t('sectorFlow.resultsFor')}</p>
        <p className="text-2xl font-semibold" data-testid="applied-range">{range}</p>
        <p className="text-base" data-testid="applied-details">{details}</p>
      </div>
      {loaded ? <QualityBadges quality={qualityOf(loaded, mode)} /> : null}
    </div>
  );
}

function ResultsStep({ section, resolved, headingRef, onBack, onNext }: {
  section: SectionCode; resolved: Resolved; headingRef: RefObject<HTMLHeadingElement | null>; onBack: () => void; onNext: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const { selection } = resolved;
  const { query } = describe(resolved, mode, language, t);
  const timeline = useTimeline(query);
  return (
    <StepFrame id={`${section}-results-h`} step="results" heading={t('guide.resultsHeading')} lead={t('guide.resultsLead')} headingRef={headingRef}
      testId="sector-results"
      actions={(
        <>
          <Button variant="outline" onClick={onBack} data-testid="guide-back"><ArrowLeft aria-hidden="true" className="rtl:rotate-180" />{t('guide.changeSelection')}</Button>
          <Button size="lg" onClick={onNext} disabled={timeline.data?.status !== 'ok'} data-testid="guide-analyze">
            <Sparkles aria-hidden="true" />{t('guide.analyze')}<ArrowRight aria-hidden="true" className="rtl:rotate-180" />
          </Button>
        </>
      )}>
      <div data-from={selection.from} data-to={selection.to} data-view={selection.view} data-indicator={selection.indicator} data-area={selection.area}
        className="flex flex-col gap-5" data-testid="guide-results-body">
        <AppliedHeader resolved={resolved} />
        <TimelineState query={timeline}>{(data) => (
          <>
            <Summary timeline={data} from={selection.from} />
            <Panel id={`${section}-table-h`} title={t('sectorFlow.tableHeading')} icon={<Table2 aria-hidden="true" className="size-4 text-primary" />}>
              <TimelineTable timeline={data} query={query} />
            </Panel>
            <details className="rounded-lg border border-border bg-card p-4 shadow-card" data-testid="guide-sources">
              <summary className="cursor-pointer text-base font-semibold">{t('sector.parts.sources')}</summary>
              <div className="mt-3"><TimelineSources timeline={data} /></div>
            </details>
          </>
        )}</TimelineState>
      </div>
    </StepFrame>
  );
}

// ---------------------------------------------------------------- step 3: analysis

function AnalysisStep({ section, resolved, headingRef, onBack, onNext }: {
  section: SectionCode; resolved: Resolved; headingRef: RefObject<HTMLHeadingElement | null>; onBack: () => void; onNext: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const chartId = useId();
  const [chart, setChart] = useState(false);
  const [brief, setBrief] = useState(false);
  const [stock, setStock] = useState<StockAssumption>('assumed_zero');
  const { selection, indicator, entry } = resolved;
  const { query, commodity, partner, flow, toEnd } = describe(resolved, mode, language, t);
  const timeline = useTimeline(query);
  const filters: SectionFilters = {
    frequency: selection.view, area: selection.area, indicator: selection.indicator, commodity: commodity || undefined,
    partner: partner || 'total', flow: flow || undefined, period_from: selection.from, period_to: toEnd,
    stock_assumption: section === 'food_security' ? stock : undefined,
  };
  return (
    <StepFrame id={`${section}-analysis-h`} step="analysis" heading={t('guide.analysisHeading')} lead={t('guide.analysisLead')} headingRef={headingRef}
      testId="sector-analysis"
      actions={(
        <>
          <Button variant="outline" onClick={onBack} data-testid="guide-back"><ArrowLeft aria-hidden="true" className="rtl:rotate-180" />{t('guide.back')}</Button>
          <Button size="lg" onClick={onNext} data-testid="guide-set-objectives">
            <Target aria-hidden="true" />{t('guide.setObjectives')}<ArrowRight aria-hidden="true" className="rtl:rotate-180" />
          </Button>
        </>
      )}>
      <AppliedHeader resolved={resolved} testId="guide-analysis-scope" />
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Panel id={`${section}-findings-h`} title={t('guide.findings')} icon={<Sparkles aria-hidden="true" className="size-4 text-primary" />} testId="sector-findings">
          <SelectionStudy indicator={selection.indicator} area={selection.area} periodKind={selection.view} mode={mode} section={section} />
        </Panel>
        <Panel id={`${section}-calc-h`} title={t('guide.calculations')} testId="sector-calculations">
          {section === 'food_security' ? (
            <SelectField label={t('analysis.stockAssumption')} value={stock} className="max-w-xs"
              onValueChange={(v) => setStock(STOCK_OPTIONS.find((o) => o === v) ?? 'assumed_zero')}
              options={STOCK_OPTIONS.map((o) => ({ value: o, label: t(`analysis.stock.${o}`) }))} data-testid="filter-stock" />
          ) : null}
          <AnalysisPanel section={section} mode={mode} filters={filters} headingLevel={3} />
        </Panel>
      </div>
      <Panel id={`${section}-chart-h`} title={t('sectorFlow.chartHeading')} icon={<BarChart3 aria-hidden="true" className="size-4 text-primary" />}
        action={(
          <Button variant="outline" size="sm" aria-expanded={chart} aria-controls={chartId} onClick={() => setChart(!chart)}
            data-testid={chart ? 'sector-hide-chart' : 'sector-show-chart'}>
            {chart ? <EyeOff aria-hidden="true" /> : <BarChart3 aria-hidden="true" />}{chart ? t('sectorFlow.hideChart') : t('sectorFlow.showChart')}
          </Button>
        )}>
        <div id={chartId} hidden={!chart}>
          {chart && timeline.data?.status === 'ok' ? (
            <div className="flex flex-col gap-3" data-testid="sector-chart">
              <TimelineChart timeline={timeline.data} />
              <p className="text-sm text-muted-foreground">{t('sectorFlow.chartNote')}</p>
            </div>
          ) : null}
        </div>
      </Panel>
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Panel id={`${section}-factors-h`} title={t('guide.factors')} testId="sector-reviews">
          <p className="text-sm text-muted-foreground">{t('guide.factorsNote')}</p>
          <ReviewCards mode={mode} section={section} headingLevel={3} compact />
        </Panel>
        <div className="flex min-w-0 flex-col gap-5">
          <AreaComparison indicator={selection.indicator} frequency={selection.view} />
          <Panel id={`${section}-limits-h`} title={t('guide.limitations')} icon={<TriangleAlert aria-hidden="true" className="size-4 text-sand-foreground" />}
            testId="guide-limitations">
            {timeline.data?.indicator.limitation[language] ? (
              <p className="text-sm" data-testid="guide-indicator-limitation">{timeline.data.indicator.limitation[language]}</p>
            ) : null}
            {timeline.data?.status === 'ok' ? <TimelineRules timeline={timeline.data} /> : null}
            {mode === 'verified_source' ? <DataQualityNotes section={section} /> : null}
          </Panel>
        </div>
      </div>
      <AskMulhim indicator={indicator.name[language]} area={entry.area.name[language]} />
      <details className="rounded-lg border border-border bg-card p-4 shadow-card" data-testid="guide-brief"
        onToggle={(e) => setBrief(e.currentTarget.open)}>
        <summary className="cursor-pointer text-base font-semibold">{t('guide.brief')}</summary>
        {/* Loaded only when opened. */}
        {brief ? <div className="mt-3"><DecisionBrief section={section} /></div> : null}
      </details>
    </StepFrame>
  );
}

// ---------------------------------------------------------------- step 4: objectives

function ObjectivesStep({ initial, initialGoal, headingRef, onBack, onNext }: {
  initial: readonly Objective[]; initialGoal: string; headingRef: RefObject<HTMLHeadingElement | null>;
  onBack: () => void; onNext: (objectives: Objective[], goal: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [chosen, setChosen] = useState<Objective[]>([...initial]);
  const [goal, setGoal] = useState(initialGoal);
  const [tried, setTried] = useState(false);
  const ready = hasObjectives({ objectives: chosen, goal });
  return (
    <StepFrame id={`${id}-h`} step="objectives" heading={t('guide.objectivesHeading')} lead={t('guide.objectivesLead')} headingRef={headingRef}
      testId="guide-objectives"
      actions={(
        <>
          <Button variant="outline" onClick={onBack} data-testid="guide-back"><ArrowLeft aria-hidden="true" className="rtl:rotate-180" />{t('guide.back')}</Button>
          <Button size="lg" aria-describedby={tried && !ready ? `${id}-need` : undefined} data-testid="guide-show-recommendations"
            onClick={() => { setTried(true); if (ready) onNext(OBJECTIVES.filter((o) => chosen.includes(o)), goal); }}>
            <ListChecks aria-hidden="true" />{t('guide.showRecommendations')}<ArrowRight aria-hidden="true" className="rtl:rotate-180" />
          </Button>
          {tried && !ready ? <p id={`${id}-need`} role="alert" className="text-sm font-medium text-destructive" data-testid="guide-need-objective">{t('guide.needObjective')}</p> : null}
        </>
      )}>
      <fieldset className="grid gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:grid-cols-2 sm:p-5" data-testid="guide-objective-list">
        <legend className="sr-only">{t('guide.objectivesHeading')}</legend>
        {OBJECTIVES.map((o) => (
          <label key={o} htmlFor={`${id}-${o}`} className={cn('grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-0.5 rounded-lg border p-3',
            chosen.includes(o) ? 'border-primary bg-primary-soft' : 'border-border hover:bg-muted')}>
            <input id={`${id}-${o}`} type="checkbox" className="row-span-2 mt-1 size-4 accent-primary" checked={chosen.includes(o)}
              aria-describedby={`${id}-${o}-help`} data-testid={`guide-objective-${o}`}
              onChange={(e) => setChosen((c) => (e.target.checked ? [...c, o] : c.filter((x) => x !== o)))} />
            <span className="font-medium">{t(`guide.objectives.${o}`)}</span>
            <span id={`${id}-${o}-help`} className="text-sm text-muted-foreground">{t(`guide.objectiveHelp.${o}`)}</span>
          </label>
        ))}
      </fieldset>
      <div className="flex max-w-3xl flex-col gap-1.5">
        <label htmlFor={`${id}-goal`} className="text-sm font-medium">{t('guide.goalLabel')}</label>
        <textarea id={`${id}-goal`} value={goal} maxLength={MAX_GOAL_LENGTH} rows={3} onChange={(e) => setGoal(e.target.value)}
          aria-describedby={`${id}-goal-help`} className="rounded-md border border-border-strong bg-card p-3 text-base" data-testid="guide-goal" />
        <p id={`${id}-goal-help`} className="text-sm text-muted-foreground">{t('guide.goalHelp', { max: MAX_GOAL_LENGTH })}</p>
      </div>
    </StepFrame>
  );
}

// ---------------------------------------------------------------- step 5: recommendations

function guidanceCsv(g: Guidance, language: AppLanguage, meta: string[]): string {
  const header = ['rank', 'objective', 'action', 'rationale', 'prerequisites', 'risks', 'missing_evidence'];
  const lines = [...meta.map((m) => csvField(safeCell(`# ${m}`))), header.join(',')];
  for (const a of g.actions) {
    lines.push([
      String(a.rank),
      safeCell(a.objective?.name[language] ?? ''),
      safeCell(a.title[language]),
      safeCell(a.rationale[language]),
      safeCell(a.prerequisites.map((p) => p[language]).join(' | ')),
      safeCell(a.risks.map((r) => r[language]).join(' | ')),
      safeCell(a.missing_evidence.map((m) => m[language]).join(' | ')),
    ].map(csvField).join(','));
  }
  return `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`;
}

function RecommendationsStep({ section, title, resolved, objectives, goal, headingRef, onBack, onRestart }: {
  section: SectionCode; title: string; resolved: Resolved; objectives: readonly Objective[]; goal: string;
  headingRef: RefObject<HTMLHeadingElement | null>; onBack: () => void; onRestart: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const link = usePreservedSearch();
  const { selection, indicator, entry } = resolved;
  const { commodity, partner, flow, toEnd, range } = describe(resolved, mode, language, t);
  const request: GuidanceRequest = {
    section, mode, indicator: selection.indicator, area: selection.area, view: selection.view,
    commodity, partner, flow, periodFrom: selection.from, periodTo: toEnd, objectives, note: goal,
  };
  const guidance = useGuidance(request);
  const g = guidance.data;
  const filters: SectionFilters = {
    frequency: selection.view, area: selection.area, indicator: selection.indicator, commodity: commodity || undefined,
    partner: partner || 'total', flow: flow || undefined, period_from: selection.from, period_to: toEnd,
  };
  const names = (g?.objectives ?? []).map((o) => o.name[language]);
  const question = t('guide.fullReportQuestion', {
    indicator: indicator.name[language], area: entry.area.name[language], range,
    objectives: names.length ? names.join(language === 'ar' ? '، ' : ', ') : goal,
  });
  const ask = link(`/assistant?${new URLSearchParams({
    sector: section, q: question, ind: selection.indicator, area: selection.area, view: selection.view,
    from: selection.from, to: toEnd, sl: `${indicator.name[language]} · ${entry.area.name[language]} · ${range}`,
    ...(commodity ? { cm: commodity } : {}), ...(partner ? { pt: partner } : {}), ...(flow ? { fl: flow } : {}),
  }).toString()}`);

  return (
    <StepFrame id={`${section}-recs-h`} step="recommendations" heading={t('guide.recommendationsHeading')} lead={t('guide.recommendationsLead')}
      headingRef={headingRef} testId="guide-recommendations"
      actions={(
        <>
          <Button variant="outline" onClick={onBack} data-testid="guide-back"><ArrowLeft aria-hidden="true" className="rtl:rotate-180" />{t('guide.changeObjectives')}</Button>
          <Button variant="ghost" onClick={onRestart} data-testid="guide-restart"><RotateCcw aria-hidden="true" />{t('guide.startAgain')}</Button>
        </>
      )}>
      <AppliedHeader resolved={resolved} testId="guide-recommendations-scope" />
      {goal ? <p className="text-sm text-muted-foreground" data-testid="guide-goal-echo" dir="auto">{t('guide.goalRecorded', { goal })}</p> : null}
      {guidance.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
      {guidance.isError ? <StatePanel kind="error" error={guidance.error} onRetry={() => void guidance.refetch()} /> : null}
      {g?.status === 'no_data' ? <p role="status" className="text-base" data-testid="guide-no-recommendation">{t('guide.noRecommendationData')}</p> : null}
      {g?.status === 'needs_objectives' ? (
        <div role="status" className="flex flex-col gap-3 rounded-lg border border-sand/60 bg-sand-subtle/60 p-4" data-testid="guide-goal-not-recognised">
          <p className="text-base">{t('guide.goalNotRecognised')}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={onBack}>{t('guide.changeObjectives')}</Button>
            <Link to={ask} className={buttonVariants({ size: 'sm' })}><Bot aria-hidden="true" />{t('guide.fullReport')}</Link>
          </div>
        </div>
      ) : null}
      {g?.status === 'ok' ? (
        <>
          <div className="flex flex-wrap gap-2" data-testid="guide-objectives-chosen">
            {g.objectives.map((o) => <Badge key={o.code} variant="outline"><Target aria-hidden="true" />{o.name[language]}</Badge>)}
          </div>
          <Panel id={`${section}-facts-h`} title={t('guide.facts')} testId="guide-facts">
            <ul className="flex flex-col gap-1 text-base">
              {g.facts.map((f) => <li key={f.id} data-fact={f.kind}><span className="font-mono text-xs text-muted-foreground">{f.id}</span> {f.text[language]}</li>)}
            </ul>
          </Panel>
          <ol className="flex flex-col gap-4" data-testid="guide-actions-list">
            {g.actions.map((a) => (
              <li key={a.rank} className={cn('flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-card sm:p-5',
                a.evidence === 'gap' ? 'border-dashed border-border-strong/60' : 'border-border border-s-4 border-s-primary')}
                data-testid="guide-action" data-rank={a.rank} data-objective={a.objective?.code ?? 'gap'} data-evidence={a.evidence}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={a.evidence === 'gap' ? 'muted' : 'verified'}>{t('guide.priority', { rank: a.rank })}</Badge>
                  {a.objective ? <Badge variant="outline">{a.objective.name[language]}</Badge> : null}
                  <span className="text-xs text-muted-foreground">{t(`guide.evidence.${a.evidence}`)}</span>
                </div>
                <h3 className="text-lg font-semibold">{a.title[language]}</h3>
                <p className="text-base"><span className="font-medium">{t('guide.rationale')}: </span>{a.rationale[language]}
                  {a.facts.length ? <span className="text-xs text-muted-foreground"> ({a.facts.join(', ')})</span> : null}</p>
                <dl className="grid gap-3 text-sm md:grid-cols-3">
                  {([['prerequisites', a.prerequisites], ['risks', a.risks], ['missingEvidence', a.missing_evidence]] as const).map(([key, items]) => (
                    items.length ? (
                      <div key={key} className="flex flex-col gap-1">
                        <dt className="font-medium">{t(`guide.${key}`)}</dt>
                        <dd><ul className="list-disc ps-5">{items.map((x) => <li key={x.en}>{x[language]}</li>)}</ul></dd>
                      </div>
                    ) : null
                  ))}
                </dl>
              </li>
            ))}
          </ol>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground" data-testid="guide-limits">
            {g.limitations.map((l) => <li key={l.en}>{l[language]}</li>)}
            <li>{t('guide.rulesVersion', { version: g.rules_version })}</li>
          </ul>
          <Panel id={`${section}-keep-h`} title={t('guide.exportsHeading')} icon={<FileText aria-hidden="true" className="size-4 text-primary" />} testId="guide-exports">
            <p className="text-sm text-muted-foreground">{t('guide.exportsNote')}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" data-testid="guide-download-csv"
                onClick={() => download(`osrip-recommendations-${section}-${selection.indicator}-${selection.area}.csv`,
                  guidanceCsv(g, language, [`${title} · ${indicator.name[language]} · ${entry.area.name[language]} · ${range}`, t('guide.rulesVersion', { version: g.rules_version })]),
                  'text/csv;charset=utf-8')}>
                <Download aria-hidden="true" />{t('guide.downloadCsv')}
              </Button>
              <SaveReportButton section={section} mode={mode} filters={filters} defaultTitle={`${title} · ${range}`} />
              <Link to={ask} className={buttonVariants({ size: 'sm' })} data-testid="guide-full-report"><Bot aria-hidden="true" />{t('guide.fullReport')}</Link>
            </div>
          </Panel>
        </>
      ) : null}
    </StepFrame>
  );
}
