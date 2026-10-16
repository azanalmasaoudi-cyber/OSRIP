import { ArrowRight, BarChart3, Clock, MapPinned } from 'lucide-react';
import { useEffect, useRef } from 'react';
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
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { AssistantColumn } from '@/components/workspace/AssistantColumn';
import { comparisonDataset, isStale, seriesDataset } from '@/components/workspace/datasets';
import { DatasetView } from '@/components/workspace/DatasetView';
import { LiveStudyPanel } from '@/components/workspace/LiveStudyPanel';
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

/**
 * The analytical workspace (the dashboard): filters for domain, section, indicator, period,
 * geography and data mode; indicator cards with units, dates, sources and a stale-data flag;
 * the chosen indicator's history as one validated dataset drawn as chart and table;
 * governorates side by side only where the coverage supports it; and the study panel, with
 * the assistant's live study and the study of the current selection. On wide screens the
 * assistant sits beside the analysis; on phones Data, Study and Assistant are tabs.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode, setMode] = useDataMode();
  const ui = useAssistantUi();
  const wide = useMediaQuery('(min-width: 1024px)');
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

  const tabs = [
    { id: 'data' as const, label: t('workspace.tabs.data') },
    { id: 'study' as const, label: t('workspace.tabs.study'), badge: ui.activeStudy ? '1' : null },
    ...(wide ? [] : [{ id: 'assistant' as const, label: t('workspace.tabs.assistant') }]),
  ];
  const nameOf = (code: string) => inArea.find((s) => s.indicatorCode === code)?.name[language] ?? code;
  const yearOptions = [{ value: ALL, label: t('analysis.allYears') }, ...years.map((y) => ({ value: y, label: y }))];

  return (
    <div data-testid="workspace">
      <PageHeader title={t('workspace.title')} intro={t('workspace.intro')} />

      <WorkspaceLaunchpad />

      <FilterBar onReset={reset} canReset={active} activeCount={count}>
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

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] lg:items-start">
        <div className="flex min-w-0 flex-col gap-4">
          <Tabs tabs={tabs} value={tab} onChange={setTab} idBase="workspace" label={t('workspace.tabs.label')} className="w-full sm:w-fit" />

          <div {...tabPanelProps('workspace', 'data', tab === 'data')} className="flex flex-col gap-8 outline-none" data-testid="workspace-data">
            <DomainTiles domains={visibleDomains} onPick={(code) => setDomain(code)} frequency={freq} />
            <section aria-labelledby="ws-cards" className="flex flex-col gap-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="ws-cards" className="text-lg font-semibold">{t(SECTION_TITLE[focusSection])}</h2>
                <Link to={to_(SECTION_PATHS[focusSection])} className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
                  {t('pages.overview.open')}<span className="sr-only">: {t(SECTION_TITLE[focusSection])}</span>
                  <ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
                </Link>
              </div>
              <IndicatorCards query={series} shown={inArea} focus={focus}
                onAnalyse={(code) => setIndicator(code)} onChooseFrequency={setFrequency} />
            </section>
            <section aria-labelledby="ws-trend" className="flex flex-col gap-3">
              <h2 id="ws-trend" className="flex items-center gap-2 text-lg font-semibold"><BarChart3 aria-hidden="true" className="size-5 text-primary" />{t('workspace.trend.heading')}</h2>
              <p className="max-w-3xl text-sm text-muted-foreground">{t('workspace.trend.note')}</p>
              {series.isPending ? <StatePanel kind="loading" skeleton="lines" />
                : trend ? <DatasetView dataset={trend} state="reference" />
                  : focus ? <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('workspace.trend.noneInPeriod')}</p></StatePanel>
                    : null}
            </section>
            <GeographyView indicator={focus?.indicatorCode ?? null} frequency={focus?.frequency ?? 'annual'} />
          </div>

          <div {...tabPanelProps('workspace', 'study', tab === 'study')} className="flex flex-col gap-6 outline-none" data-testid="workspace-study">
            <section aria-labelledby="ws-live" className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:p-5">
              <h2 id="ws-live" className="text-lg font-semibold">{t('workspace.study.liveHeading')}</h2>
              <LiveStudyPanel onAskFollowUp={wide ? undefined : () => setTab('assistant')} />
            </section>
            <section aria-labelledby="ws-selection" className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:p-5">
              <h2 id="ws-selection" className="text-lg font-semibold">{t('workspace.selection.heading')}</h2>
              <SelectionStudy indicator={focus?.indicatorCode ?? null} area={focus?.area?.code ?? 'OM'} periodKind={focus?.frequency ?? 'annual'}
                mode={mode} section={focusSection} />
            </section>
          </div>

          {!wide ? (
            <div {...tabPanelProps('workspace', 'assistant', tab === 'assistant')} className="flex flex-col rounded-lg border border-border bg-card outline-none">
              {tab === 'assistant' || ui.studies.length > 0 ? <AssistantColumn figure={false} /> : null}
            </div>
          ) : null}
        </div>

        {wide ? (
          <aside aria-label={t('workspace.assistant.label')}
            className="sticky top-4 flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-card">
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
              <AssistantColumn />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function DomainTiles({ domains, onPick, frequency }: { domains: typeof DOMAINS; onPick: (code: DomainCode) => void; frequency?: string }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="ws-domains" className="flex flex-col gap-3">
      <h2 id="ws-domains" className="sr-only">{t('pages.overview.domainsHeading')}</h2>
      <ul className="grid gap-3 md:grid-cols-3">
        {domains.map((d) => (
          <li key={d.code}>
            <Card data-testid={`domain-card-${d.code}`} className="flex h-full flex-col gap-2 p-4">
              <p className="font-semibold">{t(DOMAIN_TEXT[d.code].title)}</p>
              <ul className="flex flex-col gap-0.5 text-sm text-muted-foreground">
                {d.sections.map((s) => <SectionCount key={s} section={s} frequency={frequency} />)}
              </ul>
              <button type="button" onClick={() => onPick(d.code)} className="mt-auto w-fit text-sm font-medium text-primary underline-offset-4 hover:underline"
                data-testid={`domain-pick-${d.code}`}>
                {t('workspace.domainFocus')}<span className="sr-only">: {t(DOMAIN_TEXT[d.code].title)}</span>
              </button>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SectionCount({ section, frequency }: { section: SectionCode; frequency?: string }) {
  const { t } = useTranslation();
  const query = useSectionSeries(section, frequency);
  // A mixed-frequency section has series but needs a frequency choice before they are listed.
  const label = query.isPending ? t('workspace.seriesShort', { n: '…' })
    : query.isError ? (mixedFrequencies(query.error) ? t('workspace.mixedShort') : '—')
      : t('workspace.seriesShort', { n: query.data.status !== 'ok' ? 0 : query.data.series.length });
  return (
    <li className="flex items-baseline justify-between gap-2">
      <span className="min-w-0 truncate">{t(SECTION_TITLE[section])}</span>
      <span className="shrink-0 whitespace-nowrap tabular-nums">{label}</span>
    </li>
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
    <div className="flex flex-col gap-3">
      {stale.length ? (
        <p className="flex items-start gap-2 rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-sm" role="status" data-testid="workspace-stale">
          <Clock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{t('workspace.stale.banner', { count: stale.length })}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
    <section aria-labelledby="ws-geo" className="flex flex-col gap-3" data-testid="workspace-geography">
      <h2 id="ws-geo" className="flex items-center gap-2 text-lg font-semibold"><MapPinned aria-hidden="true" className="size-5 text-primary" />{t('workspace.geography.heading')}</h2>
      {adapterKind !== 'http' ? <StatePanel kind="not_implemented" />
        : !indicator ? null
          : comparison.isPending ? <StatePanel kind="loading" skeleton="lines" />
            : comparison.isError ? <StatePanel kind="error" detail={comparison.error.message} onRetry={() => void comparison.refetch()} />
              : dataset ? (
                <>
                  <p className="max-w-3xl text-sm text-muted-foreground">{t('workspace.geography.note')}</p>
                  <DatasetView dataset={dataset} state="reference" />
                </>
              ) : (
                <div role="status" data-testid="workspace-geography-none" className="rounded-lg border border-dashed border-border-strong/50 p-4 text-sm">
                  <p className="font-medium">{t('workspace.geography.noneTitle')}</p>
                  <p className="text-muted-foreground">
                    {comparison.data?.status === 'not_comparable' ? t('workspace.geography.notComparable') : t('workspace.geography.none')}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">{t('workspace.geography.noBoundaries')}</p>
                </div>
              )}
    </section>
  );
}
