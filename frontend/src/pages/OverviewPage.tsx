import { ArrowRight, BarChart3, Clock, MapPinned, Sparkles } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { DataAdapterError } from '@/api/adapter';
import { adapterKind } from '@/api/config';
import { useAreaRegistry } from '@/api/geography';
import { useAreaComparison } from '@/api/library';
import { useSeries } from '@/api/queries';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { FilterBar } from '@/components/common/FilterBar';
import { IndicatorCard } from '@/components/common/IndicatorCard';
import { FREQUENCIES, mixedFrequencies, MixedFrequencyNotice } from '@/components/common/MixedFrequency';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { AssistantColumn } from '@/components/workspace/AssistantColumn';
import { DashboardCard, RecentStudies, SourcesPanel } from '@/components/workspace/DashboardPanels';
import { comparisonDataset, isStale, seriesDataset } from '@/components/workspace/datasets';
import { DatasetView } from '@/components/workspace/DatasetView';
import { LiveStudyPanel } from '@/components/workspace/LiveStudyPanel';
import { ResourceKpis } from '@/components/workspace/ResourceKpis';
import { SelectionStudy } from '@/components/workspace/SelectionStudy';
import { Tabs, tabPanelProps } from '@/components/workspace/Tabs';
import { WorkspaceLaunchpad } from '@/components/workspace/WorkspaceLaunchpad';
import { ALL, seriesKey } from '@/domain/filters';
import { DOMAINS, SECTION_PATHS } from '@/domain/sections';
import { DATA_MODES, type DomainCode, type SectionCode, type Series } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useMediaQuery } from '@/lib/useMediaQuery';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';
import { useUpdateSearch } from '@/state/useUpdateSearch';
import { useResetFilters, useUrlFilter } from '@/state/useUrlFilter';

const DOMAIN_TEXT = {
  energy_essential_services: { title: 'pages.energy.title', intro: 'pages.energy.intro' },
  food_security: { title: 'pages.food.title', intro: 'pages.food.intro' },
  trade: { title: 'pages.trade.title', intro: 'pages.trade.intro' },
} as const satisfies Record<DomainCode, { title: string; intro: string }>;

const SECTION_TITLE = {
  electricity: 'nav.electricity',
  water: 'nav.water',
  food_security: 'nav.foodSecurity',
  trade: 'nav.trade',
} as const satisfies Record<SectionCode, string>;

const DOMAIN_OPTIONS = [ALL, ...DOMAINS.map((d) => d.code)] as const;
const FILTER_PARAMS = ['domain', 'section', 'indicator', 'area', 'frequency', 'from', 'to'] as const;
const TABS = ['data', 'study', 'assistant'] as const;
type Tab = (typeof TABS)[number];

/** Series of one section, of one frequency when chosen (stated totals are picked later). */
function useSectionSeries(section: SectionCode, frequency?: string) {
  const [mode] = useDataMode();
  return useSeries(section, mode, frequency);
}

