import { useId, useState, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { formatCompact, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

export interface TrendPoint {
  /** Period label shown on the axis and in the readout ("2025", "Jan–Jul 2026"). */
  label: string;
  value: number;
}

/**
 * A published series over time as an area chart: a baseline at zero when every value is positive
 * (no truncated axis), four gridlines, the latest point marked, and a readout of the point under
 * the pointer. The same figures are in the table under "Show the data".
 */
export function TrendChart({ points, unit, title }: { points: readonly TrendPoint[]; unit: string; title: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <p className="text-sm text-muted-foreground" data-testid="trend-too-short">{t('dashboard.trendTooShort')}</p>;

  const w = 720;
  const h = 260;
  const pad = { top: 16, right: 16, bottom: 30, left: 56 };
  const values = points.map((p) => p.value);
  const top = Math.max(...values);
  const bottom = Math.min(0, ...values);
  const span = top - bottom || 1;
  const x = (i: number) => pad.left + (i / (points.length - 1)) * (w - pad.left - pad.right);
  const y = (v: number) => pad.top + (1 - (v - bottom) / span) * (h - pad.top - pad.bottom);
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${x(0)},${y(bottom)} ${line} ${x(points.length - 1)},${y(bottom)}`;
  const ticks = [0, 1, 2, 3, 4].map((k) => bottom + (span * k) / 4);
  const every = Math.max(1, Math.ceil(points.length / 8));
  const shown = hover ?? points.length - 1;
  const current = points[shown];

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    const px = (rtl ? 1 - ratio : ratio) * w;
    const i = Math.round(((px - pad.left) / (w - pad.left - pad.right)) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, i)));
  };

  return (
    <figure className="flex flex-col gap-2" data-testid="trend-chart">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{title} <span className="text-muted-foreground">({unit})</span></span>
        {current ? (
          <span className="text-sm" aria-live="polite" data-testid="trend-readout">
            <span className="text-muted-foreground">{current.label}: </span>
            <span className="font-semibold tabular-nums" dir="ltr">{formatDecimal(String(current.value), language, 1)}</span>
          </span>
        ) : null}
      </figcaption>
      {/* Charts read left to right in both languages (time runs left to right). */}
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full touch-none [direction:ltr]" role="img"
        aria-label={t('dashboard.trendLabel', { title, from: points[0]?.label ?? '', to: points.at(-1)?.label ?? '' })}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={w - pad.right} y1={y(v)} y2={y(v)} stroke="var(--chart-grid)" strokeWidth="1" />
            <text x={pad.left - 8} y={y(v)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill="var(--muted-foreground)">
              {formatCompact(v, language)}
            </text>
          </g>
        ))}
        <polygon points={area} fill={`url(#${gradientId})`} />
        <polyline points={line} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (i % every === 0 || i === points.length - 1 ? (
          <text key={p.label} x={x(i)} y={h - 8} textAnchor="middle" fontSize="11" fill="var(--muted-foreground)">{p.label}</text>
        ) : null))}
        {current ? (
          <g>
            <line x1={x(shown)} x2={x(shown)} y1={pad.top} y2={y(bottom)} stroke="var(--border-strong)" strokeDasharray="3 3" />
            <circle cx={x(shown)} cy={y(current.value)} r="5" fill="var(--card)" stroke="var(--brand)" strokeWidth="2.5" />
          </g>
        ) : null}
      </svg>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">{t('dashboard.showData')}</summary>
        <table className="expand-content mt-2 w-full max-w-md text-sm">
          <thead><tr className="text-xs text-muted-foreground">
            <th scope="col" className="py-1 text-start font-medium">{t('dashboard.period')}</th>
            <th scope="col" className="py-1 text-end font-medium">{unit}</th>
          </tr></thead>
          <tbody>{points.map((p) => (
            <tr key={p.label} className="border-t border-border">
              <th scope="row" className="py-1 text-start font-normal">{p.label}</th>
              <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(String(p.value), language, 2)}</td>
            </tr>
          ))}</tbody>
        </table>
      </details>
    </figure>
  );
}
