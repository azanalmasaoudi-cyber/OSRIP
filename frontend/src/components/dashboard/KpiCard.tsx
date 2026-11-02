import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

/** A small line of the values over time (decorative; the card states the figures in words). */
export function Sparkline({ values, className }: { values: readonly number[]; className?: string }) {
  if (values.length < 2) return null;
  const w = 120;
  const h = 36;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - ((v - min) / span) * (h - 6)] as const);
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true" className={cn('h-9 w-full overflow-visible', className)} data-testid="sparkline">
      <defs>
        <linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#spark-fill)" />
      <polyline points={line} fill="none" stroke="var(--brand)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={points.at(-1)?.[0]} cy={points.at(-1)?.[1]} r="2.6" fill="var(--brand)" />
    </svg>
  );
}

export interface KpiChange {
  /** Percentage change against the previous comparable period (same months, one year earlier). */
  pct: number;
  /** "2024 → 2025" or "Jan–Jul 2025 → Jan–Jul 2026". */
  periods: string;
}

/**
 * One headline figure: title, value and unit, its period, the change against the previous
 * comparable period with its direction, a sparkline, and when the source was published or read.
 * With no published value it says "Data unavailable" and nothing else: no zero, no estimate.
 */
export function KpiCard({ title, value, unit, period, change, trend, freshness, footer, icon, testId = 'kpi-card', state, ...data }: {
  title: string;
  value: string | null;
  unit?: string;
  period?: string;
  change?: KpiChange | null;
  trend?: readonly number[];
  freshness?: string | null;
  footer?: ReactNode;
  icon?: ReactNode;
  testId?: string;
  state?: 'loading' | 'ready';
} & Record<`data-${string}`, string | undefined>) {
  const { t } = useTranslation();
  const direction = !change ? null : Math.abs(change.pct) < 0.05 ? 'flat' : change.pct > 0 ? 'up' : 'down';
  const Arrow = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : ArrowRight;
  return (
    <li className="kpi-card surface-card card-link flex min-w-0 flex-col gap-2 p-5" data-testid={testId} {...data}>
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-sm font-medium text-muted-foreground">{title}</p>
        {icon ? <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-brand">{icon}</span> : null}
      </div>
      {state === 'loading' ? <p className="text-base text-muted-foreground">{t('states.loading')}</p> : value === null ? (
        <p className="text-base font-medium text-muted-foreground" data-state="data-unavailable">{t('states.dataUnavailable')}</p>
      ) : (
        <>
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-3xl font-semibold tracking-tight tabular-nums" dir="ltr">{value}</span>
            {unit ? <span className="text-sm text-muted-foreground">{unit}</span> : null}
          </p>
          {period ? <p className="text-sm text-muted-foreground">{period}</p> : null}
          {change ? (
            // Neutral colour: a rise is not always good (imports, consumption), so no green or red.
            <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-foreground"
              data-testid="kpi-change" data-direction={direction ?? undefined}>
              <Arrow aria-hidden="true" className="size-4 shrink-0 rtl:-scale-x-100" />
              <span className="font-semibold tabular-nums" dir="ltr">{change.pct > 0 ? '+' : ''}{change.pct.toFixed(1)}%</span>
              <span className="text-muted-foreground">{change.periods}</span>
            </p>
          ) : null}
          {trend && trend.length > 1 ? <Sparkline values={trend} /> : null}
          {freshness ? <p className="text-xs text-muted-foreground" data-testid="kpi-freshness">{freshness}</p> : null}
          {footer}
        </>
      )}
    </li>
  );
}
