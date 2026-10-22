import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useTimeline, VIEWS, type SeriesView, type Timeline, type TimelineQuery } from '@/api/series';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import type { DataMode, SectionCode } from '@/domain/types';
import { formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

import { periodLabel } from './SeriesParts';

/** Headline indicators per sector, in order of preference (only those published are shown). */
export const HEADLINES: Record<SectionCode, readonly string[]> = {
  electricity: ['ELEC_CONSUMPTION', 'ELEC_GROSS_GENERATION', 'ELEC_INSTALLED_CAPACITY', 'ELEC_GENERATION', 'ELEC_PEAK_DEMAND'],
  water: ['WATER_PRODUCTION', 'WATER_CONSUMPTION', 'WATER_DISTRIBUTION'],
  food_security: ['AGRI_CROP_PRODUCTION', 'FISH_CAPTURE_LANDINGS', 'FOOD_PRODUCTION', 'AGRI_CULTIVATED_AREA'],
  trade: ['TRADE_MERCH_EXPORTS', 'TRADE_MERCH_IMPORTS', 'TRADE_NON_OIL_EXPORTS', 'TRADE_VALUE'],
};

export function headlineCodes(section: SectionCode, available: readonly string[], limit = 4): string[] {
  const preferred = HEADLINES[section].filter((c) => available.includes(c));
  return [...new Set([...preferred, ...available])].slice(0, limit);
}

export interface SeriesSelection {
  indicator: string;
  setIndicator: (v: string) => void;
  view: SeriesView;
  setView: (v: SeriesView) => void;
  from: string;
  setFrom: (v: string) => void;
  to: string;
  setTo: (v: string) => void;
  query: TimelineQuery | null;
}

function monthEnd(value: string): string {
  const [y, m] = value.split('-').map(Number);
  const last = new Date(Date.UTC(y ?? 2000, m ?? 1, 0)).getUTCDate();
  return `${value}-${String(last).padStart(2, '0')}`;
}

/** One chosen series (indicator, view and period range) for the trend chart and the table. */
export function useSeriesSelection(mode: DataMode, codes: readonly string[]): SeriesSelection {
  const [picked, setIndicator] = useState('');
  const indicator = codes.includes(picked) ? picked : (codes[0] ?? '');
  const [view, setView] = useState<SeriesView>('annual');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const query: TimelineQuery | null = indicator
    ? { dataMode: mode, indicator, view, area: 'OM', periodFrom: from ? `${from}-01` : null, periodTo: to ? monthEnd(to) : null, includeForecast: true }
    : null;
  return { indicator, setIndicator, view, setView, from, setFrom, to, setTo, query };
}

export function SeriesControls({ selection, codes, nameOf, timeline }: {
  selection: SeriesSelection;
  codes: readonly string[];
  nameOf: (code: string) => string;
  timeline: Timeline | undefined;
}) {
  const { t } = useTranslation();
  const available = timeline?.available_views ?? [...VIEWS];
  return (
    <div className="flex flex-wrap items-end gap-3" data-testid="series-controls">
      <SelectField label={t('series.indicator')} value={selection.indicator} onValueChange={selection.setIndicator}
        options={codes.map((c) => ({ value: c, label: nameOf(c) }))} data-testid="series-indicator" />
      <Segmented label={t('series.view')} value={selection.view} onChange={(v) => selection.setView((VIEWS as readonly string[]).includes(v) ? v : 'annual')}
        options={VIEWS.map((v) => ({ value: v, label: t(`series.views.${v}`), note: available.includes(v) ? undefined : t('series.viewUnavailable') }))} testId="series-view" />
      <label className="flex flex-col gap-1 text-xs font-medium">
        {t('series.from')}
        <input type="month" value={selection.from} onChange={(e) => selection.setFrom(e.target.value)} data-testid="series-from"
          className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        {t('series.to')}
        <input type="month" value={selection.to} onChange={(e) => selection.setTo(e.target.value)} data-testid="series-to"
          className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
      </label>
    </div>
  );
}

/** What a timeline request returned, or why there is nothing to draw. */
export function TimelineState({ query, children }: { query: ReturnType<typeof useTimeline>; children: (timeline: Timeline) => ReactNode }) {
  const { t } = useTranslation();
  if (query.isPending) return <p className="text-sm text-muted-foreground" role="status">{t('states.loading')}</p>;
  if (query.isError) return <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />;
  const data = query.data;
  if (data.status === 'needs_selection') return <p className="text-sm" data-testid="series-needs-selection">{t('series.needsSelection')}</p>;
  if (data.status !== 'ok' || !data.rows.length) return <p className="text-sm text-muted-foreground" data-testid="series-empty">{t('series.noData')}</p>;
  return <>{children(data)}</>;
}

function KpiCard({ mode, code }: { mode: DataMode; code: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const q = useTimeline({ dataMode: mode, indicator: code, view: 'annual', area: 'OM' });
  const data = q.data;
  if (!data || data.status !== 'ok') return null;
  const latest = [...data.rows].reverse().find((r) => r.value !== null);
  if (!latest) return null;
  const yoy = latest.changes.find((c) => c.basis === 'year_on_year');
  const ytd = [...data.year_to_date].reverse().find((r) => r.value !== null);
  const unit = data.unit?.label[language] ?? '';
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4" data-testid="kpi-card" data-indicator={code}>
      <p className="text-xs font-medium text-muted-foreground">{data.indicator.name[language]}</p>
      <p className="text-2xl font-semibold tabular-nums" dir="ltr">
        {latest.value_operator ?? ''}{formatDecimal(latest.value, language, 1)} <span className="text-sm font-normal">{unit}</span>
      </p>
      <p className="flex flex-wrap items-center gap-1.5 text-xs">
        <span>{periodLabel(latest.period_start, 'annual', language)}</span>
        <Badge variant={latest.nature === 'observed' ? 'verified' : 'sand'}>{t(`series.nature.${latest.nature}`)}</Badge>
        {yoy?.percent ? (
          <span className="tabular-nums" dir="ltr" data-testid="kpi-change">{Number(yoy.percent) > 0 ? '+' : ''}{formatDecimal(yoy.percent, language, 1)}% {t('series.yoyShort')}</span>
        ) : null}
      </p>
      {ytd ? <p className="text-xs text-muted-foreground">{t('series.ytdLatest', { value: formatDecimal(ytd.value, language, 1) ?? '', unit, end: ytd.period_end.slice(0, 7) })}</p> : null}
    </li>
  );
}

export function KeyIndicators({ mode, codes }: { mode: DataMode; codes: readonly string[] }) {
  const { t } = useTranslation();
  if (!codes.length) return <p className="text-sm text-muted-foreground">{t('series.noData')}</p>;
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="key-indicators">
      {codes.map((c) => <KpiCard key={c} mode={mode} code={c} />)}
    </ul>
  );
}
