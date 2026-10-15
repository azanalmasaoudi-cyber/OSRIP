import { ArrowRight, Clock, LineChart, MapPinned } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { DataAdapterError } from '@/api/adapter';
import { useBackendStatus } from '@/api/backendStatus';
import { adapterKind } from '@/api/config';
import { useAreaRegistry } from '@/api/geography';
import { useAreaComparison } from '@/api/library';
import { PREVIEW_GOVERNORATES, previewComparison } from '@/api/previewFixtures';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { FREQUENCIES, mixedFrequencies, MixedFrequencyNotice } from '@/components/common/MixedFrequency';
import { StatePanel } from '@/components/common/StatePanel';
import { DashboardChart } from '@/components/dashboard/DashboardChart';
import { DashboardFilters, FILTER_ICONS, FilterGroup } from '@/components/dashboard/DashboardFilters';
import { DashboardHero } from '@/components/dashboard/DashboardHero';
import { DOMAIN_TITLE, DomainOverview, SECTION_ICON, SECTION_TITLE } from '@/components/dashboard/DomainOverview';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { PreviewNotice } from '@/components/dashboard/PreviewLabel';
import { SourcesPanel } from '@/components/dashboard/SourcesPanel';
import { useDashboardSeries, type DashboardSeries } from '@/components/dashboard/useDashboardSeries';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { AssistantColumn } from '@/components/workspace/AssistantColumn';
import { comparisonDataset, isStale, seriesDataset } from '@/components/workspace/datasets';
import { LiveStudyPanel } from '@/components/workspace/LiveStudyPanel';
import { SelectionStudy } from '@/components/workspace/SelectionStudy';
import { Tabs, tabPanelProps } from '@/components/workspace/Tabs';
import { ALL, seriesKey } from '@/domain/filters';
import { DOMAINS, SECTION_PATHS } from '@/domain/sections';
import { DATA_MODES, type SectionCode, type Series } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useMediaQuery } from '@/lib/useMediaQuery';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';
import { useResetFilters, useUrlFilter } from '@/state/useUrlFilter';

const DOMAIN_OPTIONS = [ALL, ...DOMAINS.map((d) => d.code)] as const;
const FILTER_PARAMS = ['domain', 'section', 'indicator', 'area', 'frequency', 'from', 'to'] as const;
const TABS = ['data', 'study', 'assistant'] as const;
type Tab = (typeof TABS)[number];

