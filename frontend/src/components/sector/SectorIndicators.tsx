import { Clock } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { DataAdapterError } from '@/api/adapter';
import { useAreaRegistry } from '@/api/geography';
import { useSectionSeries, type SectionSeriesQuery } from '@/api/queries';
import { FilterBar } from '@/components/common/FilterBar';
import { IndicatorCard } from '@/components/common/IndicatorCard';
import { FREQUENCIES, mixedFrequencies, MixedFrequencyNotice } from '@/components/common/MixedFrequency';
import { StatePanel } from '@/components/common/StatePanel';
import { SelectField } from '@/components/ui/select';
import { SourcesPanel } from '@/components/workspace/DashboardPanels';
import { isStale } from '@/components/workspace/datasets';
import { ALL, byPeriodKind, seriesKey } from '@/domain/filters';
import type { SectionCode, Series } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';
import { useUrlFilter } from '@/state/useUrlFilter';

/**
 * The sector's "Data and indicators": every indicator published for it (in the chosen data mode),
 * each with its latest value, period, change, provenance and freshness, filtered by area and
 * frequency, and the sources behind them. "Analyse" on a card makes it the sector's current
 * selection and opens the Analysis (formerly the Analysis Workspace's indicator cards).
 */
export function SectorIndicators({ section, onAnalyse, children }: {
  section: SectionCode;
  /** The card's indicator, and its period kind when several kinds are listed. */
  onAnalyse: (code: string, kind: string | undefined) => void;
  /** Sector-specific registers (commodities for food security and trade). */
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const [frequency, setFrequency] = useUrlFilter<string>('frequency', [ALL, ...FREQUENCIES], ALL);
  const series = useSectionSeries(section, mode, frequency === ALL ? undefined : frequency);
  const registry = useAreaRegistry();
  const governorates = (registry.data?.areas ?? []).filter((a) => a.level === 'governorate');
  const [area, setArea] = useUrlFilter<string>('area', [ALL, 'OM', ...governorates.map((g) => g.code)], ALL);
  const loaded: readonly Series[] = series.data?.status === 'ok' ? series.data.series.filter((s) => s.partnerCode === null) : [];
  const shown = area === ALL ? loaded : loaded.filter((s) => (s.area?.code ?? 'OM') === area);
  return (
    <div className="flex flex-col gap-5" data-testid="sector-indicators">
      <FilterBar onReset={() => { setArea(ALL); setFrequency(ALL); }} canReset={area !== ALL || frequency !== ALL}
        activeCount={(area !== ALL ? 1 : 0) + (frequency !== ALL ? 1 : 0)} className="mb-0">
        <SelectField label={t('filters.area')} value={area} onValueChange={setArea}
          options={[{ value: ALL, label: t('filters.allAreas') }, { value: 'OM', label: t('filters.national') },
            ...governorates.map((g) => ({ value: g.code, label: language === 'ar' ? g.name_ar : g.name_en }))]}
          data-testid="filter-area" />
        <SelectField label={t('filters.frequency')} value={frequency} onValueChange={setFrequency}
          options={[{ value: ALL, label: t('filters.all') }, ...FREQUENCIES.map((f) => ({ value: f, label: t(FREQUENCY_KEY[f]) }))]}
          data-testid="filter-frequency" />
      </FilterBar>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(17rem,20rem)] xl:items-start">
        <section aria-labelledby={`${section}-indicators-h`} className="flex min-w-0 flex-col gap-3">
          <div>
            <h2 id={`${section}-indicators-h`} className="text-base font-semibold">{t('sector.data.heading')}</h2>
            <p className="text-sm text-muted-foreground">{t('sector.data.note')}</p>
          </div>
          <IndicatorCards query={series} shown={shown} onAnalyse={onAnalyse} onChooseFrequency={setFrequency} />
        </section>
        <div className="flex min-w-0 flex-col gap-5">
          <SourcesPanel series={shown} />
          {children}
        </div>
      </div>
    </div>
  );
}

function IndicatorCards({ query, shown, onAnalyse, onChooseFrequency }: {
  query: SectionSeriesQuery;
  shown: readonly Series[];
  onAnalyse: (code: string, kind: string | undefined) => void;
  onChooseFrequency: (frequency: string) => void;
}) {
  const { t } = useTranslation();
  if (query.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (query.isError) {
    const err = query.error;
    const mixed = mixedFrequencies(err);
    if (mixed) return <MixedFrequencyNotice frequencies={mixed} onChoose={onChooseFrequency} />;
    if (err instanceof DataAdapterError && err.code === 'not_implemented') return <StatePanel kind="not_implemented" detail={err.message} />;
    return <StatePanel kind="error" error={err} onRetry={() => void query.refetch()} />;
  }
  if (query.data.status === 'no_published_data') return <StatePanel kind="no_verified_data" />;
  if (!shown.length) return <StatePanel kind="empty" />;
  const stale = shown.filter((s) => isStale(s));
  // With "All", each period kind is its own group (a year-to-date total is not a full year).
  const groups = byPeriodKind(shown);
  const grouped = groups.length > 1;
  return (
    <div className="@container flex flex-col gap-3">
      {stale.length ? (
        <p className="flex items-start gap-2 rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-xs" role="status" data-testid="workspace-stale">
          <Clock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />{t('workspace.stale.banner', { count: stale.length })}
        </p>
      ) : null}
      {grouped ? <p className="text-xs text-muted-foreground" data-testid="period-kinds-note">{t('states.periodKindsApart')}</p> : null}
      {groups.map(({ kind, series }) => (
        <div key={kind ?? 'unstated'} className="flex flex-col gap-2" data-testid="period-kind-group" data-period-kind={kind}>
          {grouped && kind ? <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t(FREQUENCY_KEY[kind])}</h3> : null}
          <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
            {series.map((s) => (
              <IndicatorCard key={seriesKey(s)} series={s} headingLevel={grouped ? 4 : 3} stale={isStale(s)}
                selected={false} onAnalyse={() => onAnalyse(s.indicatorCode, s.frequency)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
