import { FlaskConical, Scale } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { PartnerBars } from './Charts';
import { DataQualityNotes } from './DataQualityNotes';
import { FilterBar } from './FilterBar';
import { FREQUENCIES } from './MixedFrequency';
import { SectionSeries } from './SectionSeries';
import { StatePanel } from './StatePanel';
import type { SectionFilters } from '@/api/analysis';
import { adapterKind } from '@/api/config';
import { useAreaRegistry } from '@/api/geography';
import { useSectionSeries } from '@/api/queries';
import { useTimeline } from '@/api/series';
import { AnalysisPanel, ExportLinks } from '@/components/analysis/AnalysisPanel';
import { ReviewCards } from '@/components/analysis/ReviewCards';
import { SectionInsights } from '@/components/analysis/SectionInsights';
import { SaveReportButton } from '@/components/analysis/SaveReportButton';
import { headlineCodes, KeyIndicators, SeriesControls, TimelineState, useSeriesSelection } from '@/components/series/SectorSeries';
import { TimelineChart, TimelineRules, TimelineSources, TimelineTable } from '@/components/series/SeriesParts';
import { SelectField } from '@/components/ui/select';
import {
  ALL,
  comparablePartnerRows,
  DISPLAY_OPTIONS,
  distinct,
  NATIONAL_TOTAL,
  TRADE_FLOWS,
  type DisplayOption,
} from '@/domain/filters';
import type { Frequency, SectionCode, Series } from '@/domain/types';
import { FLOW_KEY, FREQUENCY_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useCodeLabels } from '@/lib/useLabels';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';
import { useResetFilters, useUrlFilter } from '@/state/useUrlFilter';

type FilterName = 'indicator' | 'flow' | 'partner' | 'commodity';

interface SectionViewProps {
  section: SectionCode;
  filters: readonly FilterName[];
  title: string;
  /** 2 on a page of its own, 3 inside the Energy layout. */
  headingLevel?: 2 | 3;
}

const ALL_PARAMS = ['frequency', 'area', 'indicator', 'flow', 'partner', 'commodity', 'view', 'from', 'to', 'stock'] as const;
const STOCK_OPTIONS = ['assumed_zero', 'unknown', 'known'] as const;

const PARTS = ['indicators', 'trends', 'table', 'analysis', 'recommendations', 'sources'] as const;

/**
 * One sector, in a fixed order: key indicators, historical trends, the detailed table, the
 * analysis, the recommendations and the sources. The trend chart and the detailed table are
 * drawn from the same chronological series (one request, one dataset id); the published
 * observations below the table keep every series and filter as before.
 * Filters, calculations, observations and review cards for one section.
 * One set of URL filters drives the tables, charts, calculations, exports and
 * saved reports, so they always describe the same selection; filter values are
 * codes, so they survive a language switch.
 */
