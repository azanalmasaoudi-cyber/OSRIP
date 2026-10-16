import { BarChart3, Droplets, Ship, Wheat, Zap, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useSeries } from '@/api/queries';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Button } from '@/components/ui/button';
import { HEADLINE, latestOf, type SeriesQuery } from '@/domain/headline';
import type { ObservationRecord, SectionCode } from '@/domain/types';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { sourceTitle, useProvenance } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

const ICON: Record<SectionCode, LucideIcon> = { electricity: Zap, water: Droplets, food_security: Wheat, trade: Ship };
const TITLE = { electricity: 'nav.electricity', water: 'nav.water', food_security: 'nav.foodSecurity', trade: 'nav.trade' } as const;
const SPARK_POINTS = 8;

/**
 * The four resources at a glance: each card shows the latest published national value of its
 * headline indicator with unit, reference period, source and the previous period's value, and
 * a small chart of the recent published values (as published: no change is computed here;
 * derived figures come from the server). A resource without published data in the chosen mode
 * says so instead of showing a number.
 */
export function ResourceKpis({ focus, onAnalyse }: { focus: SectionCode; onAnalyse: (section: SectionCode, indicator: string | null) => void }) {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  // Full years and year-to-date totals, as on the home page (the same cached queries).
  const queries = {
    electricity: [useSeries('electricity', mode, 'annual'), useSeries('electricity', mode, 'year_to_date')],
    water: [useSeries('water', mode, 'annual'), useSeries('water', mode, 'year_to_date')],
    food_security: [useSeries('food_security', mode, 'annual'), useSeries('food_security', mode, 'year_to_date')],
    trade: [useSeries('trade', mode, 'annual'), useSeries('trade', mode, 'year_to_date')],
  } satisfies Record<SectionCode, SeriesQuery[]>;
  return (
    <section aria-labelledby="ws-kpis" className="@container flex flex-col gap-3" data-testid="resource-kpis">
      <h2 id="ws-kpis" className="sr-only">{t('workspace.kpis.heading')}</h2>
      <ul className="grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-4">
        {HEADLINE.map(({ section, indicators }) => (
          <li key={section} className="min-w-0">
            <ResourceKpi section={section} queries={queries[section]} indicators={indicators} selected={focus === section}
              onAnalyse={onAnalyse} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function ResourceKpi({ section, queries, indicators, selected, onAnalyse }: {
  section: SectionCode;
  queries: readonly SeriesQuery[];
  indicators: readonly string[];
  selected: boolean;
  onAnalyse: (section: SectionCode, indicator: string | null) => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const provenance = useProvenance();
  const Icon = ICON[section];
  const pending = queries.some((q) => q.isPending);
  const failed = !pending && queries.every((q) => q.isError);
  const found = pending ? null : latestOf(queries, indicators);
  const state = pending ? 'loading' : found ? 'ok' : failed ? 'error' : 'empty';
  const shown = found ? provenance.value(found.obs, language) : null;
  const history = found
    ? [...found.series.observations].sort((a, b) => a.periodEnd.localeCompare(b.periodEnd)).filter((o) => o.periodEnd <= found.obs.periodEnd)
    : [];
  const previous = history.length > 1 ? history[history.length - 2] : undefined;
  const ytd = found?.series.frequency === 'year_to_date';

  return (
    <article className={cn('flex h-full flex-col gap-2.5 rounded-lg border bg-card p-4 transition-colors',
      selected ? 'border-primary/60 ring-1 ring-primary/40' : 'border-border')}
      data-testid="resource-kpi" data-section={section} data-state={state} aria-labelledby={`kpi-${section}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          <div className="min-w-0">
            <h3 id={`kpi-${section}`} className="text-sm font-semibold leading-tight">{t(TITLE[section])}</h3>
            <p className="truncate text-xs text-muted-foreground" title={found?.series.name[language]}>
              {found ? found.series.name[language] : ' '}
            </p>
          </div>
        </div>
        <Button type="button" variant={selected ? 'default' : 'outline'} size="sm" className="h-7 shrink-0 px-2" aria-pressed={selected}
          onClick={() => onAnalyse(section, found?.series.indicatorCode ?? null)} data-testid={`kpi-analyse-${section}`}>
          <BarChart3 aria-hidden="true" />{t('workspace.kpis.analyse')}
          <span className="sr-only">: {t(TITLE[section])}</span>
        </Button>
      </div>

      {state === 'loading' ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <span className="sr-only">{t('states.loading')}</span>
          <div className="h-7 w-28 animate-pulse rounded bg-muted" />
          <div className="h-10 animate-pulse rounded bg-muted" />
        </div>
      ) : found && shown ? (
        <>
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="flex flex-wrap items-baseline gap-x-1.5">
                <span className="text-2xl font-semibold tabular-nums" dir="ltr" data-testid="kpi-value" aria-label={shown.spoken}>{shown.text}</span>
                <span className="text-xs text-muted-foreground">{found.series.unit.label[language]}</span>
              </p>
              <p className="text-xs" data-testid="kpi-period">
                {formatPeriod(found.obs.periodStart, found.obs.periodEnd, language)}
                {ytd ? ` · ${t('frequency.year_to_date')}` : found.obs.periodComplete ? '' : ` · ${t('table.incompletePeriod')}`}
              </p>
            </div>
            <Sparkline points={history.slice(-SPARK_POINTS)} />
          </div>
          <p className="text-xs text-muted-foreground">
            {previous
              ? t('workspace.kpis.previous', {
                  value: formatDecimal(previous.value, language) ?? t('states.missingValue'),
                  period: formatPeriod(previous.periodStart, previous.periodEnd, language),
                })
              : t('workspace.kpis.noPrevious')}
          </p>
          <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-2.5 text-xs">
            <p className="min-w-0 truncate text-muted-foreground" title={sourceTitle(found.series)}>
              <span className="font-medium text-foreground">{t('workspace.kpis.source')}:</span> <bdi>{sourceTitle(found.series)}</bdi>
            </p>
            <DataModeBadge mode={found.series.dataMode} compact />
          </div>
        </>
      ) : (
        <p role="status" className="flex-1 rounded-md border border-dashed border-border-strong/40 p-3 text-xs text-muted-foreground"
          data-state={state === 'error' ? 'error' : 'data-unavailable'}>
          {state === 'error' ? t('states.dataUnavailable') : t('workspace.kpis.unavailable')}
        </p>
      )}
    </article>
  );
}

/** The recent published values as small columns, oldest to newest; the latest is emphasised.
 * A missing value leaves a gap (never drawn as zero). Decorative for screen readers, which
 * get the same values from the card text and the section's table. */
function Sparkline({ points }: { points: readonly ObservationRecord[] }) {
  const values = points.map((p) => (p.value === null ? null : Number(p.value)));
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (finite.length < 2) return null;
  const max = Math.max(...finite, 0);
  const min = Math.min(...finite, 0);
  const span = max - min || 1;
  const bar = 6;
  const gap = 3;
  const height = 34;
  const width = values.length * bar + (values.length - 1) * gap;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true" className="shrink-0" data-testid="kpi-sparkline">
      {values.map((v, i) => {
        if (v === null || !Number.isFinite(v)) return null;
        const top = height - ((v - min) / span) * height;
        const zero = height - ((0 - min) / span) * height;
        const y = Math.min(top, zero);
        const h = Math.max(Math.abs(zero - top), 1.5);
        const last = i === values.length - 1;
        return (
          <rect key={i} x={i * (bar + gap)} y={y} width={bar} height={h} rx={2}
            className={last ? 'fill-chart-1' : 'fill-chart-1/40'} />
        );
      })}
    </svg>
  );
}