/**
 * The analytical workspace (the dashboard): the three domains, filters for scope, period,
 * geography and data mode; indicator cards with units, dates and sources; the chosen
 * indicator's history as one validated dataset drawn as an interactive chart and table;
 * governorates side by side where coverage supports it; the sources on screen; and the study
 * panel. On very wide screens the assistant sits beside the analysis; otherwise it is a tab.
 * When the OSRIP API does not answer, labelled preview fixtures stand in for the data.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode, setMode] = useDataMode();
  const backend = useBackendStatus();
  const preview = backend === 'offline';
  const ui = useAssistantUi();
  const wide = useMediaQuery('(min-width: 1280px)');
  const [domain, setDomain] = useUrlFilter('domain', DOMAIN_OPTIONS, ALL);
  const visibleDomains = DOMAINS.filter((d) => domain === ALL || d.code === domain);
  const sectionOptions = visibleDomains.flatMap((d) => d.sections);
  const [section, setSection] = useUrlFilter<string>('section', [ALL, ...sectionOptions], ALL);
  const focusSection = (section === ALL ? sectionOptions[0] : section) as SectionCode;
  // A section can mix annual, year-to-date and monthly series of one indicator: those are not
  // shown side by side, so the person chooses one frequency here (or from the notice).
  const [frequency, setFrequency] = useUrlFilter<string>('frequency', [ALL, ...FREQUENCIES], ALL);
  const freq = frequency === ALL ? undefined : frequency;
  const data = useDashboardSeries(focusSection, freq);
  const registry = useAreaRegistry();
  const governorates = preview
    ? PREVIEW_GOVERNORATES
    : (registry.data?.areas ?? []).filter((a) => a.level === 'governorate');
  const [area, setArea] = useUrlFilter<string>('area', [ALL, 'OM', ...governorates.map((g) => g.code)], ALL);
  const loaded: readonly Series[] = data.state === 'ready' && data.response.status === 'ok'
    ? data.response.series.filter((s) => s.partnerCode === null) : [];
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

  const tabs = [
    { id: 'data' as const, label: t('workspace.tabs.data') },
    { id: 'study' as const, label: t('workspace.tabs.study'), badge: ui.activeStudy ? '1' : null },
    ...(wide ? [] : [{ id: 'assistant' as const, label: t('workspace.tabs.assistant') }]),
  ];
  const nameOf = (code: string) => inArea.find((s) => s.indicatorCode === code)?.name[language] ?? code;
  const yearOptions = [{ value: ALL, label: t('analysis.allYears') }, ...years.map((y) => ({ value: y, label: y }))];
  const domainSections = DOMAINS.find((d) => d.sections.includes(focusSection))?.sections ?? [];

  return (
    <div data-testid="workspace" data-preview={preview ? 'true' : undefined} className="flex flex-col gap-6">
      <DashboardHero status={backend} />
      {preview ? <PreviewNotice /> : null}

      <DomainOverview domain={domain} onPick={setDomain} frequency={freq} />

      <DashboardFilters onReset={reset} canReset={active} activeCount={count}>
        <FilterGroup legend={t('dashboard.filters.scope')} icon={FILTER_ICONS.scope}>
          <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1 lg:grid-cols-3 2xl:grid-cols-1">
            <SelectField label={t('filters.domain')} value={domain}
              onValueChange={(v) => setDomain(DOMAIN_OPTIONS.find((o) => o === v) ?? ALL)}
              options={[{ value: ALL, label: t('filters.all') }, ...DOMAINS.map((d) => ({ value: d.code, label: t(DOMAIN_TITLE[d.code]) }))]}
              data-testid="filter-domain" />
            <SelectField label={t('workspace.filters.section')} value={section} onValueChange={setSection}
              options={[{ value: ALL, label: t('workspace.filters.firstSection') }, ...sectionOptions.map((s) => ({ value: s, label: t(SECTION_TITLE[s]) }))]}
              data-testid="filter-section" />
            <SelectField label={t('filters.indicator')} value={indicator} onValueChange={setIndicator}
              options={[{ value: ALL, label: t('workspace.filters.firstIndicator') }, ...indicatorCodes.map((c) => ({ value: c, label: nameOf(c) }))]}
              data-testid="filter-indicator" />
          </div>
        </FilterGroup>
        <FilterGroup legend={t('dashboard.filters.period')} icon={FILTER_ICONS.period}>
          <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1 lg:grid-cols-3 2xl:grid-cols-1">
            <SelectField label={t('filters.frequency')} value={frequency} onValueChange={setFrequency}
              options={[{ value: ALL, label: t('filters.all') }, ...FREQUENCIES.map((f) => ({ value: f, label: t(FREQUENCY_KEY[f]) }))]}
              data-testid="filter-frequency" />
            <SelectField label={t('analysis.periodFrom')} value={from} onValueChange={setFrom} options={yearOptions} data-testid="filter-from" />
            <SelectField label={t('analysis.periodTo')} value={to} onValueChange={setTo} options={yearOptions} data-testid="filter-to" />
          </div>
        </FilterGroup>
        <FilterGroup legend={t('dashboard.filters.geography')} icon={FILTER_ICONS.geography}>
          <SelectField label={t('filters.area')} value={area} onValueChange={setArea}
            options={[{ value: ALL, label: t('filters.allAreas') }, { value: 'OM', label: t('filters.national') },
              ...governorates.map((g) => ({ value: g.code, label: language === 'ar' ? g.name_ar : g.name_en }))]}
            data-testid="filter-area" />
        </FilterGroup>
        <FilterGroup legend={t('dashboard.filters.mode')} icon={FILTER_ICONS.mode}>
          <Segmented label={t('dataMode.label')} value={mode} onChange={(v) => { const m = DATA_MODES.find((x) => x === v); if (m) setMode(m); }}
            options={DATA_MODES.map((m) => ({ value: m, label: t(`workspace.filters.mode.${m}`) }))} testId="workspace-data-mode" />
          {preview ? <p className="text-xs text-synthetic-foreground">{t('dashboard.preview.modeLocked')}</p> : null}
        </FilterGroup>
      </DashboardFilters>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,23rem)] xl:items-start">
        <div className="flex min-w-0 flex-col gap-5">
          <Tabs tabs={tabs} value={tab} onChange={setTab} idBase="workspace" label={t('workspace.tabs.label')} className="w-full sm:w-fit" />

          <div {...tabPanelProps('workspace', 'data', tab === 'data')} className="flex flex-col gap-10 outline-none" data-testid="workspace-data">
            <section aria-labelledby="ws-cards" className="flex flex-col gap-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="flex flex-col gap-2">
                  <p className="text-xs font-semibold text-copper-foreground ltr:uppercase ltr:tracking-wider">{t('dashboard.kpi.heading')}</p>
                  <h2 id="ws-cards" className="text-xl font-semibold">{t(SECTION_TITLE[focusSection])}</h2>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {domainSections.length > 1 ? (
                    <div role="group" aria-label={t('workspace.filters.section')} className="flex rounded-md bg-muted p-1">
                      {domainSections.map((s) => {
                        const Icon = SECTION_ICON[s];
                        const on = s === focusSection;
                        return (
                          <button key={s} type="button" aria-pressed={on} onClick={() => setSection(s)} data-testid={`section-pick-${s}`}
                            className={cn('inline-flex min-h-9 items-center gap-1.5 rounded px-3 text-sm transition-colors',
                              on ? 'bg-card font-semibold text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground')}>
                            <Icon aria-hidden="true" className={cn('size-4', on && 'text-primary')} />{t(SECTION_TITLE[s])}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  <Link to={to_(SECTION_PATHS[focusSection])} className="inline-flex min-h-9 items-center gap-1 rounded-md px-2 text-sm font-medium text-primary underline-offset-4 hover:underline">
                    {t('pages.overview.open')}<span className="sr-only">: {t(SECTION_TITLE[focusSection])}</span>
                    <ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
                  </Link>
                </div>
              </div>
              <IndicatorCards data={data} shown={inArea} focus={focus}
                onAnalyse={(code) => setIndicator(code)} onChooseFrequency={setFrequency} />
            </section>

            <section aria-labelledby="ws-trend" className="flex flex-col gap-3">
              <h2 id="ws-trend" className="flex items-center gap-2 text-lg font-semibold"><LineChart aria-hidden="true" className="size-5 text-primary" />{t('workspace.trend.heading')}</h2>
              <p className="max-w-3xl text-sm text-muted-foreground">{t('workspace.trend.note')}</p>
              {data.state === 'loading' ? <StatePanel kind="loading" skeleton="lines" />
                : trend ? <DashboardChart dataset={trend} preview={data.state === 'ready' && data.preview} />
                  : focus ? <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('workspace.trend.noneInPeriod')}</p></StatePanel>
                    : null}
            </section>

            <GeographyView indicator={focus?.indicatorCode ?? null} frequency={focus?.frequency ?? 'annual'} preview={preview} />

            <SourcesPanel series={inArea} preview={preview} />
          </div>

          <div {...tabPanelProps('workspace', 'study', tab === 'study')} className="flex flex-col gap-6 outline-none" data-testid="workspace-study">
            <section aria-labelledby="ws-live" className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5">
              <h2 id="ws-live" className="text-lg font-semibold">{t('workspace.study.liveHeading')}</h2>
              <LiveStudyPanel onAskFollowUp={wide ? undefined : () => setTab('assistant')} />
            </section>
            <section aria-labelledby="ws-selection" className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5">
              <h2 id="ws-selection" className="text-lg font-semibold">{t('workspace.selection.heading')}</h2>
              <SelectionStudy indicator={focus?.indicatorCode ?? null} area={focus?.area?.code ?? 'OM'} periodKind={focus?.frequency ?? 'annual'}
                mode={mode} section={focusSection} />
            </section>
          </div>

          {!wide ? (
            <div {...tabPanelProps('workspace', 'assistant', tab === 'assistant')} className="flex flex-col rounded-lg border border-border bg-card shadow-card outline-none">
              {tab === 'assistant' || ui.studies.length > 0 ? <AssistantColumn figure={false} /> : null}
            </div>
          ) : null}
        </div>

        {wide ? (
          <aside aria-label={t('workspace.assistant.label')}
            className="sticky top-4 flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-card">
            <div aria-hidden="true" className="h-1 shrink-0 bg-gradient-to-r from-copper via-sand to-copper" />
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
              <AssistantColumn />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function IndicatorCards({ data, shown, focus, onAnalyse, onChooseFrequency }: {
  data: DashboardSeries;
  shown: readonly Series[];
  focus: Series | null;
  onAnalyse: (code: string) => void;
  onChooseFrequency: (frequency: string) => void;
}) {
  const { t } = useTranslation();
  if (data.state === 'loading') return <StatePanel kind="loading" skeleton="lines" />;
  if (data.state === 'error') {
    const err = data.error;
    const mixed = mixedFrequencies(err);
    // The choice stays in the workspace (the frequency filter above).
    if (mixed) return <MixedFrequencyNotice frequencies={mixed} onChoose={onChooseFrequency} />;
    if (err instanceof DataAdapterError && err.code === 'not_implemented') return <StatePanel kind="not_implemented" detail={err.message} />;
    return <StatePanel kind="error" detail={err.message} onRetry={data.retry} />;
  }
  if (data.response.status === 'no_published_data') return <StatePanel kind="no_verified_data" />;
  if (!shown.length) return <StatePanel kind="empty" />;
  // Preview fixtures use arbitrary placeholder years, so "out of date" would be meaningless.
  const staleOf = (s: Series) => !data.preview && isStale(s);
  const stale = shown.filter(staleOf);
  return (
    <div className="flex flex-col gap-3">
      {stale.length ? (
        <p className="flex items-start gap-2 rounded-md border border-sand/60 bg-sand-subtle/60 p-3 text-sm" role="status" data-testid="workspace-stale">
          <Clock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{t('workspace.stale.banner', { count: stale.length })}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
        {shown.map((s) => (
          <KpiCard key={seriesKey(s)} series={s} stale={staleOf(s)} preview={data.preview}
            selected={focus !== null && seriesKey(focus) === seriesKey(s)} onAnalyse={() => onAnalyse(s.indicatorCode)} />
        ))}
      </div>
    </div>
  );
}

/** Governorates side by side, only where the coverage supports a valid comparison. */
function GeographyView({ indicator, frequency, preview }: { indicator: string | null; frequency: string; preview: boolean }) {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const comparison = useAreaComparison(mode, indicator, null, null, frequency);
  const source = preview ? previewComparison(indicator) : comparison.data;
  const dataset = comparisonDataset(source, preview ? 'synthetic' : mode);
  return (
    <section aria-labelledby="ws-geo" className="flex flex-col gap-3" data-testid="workspace-geography">
      <h2 id="ws-geo" className="flex items-center gap-2 text-lg font-semibold"><MapPinned aria-hidden="true" className="size-5 text-primary" />{t('workspace.geography.heading')}</h2>
      {adapterKind !== 'http' ? <StatePanel kind="not_implemented" />
        : !indicator ? null
          : !preview && comparison.isPending ? <StatePanel kind="loading" skeleton="lines" />
            : !preview && comparison.isError ? <StatePanel kind="error" detail={comparison.error.message} onRetry={() => void comparison.refetch()} />
              : dataset ? (
                <>
                  <p className="max-w-3xl text-sm text-muted-foreground">{t('workspace.geography.note')}</p>
                  <DashboardChart dataset={dataset} preview={preview} />
                </>
              ) : (
                <div role="status" data-testid="workspace-geography-none" className="rounded-lg border border-dashed border-border-strong/50 bg-card/50 p-4 text-sm">
                  <p className="font-medium">{t('workspace.geography.noneTitle')}</p>
                  <p className="text-muted-foreground">
                    {source?.status === 'not_comparable' ? t('workspace.geography.notComparable') : t('workspace.geography.none')}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">{t('workspace.geography.noBoundaries')}</p>
                </div>
              )}
    </section>
  );
}
