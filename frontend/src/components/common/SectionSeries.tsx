import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { mixedFrequencies, MixedFrequencyNotice, type Frequency } from './MixedFrequency';
import { SeriesCard } from './SeriesCard';
import { StatePanel } from './StatePanel';
import { DataAdapterError } from '@/api/adapter';
import { useSectionSeries } from '@/api/queries';
import { byPeriodKind, filterSeries, seriesKey, type DisplayOption, type SeriesFilter } from '@/domain/filters';
import type { SectionCode, Series } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';
import { useDataMode } from '@/state/useDataMode';

interface SectionSeriesProps {
  section: SectionCode;
  filter?: SeriesFilter;
  display?: DisplayOption;
  onResetFilters?: () => void;
  /** Extra content placed above the cards, given the filtered series (e.g. a partner comparison). */
  renderAbove?: (series: Series[]) => ReactNode;
  /** Selected frequency (undefined = all, each period kind read and listed on its own). */
  frequency?: string;
  onChooseFrequency?: (frequency: Frequency) => void;
  /** Level of the period-kind headings when several kinds are listed. */
  headingLevel?: 3 | 4;
}

/** Loads, filters and renders all series for one section in the current data mode. */
export function SectionSeries({ section, filter = {}, display = 'chart', onResetFilters, renderAbove, frequency, onChooseFrequency, headingLevel = 3 }: SectionSeriesProps) {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const query = useSectionSeries(section, mode, frequency);
  const Heading = `h${headingLevel}` as const;

  if (query.isPending) return <StatePanel kind="loading" />;
  if (query.isError) {
    const err = query.error;
    const mixed = mixedFrequencies(err);
    if (mixed) return <MixedFrequencyNotice frequencies={mixed} onChoose={onChooseFrequency} />;
    if (err instanceof DataAdapterError && err.code === 'not_implemented') {
      return <StatePanel kind="not_implemented" detail={err.message} />;
    }
    return <StatePanel kind="error" detail={err.message} onRetry={() => void query.refetch()} />;
  }

  const data = query.data;
  if (data.status === 'no_published_data') return <StatePanel kind="no_verified_data" />;
  const visible = filterSeries(data.series, filter);
  if (visible.length === 0) return <StatePanel kind="empty" onReset={onResetFilters} />;

  const cards = (series: Series[]) => (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-2">
      {series.map((s) => (
        <SeriesCard key={seriesKey(s)} series={s} display={display} />
      ))}
    </div>
  );
  const groups = byPeriodKind(visible);
  if (groups.length === 1) {
    return (
      <div className="flex flex-col gap-6">
        {renderAbove?.(visible)}
        {cards(visible)}
      </div>
    );
  }
  // Several period kinds (the "All" frequency): each is its own group, never side by side.
  return (
    <div className="flex flex-col gap-8">
      <p className="max-w-3xl text-sm text-muted-foreground" data-testid="period-kinds-note">{t('states.periodKindsApart')}</p>
      {groups.map(({ kind, series }) => (
        <section key={kind ?? 'unstated'} aria-labelledby={kind ? `period-${section}-${kind}` : undefined} className="flex flex-col gap-4"
          data-testid="period-kind-group" data-period-kind={kind}>
          {kind ? <Heading id={`period-${section}-${kind}`} className="text-lg font-semibold">{t(FREQUENCY_KEY[kind])}</Heading> : null}
          {renderAbove?.(series)}
          {cards(series)}
        </section>
      ))}
    </div>
  );
}
