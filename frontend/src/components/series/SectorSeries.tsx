import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { Timeline, useTimeline } from '@/api/series';
import { StatePanel } from '@/components/common/StatePanel';
import type { SectionCode } from '@/domain/types';

/** Headline indicators per sector, listed first in the sector's indicator choice. */
export const HEADLINES: Record<SectionCode, readonly string[]> = {
  electricity: ['ELEC_CONSUMPTION', 'ELEC_GROSS_GENERATION', 'ELEC_INSTALLED_CAPACITY', 'ELEC_GENERATION', 'ELEC_PEAK_DEMAND'],
  water: ['WATER_PRODUCTION', 'WATER_CONSUMPTION', 'WATER_DISTRIBUTION'],
  food_security: ['AGRI_CROP_PRODUCTION', 'FISH_CAPTURE_LANDINGS', 'FOOD_PRODUCTION', 'AGRI_CULTIVATED_AREA'],
  trade: ['TRADE_MERCH_EXPORTS', 'TRADE_MERCH_IMPORTS', 'TRADE_NON_OIL_EXPORTS', 'TRADE_VALUE'],
};

/** What a timeline request returned, or why there is nothing to draw. */
export function TimelineState({ query, children }: { query: ReturnType<typeof useTimeline>; children: (timeline: Timeline) => ReactNode }) {
  const { t } = useTranslation();
  if (query.isPending) return <p className="text-sm text-muted-foreground" role="status">{t('states.loading')}</p>;
  if (query.isError) return <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />;
  const data = query.data;
  if (data.status === 'needs_selection') return <p className="text-sm" data-testid="series-needs-selection">{t('series.needsSelection')}</p>;
  // A range can hold only year-to-date totals (a year not yet complete): those are shown.
  if (data.status !== 'ok' || (!data.rows.length && !data.year_to_date.length)) return <p className="text-sm text-muted-foreground" data-testid="series-empty">{t('series.noData')}</p>;
  return <>{children(data)}</>;
}
