import { useTranslation } from 'react-i18next';

import type { StudyChart } from '@/api/studies';
import { formatCompact, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * Charts for a study result, drawn from the same table rows the page shows. Numbers are
 * parsed here for geometry only; every printed value is formatted from the original decimal
 * string, and the table beside each chart carries the same values for assistive technology.
 * Observed, calculated, forecast and scenario series are told apart by line style and a
 * text legend, never by colour alone. The time axis mirrors with the text direction.
 */

type Row = Record<string, string | null>;
export type LabelFor = (row: Row, key: string) => string;

const NATURE_STYLE = {
  observed: { stroke: 'var(--chart-1)', dash: undefined },
  calculated: { stroke: 'var(--chart-2)', dash: undefined },
  forecast: { stroke: 'var(--chart-2)', dash: '6 4' },
  scenario: { stroke: 'var(--copper)', dash: '2 5' },
} as const;

type Marker = 'circle' | 'square' | 'diamond';
const MARKERS: readonly Marker[] = ['circle', 'square', 'diamond'];
const PALETTE = ['var(--chart-1)', 'var(--chart-2)', 'var(--copper)'] as const;

/** A series' line style: its nature (observed, calculated, forecast, scenario) decides the dash;
 * a second series of the same nature gets the next colour, and every series its own marker
 * shape, so lines are told apart without relying on colour alone. */
function seriesStyle(chart: StudyChart, index: number): { stroke: string; dash: string | undefined; marker: Marker } {
  const s = chart.series[index];
  const base = NATURE_STYLE[s?.nature ?? 'observed'];
  const sameBefore = chart.series.slice(0, index).filter((x) => x.nature === s?.nature).length;
  const start = Math.max(0, PALETTE.indexOf(base.stroke));
  const stroke = sameBefore === 0 ? base.stroke : (PALETTE[(start + sameBefore) % PALETTE.length] ?? base.stroke);
  return { stroke, dash: base.dash, marker: MARKERS[index % MARKERS.length] ?? 'circle' };
}

function Point({ x, y, r, marker, fill, stroke }: { x: number; y: number; r: number; marker: Marker; fill: string; stroke: string }) {
  if (marker === 'square') return <rect x={x - r} y={y - r} width={r * 2} height={r * 2} fill={fill} stroke={stroke} strokeWidth="2" />;
  if (marker === 'diamond') return <polygon points={`${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}`} fill={fill} stroke={stroke} strokeWidth="2" />;
  return <circle cx={x} cy={y} r={r} fill={fill} stroke={stroke} strokeWidth="2" />;
}

function toNumber(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** 0 or the data minimum (if negative) up to a rounded maximum, with about four steps. */
function scale(values: number[]): { lo: number; hi: number; ticks: number[] } {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;
  const rough = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step || step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { lo, hi, ticks };
}

function Legend({ chart }: { chart: StudyChart }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  if (chart.series.length < 2 && chart.series[0]?.nature === 'observed') return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {chart.series.map((s, i) => {
        const style = seriesStyle(chart, i);
        return (
          <li key={s.column} className="inline-flex items-center gap-1.5" data-nature={s.nature}>
            <svg width="26" height="12" aria-hidden="true">
              <line x1="1" y1="6" x2="25" y2="6" stroke={style.stroke} strokeWidth="2.5" strokeDasharray={style.dash} strokeLinecap="round" />
              {chart.type === 'line' ? <Point x={13} y={6} r={3} marker={style.marker} fill="var(--card)" stroke={style.stroke} /> : null}
            </svg>
            {s.label[language]} · {t(`studies.nature.${s.nature}`)}
          </li>
        );
      })}
    </ul>
  );
}

/** Row indexes to emphasise (the rows a spoken sentence is about); empty: none. */
type Highlight = ReadonlySet<number>;
const NONE: Highlight = new Set();

export function StudyLineChart({ chart, rows, labelFor, highlight = NONE }: { chart: StudyChart; rows: Row[]; labelFor: LabelFor; highlight?: Highlight }) {
  const language = useAppLanguage();
  const rtl = language === 'ar';
  const W = 640;
  const H = 240;
  const pad = { side: 52, end: 16, top: 16, bottom: 30 };
  const plotW = W - pad.side - pad.end;
  const plotH = H - pad.top - pad.bottom;
  const all = chart.series.flatMap((s) => rows.map((r) => toNumber(r[s.column]))).filter((v): v is number => v !== null);
  const { lo, hi, ticks } = scale(all);
  const n = rows.length;
  const xAt = (i: number) => {
    const offset = n === 1 ? plotW / 2 : (i / (n - 1)) * plotW;
    return rtl ? W - pad.side - offset : pad.side + offset;
  };
  const yAt = (v: number) => pad.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  const axisX = rtl ? W - pad.side + 6 : pad.side - 6;

  return (
    <figure className="m-0" data-testid="study-line-chart">
      <figcaption className="text-sm font-medium">{chart.title[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 h-auto w-full" aria-hidden="true">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={rtl ? pad.end : pad.side} x2={rtl ? W - pad.side : W - pad.end} y1={yAt(tick)} y2={yAt(tick)}
              stroke="var(--chart-grid)" strokeWidth={tick === 0 ? 1.5 : 1} />
            <text x={axisX} y={yAt(tick) + 4} fontSize="11" textAnchor={rtl ? 'start' : 'end'} fill="var(--muted-foreground)">
              {formatCompact(tick, language)}
            </text>
          </g>
        ))}
        {rows.map((r, i) => (i % labelEvery === 0 || i === n - 1 ? (
          <text key={i} x={xAt(i)} y={H - 8} fontSize="11" textAnchor="middle" fill="var(--muted-foreground)">{labelFor(r, chart.x)}</text>
        ) : null))}
        {chart.series.map((s, si) => {
          const style = seriesStyle(chart, si);
          // Missing values break the line: a gap is never bridged.
          const segments: string[] = [];
          let current = '';
          rows.forEach((r, i) => {
            const v = toNumber(r[s.column]);
            if (v === null) {
              if (current) segments.push(current);
              current = '';
              return;
            }
            current += `${current ? 'L' : 'M'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`;
          });
          if (current) segments.push(current);
          return (
            <g key={s.column} data-nature={s.nature}>
              {segments.map((d) => (
                <path key={d} d={d} fill="none" stroke={style.stroke} strokeWidth="2.5" strokeDasharray={style.dash} strokeLinejoin="round" strokeLinecap="round" />
              ))}
              {rows.map((r, i) => {
                const v = toNumber(r[s.column]);
                if (v === null) return null;
                const on = highlight.has(i);
                return (
                  <g key={i} data-point={i} data-highlighted={on ? 'true' : undefined}>
                    {on ? <circle cx={xAt(i)} cy={yAt(v)} r="10" fill="var(--copper)" opacity="0.25" /> : null}
                    <Point x={xAt(i)} y={yAt(v)} r={on ? 5.5 : 3.5} marker={style.marker} fill={on ? 'var(--copper)' : 'var(--card)'} stroke={style.stroke} />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <Legend chart={chart} />
    </figure>
  );
}

export function StudyBarChart({ chart, rows, labelFor, highlight = NONE }: { chart: StudyChart; rows: Row[]; labelFor: LabelFor; highlight?: Highlight }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const series = chart.series[0];
  if (!series) return null;
  const values = rows.map((r) => toNumber(r[series.column]));
  const max = Math.max(1e-9, ...values.map((v) => Math.abs(v ?? 0)));
  const style = NATURE_STYLE[series.nature];
  return (
    <figure className="m-0" data-testid="study-bar-chart">
      <figcaption className="mb-3 text-sm font-medium">{chart.title[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</figcaption>
      <ul className="flex flex-col gap-2" aria-hidden="true">
        {rows.map((r, i) => {
          const v = values[i] ?? null;
          const on = highlight.has(i);
          return (
            <li key={i} data-point={i} data-highlighted={on ? 'true' : undefined}
              className={cn('grid grid-cols-[minmax(5rem,10rem)_1fr_auto] items-center gap-3 rounded-sm text-sm', on && 'bg-copper-subtle/60 outline-2 outline-offset-2 outline-copper')}>
              <span className="truncate" dir="auto">{labelFor(r, chart.x)}</span>
              <span className="h-4 rounded-e-[3px] bg-chart-grid/50">
                {v !== null ? (
                  <span className="block h-full rounded-e-[3px]" style={{ width: `${(Math.abs(v) / max) * 100}%`, background: v < 0 ? 'var(--copper)' : style.stroke }} />
                ) : null}
              </span>
              <span className="min-w-14 text-end tabular-nums" dir="ltr">
                {v === null ? <span className="italic text-muted-foreground">{t('studies.missing')}</span> : formatDecimal(r[series.column] ?? null, language, 3)}
              </span>
            </li>
          );
        })}
      </ul>
      <Legend chart={chart} />
    </figure>
  );
}

export function StudyHeatmap({ chart, rows, labelFor }: { chart: StudyChart; rows: Row[]; labelFor: LabelFor }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const yKey = chart.y ?? '';
  const valueKey = chart.value ?? '';
  const xs: string[] = [];
  const ys: string[] = [];
  const cells = new Map<string, { raw: string | null; label: string }>();
  for (const r of rows) {
    const x = r[chart.x] ?? '';
    const y = r[yKey] ?? '';
    if (!xs.includes(x)) xs.push(x);
    if (!ys.includes(y)) ys.push(y);
    cells.set(`${y}|${x}`, { raw: r[valueKey] ?? null, label: labelFor(r, chart.x) });
  }
  const numbers = [...cells.values()].map((c) => toNumber(c.raw)).filter((v): v is number => v !== null);
  const lo = Math.min(...numbers);
  const hi = Math.max(...numbers);
  const xLabel = (x: string) => {
    const row = rows.find((r) => r[chart.x] === x);
    return row ? labelFor(row, chart.x) : x;
  };
  return (
    <figure className="m-0" data-testid="study-heatmap">
      <figcaption className="mb-3 text-sm font-medium">{chart.title[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</figcaption>
      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th scope="col" className="sr-only">{yKey}</th>
              {xs.map((x) => <th key={x} scope="col" className="px-1 font-medium text-muted-foreground">{xLabel(x)}</th>)}
            </tr>
          </thead>
          <tbody>
            {ys.map((y) => (
              <tr key={y}>
                <th scope="row" className="pe-2 text-start font-medium text-muted-foreground">{y}</th>
                {xs.map((x) => {
                  const cell = cells.get(`${y}|${x}`);
                  const v = toNumber(cell?.raw);
                  // Intensity stays light enough for dark text to remain readable.
                  const pct = v === null || hi === lo ? 30 : 10 + ((v - lo) / (hi - lo)) * 45;
                  return (
                    <td key={x} className={cn('min-w-12 rounded-sm px-1.5 py-2 text-center tabular-nums', v === null && 'border border-dashed border-border-strong/50 italic text-muted-foreground')}
                      style={v === null ? undefined : { background: `color-mix(in oklab, var(--chart-1) ${pct.toFixed(0)}%, transparent)` }}>
                      {cell === undefined ? '' : v === null ? t('studies.missing') : <span dir="ltr">{formatDecimal(cell.raw, language, 2)}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

/** Fills for pie slices: the three chart colours, then lighter mixes of them. Each slice is
 * also named in the legend with its value and share, so colour is never the only signal. */
const SLICE_FILLS = [100, 60, 32].flatMap((pct) =>
  PALETTE.map((c) => (pct === 100 ? c : `color-mix(in oklab, ${c} ${pct}%, var(--card))`)),
);

function arc(cx: number, cy: number, outer: number, inner: number, from: number, to: number): string {
  const point = (r: number, a: number) => `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;
  const large = to - from > Math.PI ? 1 : 0;
  return `M${point(outer, from)}A${outer},${outer} 0 ${large} 1 ${point(outer, to)}L${point(inner, to)}A${inner},${inner} 0 ${large} 0 ${point(inner, from)}Z`;
}

/** Shares of one series across categories (a ring). The server offers it only for values that
 * are all zero or positive and add up to a meaningful total; the share shown is the slice's
 * part of the values drawn, and every value is printed from its original decimal string. */
export function StudyPieChart({ chart, rows, labelFor }: { chart: StudyChart; rows: Row[]; labelFor: LabelFor }) {
  const language = useAppLanguage();
  const series = chart.series[0];
  if (!series) return null;
  const values = rows.map((r) => toNumber(r[series.column]));
  const total = values.reduce<number>((sum, v) => sum + (v !== null && v > 0 ? v : 0), 0);
  if (total <= 0) return null;
  const cx = 110;
  const cy = 110;
  let angle = -Math.PI / 2;
  const slices = [];
  for (const [i, r] of rows.entries()) {
    const v = values[i] ?? null;
    if (v === null || v <= 0) continue;
    const share = v / total;
    const from = angle;
    angle += share * Math.PI * 2;
    slices.push({ i, from, to: angle, share, fill: SLICE_FILLS[i % SLICE_FILLS.length] ?? 'var(--chart-1)', label: labelFor(r, chart.x), raw: r[series.column] ?? null });
  }
  return (
    <figure className="m-0" data-testid="study-pie-chart">
      <figcaption className="text-sm font-medium">{chart.title[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</figcaption>
      <div className="mt-2 flex flex-wrap items-center gap-6">
        <svg viewBox="0 0 220 220" className="h-auto w-48 shrink-0" aria-hidden="true">
          {slices.map((s) => (s.share > 0.9999
            ? <circle key={s.i} cx={cx} cy={cy} r={71} fill="none" stroke={s.fill} strokeWidth={38} />
            : <path key={s.i} d={arc(cx, cy, 90, 52, s.from, s.to)} fill={s.fill} stroke="var(--card)" strokeWidth="2" data-point={s.i} />))}
        </svg>
        <ul className="flex min-w-0 flex-col gap-1.5 text-sm">
          {slices.map((s) => (
            <li key={s.i} className="flex items-center gap-2" data-point={s.i}>
              <span aria-hidden="true" className="size-3 shrink-0 rounded-sm" style={{ background: s.fill }} />
              <span className="truncate" dir="auto">{s.label}</span>
              <span className="tabular-nums text-muted-foreground" dir="ltr">
                {formatDecimal(s.raw, language, 3)} · {formatDecimal(String(s.share * 100), language, 1)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  );
}

/** A rounded axis over the data's own range (not forced through zero), about four steps. */
function rangeScale(values: number[]): { lo: number; hi: number; ticks: number[] } {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.abs(max) || 1;
  const rough = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const lo = Math.floor(min / step) * step;
  const top = Math.ceil(max / step) * step;
  const hi = top === lo ? lo + step : top;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { lo, hi, ticks };
}

/** One measure against another, a point per row. Both axes are numbers and read from left to
 * right in both languages, as in a printed graph. */
export function StudyScatterChart({ chart, rows, xLabel }: { chart: StudyChart; rows: Row[]; xLabel: string }) {
  const language = useAppLanguage();
  const series = chart.series[0];
  if (!series) return null;
  const points = rows
    .map((r, i) => ({ i, x: toNumber(r[chart.x]), y: toNumber(r[series.column]) }))
    .filter((p): p is { i: number; x: number; y: number } => p.x !== null && p.y !== null);
  if (points.length === 0) return null;
  const W = 640;
  const H = 280;
  const pad = { left: 56, right: 16, top: 16, bottom: 40 };
  const xs = rangeScale(points.map((p) => p.x));
  const ys = rangeScale(points.map((p) => p.y));
  const xAt = (v: number) => pad.left + ((v - xs.lo) / (xs.hi - xs.lo || 1)) * (W - pad.left - pad.right);
  const yAt = (v: number) => pad.top + (H - pad.top - pad.bottom) * (1 - (v - ys.lo) / (ys.hi - ys.lo || 1));
  return (
    <figure className="m-0" data-testid="study-scatter-chart">
      <figcaption className="text-sm font-medium">{chart.title[language]}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 h-auto w-full" aria-hidden="true" direction="ltr">
        {ys.ticks.map((tick) => (
          <g key={`y${tick}`}>
            <line x1={pad.left} x2={W - pad.right} y1={yAt(tick)} y2={yAt(tick)} stroke="var(--chart-grid)" />
            <text x={pad.left - 6} y={yAt(tick) + 4} fontSize="11" textAnchor="end" fill="var(--muted-foreground)">{formatCompact(tick, language)}</text>
          </g>
        ))}
        {xs.ticks.map((tick) => (
          <text key={`x${tick}`} x={xAt(tick)} y={H - 22} fontSize="11" textAnchor="middle" fill="var(--muted-foreground)">{formatCompact(tick, language)}</text>
        ))}
        <text x={(pad.left + W - pad.right) / 2} y={H - 4} fontSize="11" textAnchor="middle" fill="var(--muted-foreground)">{xLabel}</text>
        {points.map((p) => (
          <circle key={p.i} cx={xAt(p.x)} cy={yAt(p.y)} r="4" fill="color-mix(in oklab, var(--chart-2) 55%, transparent)" stroke="var(--chart-2)" strokeWidth="1.5" data-point={p.i} />
        ))}
      </svg>
      <p className="mt-1 text-xs text-muted-foreground">{series.label[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</p>
    </figure>
  );
}

/** Vertical bars by period (or category), one bar per series side by side. The axis mirrors
 * with the text direction like the line chart, and a missing value leaves its place empty. */
export function StudyColumnChart({ chart, rows, labelFor }: { chart: StudyChart; rows: Row[]; labelFor: LabelFor }) {
  const language = useAppLanguage();
  const rtl = language === 'ar';
  const W = 640;
  const H = 240;
  const pad = { side: 52, end: 16, top: 16, bottom: 30 };
  const plotW = W - pad.side - pad.end;
  const plotH = H - pad.top - pad.bottom;
  const all = chart.series.flatMap((s) => rows.map((r) => toNumber(r[s.column]))).filter((v): v is number => v !== null);
  const { lo, hi, ticks } = scale(all);
  const n = Math.max(1, rows.length);
  const slot = plotW / n;
  const barW = Math.max(2, (slot * 0.72) / Math.max(1, chart.series.length));
  const xAt = (i: number, si: number) => {
    const offset = i * slot + slot * 0.14 + si * barW;
    return rtl ? W - pad.side - offset - barW : pad.side + offset;
  };
  const centre = (i: number) => (rtl ? W - pad.side - (i + 0.5) * slot : pad.side + (i + 0.5) * slot);
  const yAt = (v: number) => pad.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const labelEvery = Math.max(1, Math.ceil(n / 10));
  const axisX = rtl ? W - pad.side + 6 : pad.side - 6;
  return (
    <figure className="m-0" data-testid="study-column-chart">
      <figcaption className="text-sm font-medium">{chart.title[language]}{chart.unit ? ` (${chart.unit[language === 'ar' ? 'label_ar' : 'label_en']})` : ''}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 h-auto w-full" aria-hidden="true">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={rtl ? pad.end : pad.side} x2={rtl ? W - pad.side : W - pad.end} y1={yAt(tick)} y2={yAt(tick)}
              stroke="var(--chart-grid)" strokeWidth={tick === 0 ? 1.5 : 1} />
            <text x={axisX} y={yAt(tick) + 4} fontSize="11" textAnchor={rtl ? 'start' : 'end'} fill="var(--muted-foreground)">{formatCompact(tick, language)}</text>
          </g>
        ))}
        {rows.map((r, i) => (i % labelEvery === 0 || i === n - 1 ? (
          <text key={i} x={centre(i)} y={H - 8} fontSize="11" textAnchor="middle" fill="var(--muted-foreground)">{labelFor(r, chart.x)}</text>
        ) : null))}
        {chart.series.map((s, si) => {
          const style = seriesStyle(chart, si);
          return (
            <g key={s.column} data-nature={s.nature}>
              {rows.map((r, i) => {
                const v = toNumber(r[s.column]);
                if (v === null) return null;
                return (
                  <rect key={i} data-point={i} x={xAt(i, si)} y={Math.min(yAt(v), yAt(0))} width={barW}
                    height={Math.max(1, Math.abs(yAt(v) - yAt(0)))} fill={v < 0 ? 'var(--copper)' : style.stroke} rx="1.5" />
                );
              })}
            </g>
          );
        })}
      </svg>
      <Legend chart={chart} />
    </figure>
  );
}