/** A card with a heading row, used for the workspace's main panels. */
function Panel({ id, title, icon, action, children, testId }: {
  id: string;
  title: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:p-5" data-testid={testId}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 id={id} className="flex items-center gap-2 text-sm font-semibold">{icon}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/**
 * The analytical workspace (the dashboard). Top: the four resources with their latest
 * published values. Then the filters (domain, section, indicator, period, geography and data
 * mode); the chosen indicator's history as one validated dataset drawn as chart and table,
 * beside the server's findings for that selection; the section's indicator cards; and below,
 * the governorate comparison, recent studies and the sources of what is shown. On wide screens
 * the assistant sits beside the analysis (a question there brings its live study forward in
 * the Study tab); on phones Data, Study and Assistant are tabs.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode, setMode] = useDataMode();
  const ui = useAssistantUi();
  const wide = useMediaQuery('(min-width: 1024px)');
  const update = useUpdateSearch();
  const [domain, setDomain] = useUrlFilter('domain', DOMAIN_OPTIONS, ALL);
  const visibleDomains = DOMAINS.filter((d) => domain === ALL || d.code === domain);
  const sectionOptions = visibleDomains.flatMap((d) => d.sections);
  const [section, setSection] = useUrlFilter<string>('section', [ALL, ...sectionOptions], ALL);
  const focusSection = (section === ALL ? sectionOptions[0] : section) as SectionCode;
  // A section can mix annual, year-to-date and monthly series of one indicator: those are not
  // shown side by side, so the person chooses one frequency here (or from the notice).
  const [frequency, setFrequency] = useUrlFilter<string>('frequency', [ALL, ...FREQUENCIES], ALL);
  const freq = frequency === ALL ? undefined : frequency;
  const series = useSectionSeries(focusSection, freq);
  const registry = useAreaRegistry();
  const governorates = (registry.data?.areas ?? []).filter((a) => a.level === 'governorate');
  const [area, setArea] = useUrlFilter<string>('area', [ALL, 'OM', ...governorates.map((g) => g.code)], ALL);
  const loaded: readonly Series[] = series.data?.status === 'ok' ? series.data.series.filter((s) => s.partnerCode === null) : [];
  const inArea = area === ALL ? loaded : loaded.filter((s) => (s.area?.code ?? 'OM') === area);
  const indicatorCodes = [...new Set(inArea.map((s) => s.indicatorCode))];
  const [indicator, setIndicator] = useUrlFilter<string>('indicator', [ALL, ...indicatorCodes], ALL);
  const years = [...new Set(loaded.flatMap((s) => s.observations.map((o) => o.periodStart.slice(0, 4))))].sort();
  const [from, setFrom] = useUrlFilter<string>('from', [ALL, ...years], ALL);
  const [to, setTo] = useUrlFilter<string>('to', [ALL, ...years], ALL);
  const [tabParam, setTab] = useUrlFilter<Tab>('tab', TABS, 'data');
  const tab: Tab = wide && tabParam === 'assistant' ? 'data' : tabParam;
  const { reset, active, count } = useResetFilters(FILTER_PARAMS);
  const to_ = usePreservedSearch();

  // The analysed series: the chosen indicator (or the first) in the chosen area (national first).
  const candidates = inArea.filter((s) => indicator === ALL || s.indicatorCode === indicator);
  const focus = candidates.find((s) => (s.area?.code ?? 'OM') === 'OM') ?? candidates[0] ?? null;
  const trend = focus ? seriesDataset(focus, from === ALL ? null : from, to === ALL ? null : to) : null;

  // A new study (a question asked here or in the panel) brings the Study tab forward.
  const lastStudy = useRef(ui.activeStudy?.id ?? null);
  useEffect(() => {
    const id = ui.activeStudy?.id ?? null;
    if (id && id !== lastStudy.current) setTab('study');
    lastStudy.current = id;
  }, [ui.activeStudy?.id, setTab]);

  // "Analyse" on a resource card: its domain, section and headline indicator, in one change.
  const analyseResource = (code: SectionCode, indicatorCode: string | null) => {
    const owner = DOMAINS.find((d) => d.sections.includes(code));
    update((p) => {
      if (owner) p.set('domain', owner.code);
      p.set('section', code);
      if (indicatorCode) p.set('indicator', indicatorCode);
      else p.delete('indicator');
      p.delete('tab');
    }, { replace: true });
  };
  const openStudy = (id: string) => {
    ui.openStudy(id, ui.studies.find((s) => s.id === id)?.guest ?? true);
    setTab('study');
  };

  const tabs = [
    { id: 'data' as const, label: t('workspace.tabs.data') },
    { id: 'study' as const, label: t('workspace.tabs.study'), badge: ui.activeStudy ? '1' : null },
    ...(wide ? [] : [{ id: 'assistant' as const, label: t('workspace.tabs.assistant') }]),
  ];
  const nameOf = (code: string) => inArea.find((s) => s.indicatorCode === code)?.name[language] ?? code;
  const yearOptions = [{ value: ALL, label: t('analysis.allYears') }, ...years.map((y) => ({ value: y, label: y }))];

  const findings = (
    <Panel id="ws-selection" title={t('workspace.findings.heading')} icon={<Sparkles aria-hidden="true" className="size-4 text-primary" />}
      testId="workspace-findings">
      <p className="text-xs text-muted-foreground">{t('workspace.findings.note')}</p>
      <SelectionStudy indicator={focus?.indicatorCode ?? null} area={focus?.area?.code ?? 'OM'} periodKind={focus?.frequency ?? 'annual'}
        mode={mode} section={focusSection} />
    </Panel>
  );

  return (
    <div data-testid="workspace" className="flex flex-col gap-5">
      <PageHeader title={t('workspace.title')} intro={t('workspace.intro')} />

      <ResourceKpis focus={focusSection} onAnalyse={analyseResource} />

      <FilterBar onReset={reset} canReset={active} activeCount={count} className="mb-0">
        <SelectField label={t('filters.domain')} value={domain}
          onValueChange={(v) => setDomain(DOMAIN_OPTIONS.find((o) => o === v) ?? ALL)}
          options={[{ value: ALL, label: t('filters.all') }, ...DOMAINS.map((d) => ({ value: d.code, label: t(DOMAIN_TEXT[d.code].title) }))]}
          data-testid="filter-domain" />
        <SelectField label={t('workspace.filters.section')} value={section} onValueChange={setSection}
          options={[{ value: ALL, label: t('workspace.filters.firstSection') }, ...sectionOptions.map((s) => ({ value: s, label: t(SECTION_TITLE[s]) }))]}
          data-testid="filter-section" />
        <SelectField label={t('filters.indicator')} value={indicator} onValueChange={setIndicator}
          options={[{ value: ALL, label: t('workspace.filters.firstIndicator') }, ...indicatorCodes.map((c) => ({ value: c, label: nameOf(c) }))]}
          data-testid="filter-indicator" />
        <SelectField label={t('filters.area')} value={area} onValueChange={setArea}
          options={[{ value: ALL, label: t('filters.allAreas') }, { value: 'OM', label: t('filters.national') },
            ...governorates.map((g) => ({ value: g.code, label: language === 'ar' ? g.name_ar : g.name_en }))]}
          data-testid="filter-area" />
        <SelectField label={t('filters.frequency')} value={frequency} onValueChange={setFrequency}
          options={[{ value: ALL, label: t('filters.all') }, ...FREQUENCIES.map((f) => ({ value: f, label: t(FREQUENCY_KEY[f]) }))]}
          data-testid="filter-frequency" />
        <SelectField label={t('analysis.periodFrom')} value={from} onValueChange={setFrom} options={yearOptions} data-testid="filter-from" />
        <SelectField label={t('analysis.periodTo')} value={to} onValueChange={setTo} options={yearOptions} data-testid="filter-to" />
        <Segmented label={t('dataMode.label')} value={mode} onChange={(v) => { const m = DATA_MODES.find((x) => x === v); if (m) setMode(m); }}
          options={DATA_MODES.map((m) => ({ value: m, label: t(`workspace.filters.mode.${m}`) }))} testId="workspace-data-mode" />
      </FilterBar>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,22rem)] lg:items-start">
        <div className="flex min-w-0 flex-col gap-4">
          <Tabs tabs={tabs} value={tab} onChange={setTab} idBase="workspace" label={t('workspace.tabs.label')} className="w-full sm:w-fit" />

          <div {...tabPanelProps('workspace', 'data', tab === 'data')} className="flex flex-col gap-5 outline-none" data-testid="workspace-data">
            <Panel id="ws-trend" title={t('workspace.trend.heading')} icon={<BarChart3 aria-hidden="true" className="size-4 text-primary" />}
              action={focus ? <span className="text-xs text-muted-foreground">{focus.name[language]} · {focus.unit.label[language]}</span> : null}>
              <p className="max-w-3xl text-xs text-muted-foreground">{t('workspace.trend.note')}</p>
              {series.isPending ? <StatePanel kind="loading" skeleton="lines" />
                : trend ? <DatasetView dataset={trend} state="reference" />
                  : focus ? <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('workspace.trend.noneInPeriod')}</p></StatePanel>
                    : <p className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs text-muted-foreground">{t('workspace.selection.choose')}</p>}
            </Panel>
            {wide ? null : findings}
            <Panel id="ws-cards" title={t(SECTION_TITLE[focusSection])}
              action={<Link to={to_(SECTION_PATHS[focusSection])} className="inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline">
                {t('pages.overview.open')}<span className="sr-only">: {t(SECTION_TITLE[focusSection])}</span>
                <ArrowRight aria-hidden="true" className="size-3.5 rtl:-scale-x-100" />
              </Link>}>
              <IndicatorCards query={series} shown={inArea} focus={focus}
                onAnalyse={(code) => setIndicator(code)} onChooseFrequency={setFrequency} />
            </Panel>
          </div>

          <div {...tabPanelProps('workspace', 'study', tab === 'study')} className="flex flex-col gap-5 outline-none" data-testid="workspace-study">
            <Panel id="ws-live" title={t('workspace.study.liveHeading')}>
              <LiveStudyPanel onAskFollowUp={wide ? undefined : () => setTab('assistant')} />
            </Panel>
          </div>

          {!wide ? (
            <div {...tabPanelProps('workspace', 'assistant', tab === 'assistant')} className="flex flex-col overflow-hidden rounded-lg border border-border bg-card outline-none">
              {tab === 'assistant' || ui.studies.length > 0 ? <AssistantColumn /> : null}
            </div>
          ) : null}
        </div>

        {wide ? (
          <div className="flex min-w-0 flex-col gap-5">
            {findings}
            <aside aria-label={t('workspace.assistant.label')}
              className="sticky top-[4.5rem] flex max-h-[calc(100dvh-5.5rem)] flex-col overflow-hidden rounded-lg border border-border bg-card">
              <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
                <AssistantColumn />
              </div>
            </aside>
          </div>
        ) : null}
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <GeographyView indicator={focus?.indicatorCode ?? null} frequency={focus?.frequency ?? 'annual'} />
        <RecentStudies onOpen={openStudy} />
        <SourcesPanel series={inArea} />
      </div>

      <WorkspaceLaunchpad />
    </div>
  );
}

