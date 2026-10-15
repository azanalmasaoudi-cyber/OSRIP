import { BarChart3, Clock, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PreviewBadge } from './PreviewLabel';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { SourceDetailsButton } from '@/components/common/SourceDetails';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { latestObservation } from '@/domain/filters';
import type { Series } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { sourceTitle } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useCodeLabels } from '@/lib/useLabels';
import { cn } from '@/lib/utils';

/** Shape of the published values over time, decorative: the chart and table carry the values. */
function Sparkline({ series }: { series: Series }) {
  const rtl = useAppLanguage() === 'ar';
  const values = [...series.observations]
    .sort((a, b) => a.periodStart.localeCompare(b.periodStart))
    .map((o) => (o.value === null ? null : Number(o.value)))
    .filter((v): v is number => v !== null && Number.isFinite(v));
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const W = 120;
  const H = 32;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W;
    return `${rtl ? W - x : x},${H - 2 - ((v - min) / (max - min || 1)) * (H - 4)}`;
  });
  const last = points.at(-1)?.split(',') ?? ['0', '0'];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true" className="h-8 w-28 overflow-visible" preserveAspectRatio="none">
      <polyline points={points.join(' ')} fill="none" stroke="var(--chart-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="var(--copper)" />
    </svg>
  );
}

/**
 * The latest value of one series with unit, period, previous value and its source. It shows
 * no computed change: derived figures come from the backend calculation layer, not the UI.
 */
export function KpiCard({ series, stale, selected, preview, onAnalyse }: {
  series: Series;
  stale: boolean;
  selected: boolean;
  preview: boolean;
  onAnalyse: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  const { latest, previous } = latestObservation(series);
  const latestValue = latest ? formatDecimal(latest.value, language) : null;
  const context = [series.flow ? t(FLOW_KEY[series.flow]) : null, series.commodityCode ? labels.commodity(series.commodityCode) : null]
    .filter(Boolean).join(' · ');

  return (
    <article data-testid="indicator-card" data-indicator={series.indicatorCode} data-stale={stale ? 'true' : undefined}
      data-selected={selected ? 'true' : undefined}
      className={cn('relative flex flex-col gap-4 overflow-hidden rounded-lg border bg-card p-5 shadow-card transition-[border-color,box-shadow] duration-200',
        selected ? 'border-primary/50 ring-1 ring-primary/40' : 'border-border hover:shadow-raised')}>
      <div aria-hidden="true" className={cn('absolute inset-y-0 start-0 w-1', selected ? 'bg-primary' : 'bg-transparent')} />
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1">
          <DataModeBadge mode={series.dataMode} />
          {preview ? <PreviewBadge /> : null}
          {stale ? <Badge variant="sand" data-testid="indicator-stale"><Clock aria-hidden="true" />{t('workspace.stale.badge')}</Badge> : null}
        </div>
        <div className="min-w-0">
          <h3 className="text-pretty font-semibold leading-snug">{series.name[language]}</h3>
          {context || series.area ? (
            <p className="text-xs text-muted-foreground">{[context, series.area?.name[language]].filter(Boolean).join(' · ')}</p>
          ) : null}
        </div>
      </header>

      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-baseline gap-x-2">
            {latestValue ? (
              <span className="text-3xl font-semibold tabular-nums text-foreground" dir="ltr" data-testid="indicator-value">{latestValue}</span>
            ) : (
              <span className="text-xl italic text-muted-foreground" data-missing="true">{t('states.missingValue')}</span>
            )}
            <span className="text-sm text-muted-foreground">{series.unit.label[language]}</span>
          </p>
          {latest ? <p className="text-sm text-muted-foreground">{t('indicator.latest')} · {formatPeriod(latest.periodStart, latest.periodEnd, language)}</p> : null}
        </div>
        <Sparkline series={series} />
      </div>

      <p className="text-xs text-muted-foreground">
        {previous ? (
          <>
            {t('indicator.previous')} ({formatPeriod(previous.periodStart, previous.periodEnd, language)}):{' '}
            <span className="font-medium tabular-nums text-foreground" dir="ltr">{formatDecimal(previous.value, language) ?? t('states.missingValue')}</span>
          </>
        ) : t('indicator.noPrevious')}
      </p>

      <footer className="mt-auto flex flex-col gap-3 border-t border-border pt-3">
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground" data-testid="indicator-source">
          <FileText aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-copper-foreground" />
          <span><span className="font-medium text-foreground">{t('dashboard.sources.label')}:</span> {sourceTitle(series)}</span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <SourceDetailsButton series={series} />
          <Button type="button" variant={selected ? 'default' : 'outline'} size="sm" onClick={onAnalyse} aria-pressed={selected} data-testid="indicator-analyse">
            <BarChart3 aria-hidden="true" />{selected ? t('workspace.cards.analysed') : t('workspace.cards.analyse')}
          </Button>
        </div>
      </footer>
    </article>
  );
}
