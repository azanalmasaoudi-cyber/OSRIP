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
      {chart.series.map((s) => {
        const style = NATURE_STYLE[s.nature];
        return (
          <li key={s.column} className="inline-flex items-center gap-1.5" data-nature={s.nature}>
            <svg width="22" height="8" aria-hidden="true">
              <line x1="1" y1="4" x2="21" y2="4" stroke={style.stroke} strokeWidth="2.5" strokeDasharray={style.dash} strokeLinecap="round" />
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
        {chart.series.map((s) => {
          const style = NATURE_STYLE[s.nature];
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
                    <circle cx={xAt(i)} cy={yAt(v)} r={on ? 5.5 : 3.5} fill={on ? 'var(--copper)' : 'var(--card)'} stroke={style.stroke} strokeWidth="2" />
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