function IndicatorCards({ query, shown, focus, onAnalyse, onChooseFrequency }: {
  query: ReturnType<typeof useSectionSeries>;
  shown: readonly Series[];
  focus: Series | null;
  onAnalyse: (code: string) => void;
  onChooseFrequency: (frequency: string) => void;
}) {
  const { t } = useTranslation();
  if (query.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (query.isError) {
    const err = query.error;
    const mixed = mixedFrequencies(err);
    // The choice stays in the workspace (the frequency filter above).
    if (mixed) return <MixedFrequencyNotice frequencies={mixed} onChoose={onChooseFrequency} />;
    if (err instanceof DataAdapterError && err.code === 'not_implemented') return <StatePanel kind="not_implemented" detail={err.message} />;
    return <StatePanel kind="error" detail={err.message} onRetry={() => void query.refetch()} />;
  }
  if (query.data.status === 'no_published_data') return <StatePanel kind="no_verified_data" />;
  if (!shown.length) return <StatePanel kind="empty" />;
  const stale = shown.filter((s) => isStale(s));
  return (
    <div className="@container flex flex-col gap-3">
      {stale.length ? (
        <p className="flex items-start gap-2 rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-xs" role="status" data-testid="workspace-stale">
          <Clock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />{t('workspace.stale.banner', { count: stale.length })}
        </p>
      ) : null}
      <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
        {shown.map((s) => (
          <IndicatorCard key={seriesKey(s)} series={s} headingLevel={3} stale={isStale(s)}
            selected={focus !== null && seriesKey(focus) === seriesKey(s)} onAnalyse={() => onAnalyse(s.indicatorCode)} />
        ))}
      </div>
    </div>
  );
}

/** Governorates side by side, only where the coverage supports a valid comparison. */
function GeographyView({ indicator, frequency }: { indicator: string | null; frequency: string }) {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const comparison = useAreaComparison(mode, indicator, null, null, frequency);
  const dataset = comparisonDataset(comparison.data, mode);
  return (
    <DashboardCard title={t('workspace.comparison.heading')} labelledBy="ws-geo" testId="workspace-geography"
      icon={<MapPinned aria-hidden="true" className="size-4 text-primary" />}>
      <p className="text-xs font-medium">{t('workspace.geography.heading')}</p>
      {adapterKind !== 'http' ? <StatePanel kind="not_implemented" />
        : !indicator ? null
          : comparison.isPending ? <StatePanel kind="loading" skeleton="lines" />
            : comparison.isError ? <StatePanel kind="error" detail={comparison.error.message} onRetry={() => void comparison.refetch()} />
              : dataset ? (
                <>
                  <p className="text-xs text-muted-foreground">{t('workspace.geography.note')}</p>
                  <DatasetView dataset={dataset} state="reference" />
                </>
              ) : (
                <div role="status" data-testid="workspace-geography-none" className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs">
                  <p className="font-medium">{t('workspace.geography.noneTitle')}</p>
                  <p className="text-muted-foreground">
                    {comparison.data?.status === 'not_comparable' ? t('workspace.geography.notComparable') : t('workspace.geography.none')}
                  </p>
                  <p className="mt-2 text-muted-foreground">{t('workspace.geography.noBoundaries')}</p>
                </div>
              )}
    </DashboardCard>
  );
}