export function SectionView({ section, filters, title, headingLevel = 2 }: SectionViewProps) {
  const Heading = `h${headingLevel}` as const;
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  const [mode] = useDataMode();
  const [frequency, setFrequency] = useUrlFilter<string>('frequency', [ALL, ...FREQUENCIES], ALL);
  const freq = frequency === ALL ? undefined : frequency;
  // "All" reads each period kind on its own (a mixed read is refused) and lists them apart.
  const query = useSectionSeries(section, mode, freq);
  const registry = useAreaRegistry();
  const governorates = (registry.data?.areas ?? []).filter((a) => a.level === 'governorate');
  const [area, setArea] = useUrlFilter<string>('area', [ALL, 'OM', ...governorates.map((g) => g.code)], ALL);
  const loaded: readonly Series[] = query.data?.status === 'ok' ? query.data.series : [];

  const indicatorCodes = distinct(loaded.map((s) => s.indicatorCode));
  const partnerCodes = distinct(loaded.map((s) => s.partnerCode));
  const commodityCodes = labels.commodities.map((c) => c.code);
  const years = [...new Set(loaded.flatMap((s) => s.observations.map((o) => o.periodStart.slice(0, 4))))].sort();

  const [indicator, setIndicator] = useUrlFilter('indicator', [ALL, ...indicatorCodes], ALL);
  const [flow, setFlow] = useUrlFilter<string>('flow', [ALL, ...TRADE_FLOWS], ALL);
  const [partner, setPartner] = useUrlFilter('partner', [ALL, NATIONAL_TOTAL, ...partnerCodes], ALL);
  const [commodity, setCommodity] = useUrlFilter('commodity', [ALL, ...commodityCodes], ALL);
  const [from, setFrom] = useUrlFilter('from', [ALL, ...years], ALL);
  const [to, setTo] = useUrlFilter('to', [ALL, ...years], ALL);
  const [stock, setStock] = useUrlFilter<string>('stock', STOCK_OPTIONS, 'assumed_zero');
  const [display, setDisplay] = useUrlFilter<DisplayOption>('view', DISPLAY_OPTIONS, 'chart');
  const { reset, active, count } = useResetFilters(ALL_PARAMS);

  const nameOf = (code: string) => loaded.find((s) => s.indicatorCode === code)?.name[language] ?? code;
  // Real partner countries carry registry names; fixture partners keep their fictional labels.
  const partnerName = (code: string | null) =>
    (code !== null ? loaded.find((s) => s.partnerCode === code)?.partnerName?.[language] : undefined) ?? labels.partner(code);
  const periodFrom = from === ALL ? undefined : `${from}-01-01`;
  const periodTo = to === ALL ? undefined : `${to}-12-31`;
  const shared: SectionFilters = {
    frequency: freq, area: area === ALL ? undefined : area, indicator, flow, partner, commodity, period_from: periodFrom, period_to: periodTo,
    stock_assumption: section === 'food_security' ? stock : undefined,
  };
  const areaName = area === ALL ? t('filters.allAreas') : area === 'OM' ? t('filters.national')
    : (governorates.find((g) => g.code === area)?.[language === 'ar' ? 'name_ar' : 'name_en'] ?? area);
  const summary = [
    areaName,
    frequency === ALL ? t('filters.allFrequencies') : t(FREQUENCY_KEY[frequency as Frequency]),
    indicator === ALL ? null : nameOf(indicator),
    flow === ALL || !filters.includes('flow') ? null : t(FLOW_KEY[flow as keyof typeof FLOW_KEY]),
    partner === ALL || !filters.includes('partner') ? null : partner === NATIONAL_TOTAL ? t('filters.nationalTotal') : partnerName(partner),
    commodity === ALL || !filters.includes('commodity') ? null : (labels.commodities.find((c) => c.code === commodity)?.name[language] ?? commodity),
    from === ALL && to === ALL ? t('analysis.allYears') : `${from === ALL ? '…' : from}–${to === ALL ? '…' : to}`,
  ].filter(Boolean).join(' · ');
  const inScope = indicator === ALL ? loaded : loaded.filter((s) => s.indicatorCode === indicator);
  const api = adapterKind === 'http';
  const link = usePreservedSearch();
  // National series without breakdown, headline indicators first (the chart, table and cards).
  const nationalCodes = distinct(loaded.filter((s) => (s.area?.code ?? 'OM') === 'OM' && !s.partnerCode && !s.commodityCode)
    .map((s) => s.indicatorCode));
  const seriesCodes = headlineCodes(section, nationalCodes, 12);
  const selection = useSeriesSelection(mode, seriesCodes);
  const timeline = useTimeline(api ? selection.query : null);
  const partHeading = (part: (typeof PARTS)[number]) => t(`sector.parts.${part}`);
  const yearOptions = [{ value: ALL, label: t('analysis.allYears') }, ...years.map((y) => ({ value: y, label: y }))];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <FilterBar onReset={reset} canReset={active} activeCount={count}>
          <SelectField label={t('filters.area')} value={area} onValueChange={setArea}
            options={[{ value: ALL, label: t('filters.allAreas') }, { value: 'OM', label: t('filters.national') },
              ...governorates.map((g) => ({ value: g.code, label: language === 'ar' ? g.name_ar : g.name_en }))]}
            data-testid="filter-area" />
          <SelectField label={t('filters.frequency')} value={frequency} onValueChange={setFrequency}
            options={[{ value: ALL, label: t('filters.all') }, ...FREQUENCIES.map((f) => ({ value: f, label: t(FREQUENCY_KEY[f]) }))]}
            data-testid="filter-frequency" />
          {filters.includes('indicator') ? (
            <SelectField label={t('filters.indicator')} value={indicator} onValueChange={setIndicator}
              options={[{ value: ALL, label: t('filters.all') }, ...indicatorCodes.map((c) => ({ value: c, label: nameOf(c) }))]}
              data-testid="filter-indicator" />
          ) : null}
          {filters.includes('commodity') ? (
            <SelectField label={t('filters.commodity')} value={commodity} onValueChange={setCommodity}
              options={[{ value: ALL, label: t('filters.all') },
                ...labels.commodities.map((c) => ({ value: c.code, label: c.name[language] }))]}
              data-testid="filter-commodity" />
          ) : null}
          {filters.includes('flow') ? (
            <SelectField label={t('filters.flow')} value={flow} onValueChange={setFlow}
              options={[{ value: ALL, label: t('filters.all') }, ...TRADE_FLOWS.map((f) => ({ value: f, label: t(FLOW_KEY[f]) }))]}
              data-testid="filter-flow" />
          ) : null}
          {filters.includes('partner') ? (
            <SelectField label={t('filters.partner')} value={partner} onValueChange={setPartner}
              options={[{ value: ALL, label: t('filters.all') }, { value: NATIONAL_TOTAL, label: t('filters.nationalTotal') },
                ...partnerCodes.map((c) => ({ value: c, label: partnerName(c) }))]}
              data-testid="filter-partner" />
          ) : null}
          <SelectField label={t('analysis.periodFrom')} value={from} onValueChange={setFrom} options={yearOptions}
            data-testid="filter-from" />
          <SelectField label={t('analysis.periodTo')} value={to} onValueChange={setTo} options={yearOptions}
            data-testid="filter-to" />
          {section === 'food_security' ? (
            <SelectField label={t('analysis.stockAssumption')} value={stock} onValueChange={setStock}
              options={STOCK_OPTIONS.map((s) => ({ value: s, label: t(`analysis.stock.${s}`) }))}
              data-testid="filter-stock" />
          ) : null}
          <SelectField label={t('filters.display')} value={display} onValueChange={(v) => setDisplay(v === 'table' ? 'table' : 'chart')}
            options={[{ value: 'chart', label: t('filters.displayChart') }, { value: 'table', label: t('filters.displayTable') }]}
            data-testid="filter-display" />
        </FilterBar>
        <p className="-mt-2 mb-3 text-sm" role="status" data-testid="filter-summary">
          <span className="font-semibold">{t('filters.showing')}:</span> {summary}
        </p>
        {adapterKind === 'http' ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-3xl text-xs text-muted-foreground">{t('analysis.filtersNote')} {t('filters.scopeNote')}</p>
            <SaveReportButton section={section} mode={mode} filters={shared} defaultTitle={title} />
          </div>
        ) : null}
      </div>

      <nav aria-label={t('sector.partsLabel')} className="-mt-4 flex flex-wrap gap-2 text-xs" data-testid="sector-parts">
        {PARTS.map((part, i) => (
          <a key={part} href={`#${section}-${part}`} className="rounded-full border border-border-strong/50 px-3 py-1 hover:bg-muted">
            {i + 1}. {partHeading(part)}
          </a>
        ))}
      </nav>

      <section id={`${section}-indicators`} aria-labelledby={`${section}-indicators-h`} className="flex scroll-mt-20 flex-col gap-3" data-testid="part-indicators">
        <Heading id={`${section}-indicators-h`} className="text-xl font-semibold">{partHeading('indicators')}</Heading>
        {api ? <KeyIndicators mode={mode} codes={seriesCodes.slice(0, 4)} />
          : <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>}
      </section>

      <section id={`${section}-trends`} aria-labelledby={`${section}-trends-h`} className="flex scroll-mt-20 flex-col gap-3" data-testid="part-trends">
        <Heading id={`${section}-trends-h`} className="text-xl font-semibold">{partHeading('trends')}</Heading>
        {api && seriesCodes.length ? (
          <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5">
            <SeriesControls selection={selection} codes={seriesCodes} nameOf={nameOf} timeline={timeline.data} />
            <TimelineState query={timeline}>{(data) => (
              <>
                <TimelineChart timeline={data} />
                <TimelineRules timeline={data} />
              </>
            )}</TimelineState>
          </div>
        ) : api ? <p className="text-sm text-muted-foreground">{t('series.noData')}</p> : null}
      </section>

      <section id={`${section}-table`} aria-labelledby={`${section}-table-h`} className="flex scroll-mt-20 flex-col gap-4" data-testid="part-table">
        <Heading id={`${section}-table-h`} className="text-xl font-semibold">{partHeading('table')}</Heading>
        {api && seriesCodes.length && selection.query ? (
          <TimelineState query={timeline}>{(data) => <TimelineTable timeline={data} query={selection.query!} />}</TimelineState>
        ) : null}
        <section aria-labelledby={`obs-${section}`} className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h4 id={`obs-${section}`} className="text-base font-semibold">{t('pages.reports.observations')}</h4>
            {api ? <ExportLinks section={section} mode={mode} filters={shared} only="observations" /> : null}
          </div>
          <SectionSeries
            section={section}
            filter={{ indicator, flow, partner, commodity, periodFrom, periodTo, area }}
            display={display}
            frequency={freq}
            onChooseFrequency={setFrequency}
            onResetFilters={reset}
            headingLevel={headingLevel === 2 ? 3 : 4}
            renderAbove={
              section === 'trade' && display === 'chart'
                ? (visible) => {
                    const rows = comparablePartnerRows(visible);
                    return rows ? (
                      <div className="rounded-lg border border-border bg-card p-5 shadow-card sm:p-6">
                        <PartnerBars rows={rows} labelFor={partnerName} />
                      </div>
                    ) : null;
                  }
                : undefined
            }
          />
        </section>
      </section>

      <section id={`${section}-analysis`} aria-labelledby={`${section}-analysis-h`} className="flex scroll-mt-20 flex-col gap-4" data-testid="part-analysis">
        <Heading id={`${section}-analysis-h`} className="text-xl font-semibold">{partHeading('analysis')}</Heading>
        {api && mode === 'verified_source' ? <DataQualityNotes section={section} /> : null}
        {api ? <SectionInsights section={section} mode={mode} filters={shared} series={inScope} /> : null}
        {api ? (
          <AnalysisPanel section={section} mode={mode} filters={shared} headingLevel={headingLevel} />
        ) : (
          <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>
        )}
      </section>

      <section id={`${section}-recommendations`} aria-labelledby={`${section}-recommendations-h`} className="flex scroll-mt-20 flex-col gap-4" data-testid="part-recommendations">
        <Heading id={`${section}-recommendations-h`} className="text-xl font-semibold">{partHeading('recommendations')}</Heading>
        {api ? (
          <div className="flex flex-wrap gap-2">
            <Link to={link('/assistant')} className="inline-flex items-center gap-1.5 rounded-md border border-border-strong/60 px-3 py-1.5 text-sm hover:bg-muted"
              data-testid="sector-balance-link">
              <Scale aria-hidden="true" className="size-4" />{t('sector.balanceLink')}
            </Link>
            <Link to={link(`/studies?create=${section}`)} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary-hover"
              data-testid="sector-create-study">
              <FlaskConical aria-hidden="true" className="size-4" />{t('jobs.create')}
            </Link>
          </div>
        ) : null}
        {api ? <ReviewCards mode={mode} section={section} headingLevel={headingLevel} /> : null}
      </section>

      <section id={`${section}-sources`} aria-labelledby={`${section}-sources-h`} className="flex scroll-mt-20 flex-col gap-3" data-testid="part-sources">
        <Heading id={`${section}-sources-h`} className="text-xl font-semibold">{partHeading('sources')}</Heading>
        {api && timeline.data?.status === 'ok' ? <TimelineSources timeline={timeline.data} /> : null}
        <p className="text-sm">
          <Link to={link('/sources')} className="text-primary underline underline-offset-2">{t('sector.allSources')}</Link>
        </p>
      </section>
    </div>
  );
}
