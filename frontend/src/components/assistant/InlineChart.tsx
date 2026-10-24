import { useTranslation } from 'react-i18next';

import type { Evidence } from '@/api/assistant';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

import { pick } from './Evidence';

/** The words that ask for a chart, in English and Arabic. */
const CHART_REQUEST = /\b(chart|graph|plot|visuali[sz]e|visuali[sz]ation)\b|رسم|مخطط|بياني|ارسم/i;

export function asksForChart(question: string | undefined): boolean {
  return Boolean(question && CHART_REQUEST.test(question));
}

/** The cited published observations that can share one chart: same indicator, area, unit and
 * kind of period, at least two periods with exact values, in time order. Null otherwise. */
export function chartPoints(evidence: Evidence[]): Evidence[] | null {
  const obs = evidence.filter((e) => e.kind === 'observation' && e.value != null && !e.value_operator && e.period_start);
  const first = obs[0];
  if (!first) return null;
  const same = obs.filter((e) => e.indicator === first.indicator && e.area === first.area && e.unit === first.unit
    && (e.period_kind ?? e.frequency) === (first.period_kind ?? first.frequency));
  const byPeriod = new Map(same.map((e) => [e.period_start ?? '', e]));
  const points = [...byPeriod.values()].sort((a, b) => (a.period_start ?? '').localeCompare(b.period_start ?? ''));
  return points.length >= 2 ? points : null;
}

/**
 * A chart the person asked for, inside the conversation: bars for the cited published values
 * (never estimated, never filled in), each labelled with its period and value, and the source
 * of every bar listed below by its evidence id.
 */
export function InlineChart({ points, messageId }: { points: Evidence[]; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const first = points[0]!;
  const values = points.map((p) => Number(p.value));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const width = 560;
  const height = 220;
  const pad = { top: 16, bottom: 40, side: 12 };
  const slot = (width - pad.side * 2) / points.length;
  const bar = Math.min(56, slot * 0.6);
  const y = (v: number) => pad.top + ((max - v) / span) * (height - pad.top - pad.bottom);
  const unit = pick(first.unit_label, language) || String(first.unit ?? '');
  const title = `${pick(first.indicator_name, language)} · ${pick(first.area_name, language)}`;
  const label = (p: Evidence) => formatPeriod(p.period_start ?? '', p.period_end ?? p.period_start ?? '', language);
  const summary = points.map((p) => `${label(p)}: ${formatDecimal(p.value ?? null, language, 3)} ${unit}`).join('; ');
  const sources = [...new Set(points.map((p) => p.source?.title).filter(Boolean))];
  return (
    <figure className="flex flex-col gap-1.5" data-testid="inline-chart" data-points={points.length} data-message={messageId}>
      <figcaption className="text-xs font-semibold" dir="auto">{title} <span className="font-normal text-muted-foreground">({unit})</span></figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full max-w-xl [direction:ltr]" role="img" aria-label={`${title}. ${summary}`}>
        <line x1={pad.side} x2={width - pad.side} y1={y(0)} y2={y(0)} className="stroke-border-strong" strokeWidth={1} />
        {points.map((p, i) => {
          const v = Number(p.value);
          const cx = pad.side + slot * i + slot / 2;
          const top = Math.min(y(v), y(0));
          const h = Math.max(1, Math.abs(y(v) - y(0)));
          return (
            <g key={p.period_start} data-point={p.id}>
              <rect x={cx - bar / 2} y={top} width={bar} height={h} rx={3} className="fill-primary/80" />
              <text x={cx} y={top - 4} textAnchor="middle" className="fill-foreground text-[11px] tabular-nums">
                {formatDecimal(p.value ?? null, language, 1)}
              </text>
              <text x={cx} y={height - pad.bottom + 16} textAnchor="middle" className="fill-muted-foreground text-[11px]">{label(p)}</text>
              <text x={cx} y={height - pad.bottom + 30} textAnchor="middle" className="fill-muted-foreground font-mono text-[10px]">[{p.id}]</text>
            </g>
          );
        })}
      </svg>
      <p className="text-xs text-muted-foreground" dir="auto" data-testid="inline-chart-sources">
        {t('chat.chartSources', { sources: sources.join(' · '), ids: points.map((p) => p.id).join(', ') })}
      </p>
    </figure>
  );
}
