import type { ReactNode } from 'react';

import { mixedFrequencies, MixedFrequencyNotice, type Frequency } from './MixedFrequency';
import { SeriesCard } from './SeriesCard';
import { StatePanel } from './StatePanel';
import { DataAdapterError } from '@/api/adapter';
import { useSeries } from '@/api/queries';
import { filterSeries, seriesKey, type DisplayOption, type SeriesFilter } from '@/domain/filters';
import type { SectionCode, Series } from '@/domain/types';
import { useDataMode } from '@/state/useDataMode';

interface SectionSeriesProps {
  section: SectionCode;
  filter?: SeriesFilter;
  display?: DisplayOption;
  onResetFilters?: () => void;
  /** Extra content placed above the cards, given the filtered series (e.g. a partner comparison). */
  renderAbove?: (series: Series[]) => ReactNode;
  /** Selected frequency (undefined = all); the API refuses a mix, and the reader then picks one. */
  frequency?: string;
  onChooseFrequency?: (frequency: Frequency) => void;
}

/** Loads, filters and renders all series for one section in the current data mode. */
export function SectionSeries({ section, filter = {}, display = 'chart', onResetFilters, renderAbove, frequency, onChooseFrequency }: SectionSeriesProps) {
  const [mode] = useDataMode();
  const query = useSeries(section, mode, frequency);

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

  return (
    <div className="flex flex-col gap-6">
      {renderAbove?.(visible)}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-2">
        {visible.map((series) => (
          <SeriesCard key={seriesKey(series)} series={series} display={display} />
        ))}
      </div>
    </div>
  );
}
