import { BarChart3, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { DataModeBadge } from './DataModeBadge';
import { SourceDetailsButton } from './SourceDetails';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { latestObservation } from '@/domain/filters';
import type { Series } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useCodeLabels } from '@/lib/useLabels';

/**
 * Stat tile: the latest value of one series with its unit and period, plus the
 * previous period's value for context. It shows no computed change: derived
 * figures come from the backend calculation layer, not the UI.
 */
export function IndicatorCard({ series, headingLevel = 3, stale = false, selected = false, onAnalyse }: {
  series: Series;
  headingLevel?: 3 | 4 | 5;
  /** The latest period ended longer ago than the usual publication interval. */
  stale?: boolean;
  /** This card's series is the one analysed below (workspace). */
  selected?: boolean;
  onAnalyse?: () => void;
}) {
  const Heading = `h${headingLevel}` as const;
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  const { latest, previous } = latestObservation(series);
  const unit = series.unit.label[language];
  const latestValue = latest ? formatDecimal(latest.value, language) : null;
  const context = [series.flow ? t(FLOW_KEY[series.flow]) : null, series.commodityCode ? labels.commodity(series.commodityCode) : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <Card className={cn('flex flex-col gap-3 p-5', selected && 'ring-2 ring-primary')} data-testid="indicator-card" data-indicator={series.indicatorCode}
      data-stale={stale ? 'true' : undefined} data-selected={selected ? 'true' : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Heading className="text-sm font-semibold leading-snug">{series.name[language]}</Heading>
          {context ? <p className="text-xs text-muted-foreground">{context}</p> : null}
          {series.area ? <p className="text-xs text-muted-foreground">{series.area.name[language]}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <DataModeBadge mode={series.dataMode} />
          {stale ? <Badge variant="sand" data-testid="indicator-stale"><Clock aria-hidden="true" />{t('workspace.stale.badge')}</Badge> : null}
        </div>
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{t('indicator.latest')}</p>
        <p className="flex flex-wrap items-baseline gap-x-2">
          {latestValue ? (
            <span className="text-3xl font-semibold" dir="ltr" data-testid="indicator-value">
              {latestValue}
            </span>
          ) : (
            <span className="text-xl italic text-muted-foreground" data-missing="true">
              {t('states.missingValue')}
            </span>
          )}
          <span className="text-sm text-muted-foreground">{unit}</span>
        </p>
        {latest ? <p className="text-sm">{formatPeriod(latest.periodStart, latest.periodEnd, language)}</p> : null}
      </div>
      <p className="border-t border-border pt-3 text-xs text-muted-foreground">
        {previous ? (
          <>
            {t('indicator.previous')} ({formatPeriod(previous.periodStart, previous.periodEnd, language)}):{' '}
            <span className="font-medium text-foreground" dir="ltr">
              {formatDecimal(previous.value, language) ?? t('states.missingValue')}
            </span>
          </>
        ) : (
          t('indicator.noPrevious')
        )}
      </p>
      <div className="mt-auto flex flex-wrap items-center gap-2">
        <SourceDetailsButton series={series} />
        {onAnalyse ? (
          <Button type="button" variant={selected ? 'default' : 'outline'} size="sm" onClick={onAnalyse} aria-pressed={selected}
            data-testid="indicator-analyse">
            <BarChart3 aria-hidden="true" />{selected ? t('workspace.cards.analysed') : t('workspace.cards.analyse')}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}
