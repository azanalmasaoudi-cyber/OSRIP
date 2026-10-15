import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { PreviewBadge } from './PreviewLabel';
import type { Dataset } from '@/api/studyEvents';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { StudyTable } from '@/components/studies/StudyView';
import { formatCompact, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * One validated dataset drawn as an interactive chart and as an accessible, sortable table
 * from exactly the same rows. Numbers are parsed for geometry only; every printed value is
 * formatted from the original decimal string. The time axis mirrors in Arabic.
 */

type Row = Record<string, string | null>;

function toNumber(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function niceScale(values: number[]) {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const rough = (max - min || 1) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step || step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { lo, hi, ticks };
}

export function DashboardChart({ dataset, preview }: { dataset: Dataset; preview: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const rows = dataset.table.rows as Row[];
  const columns = dataset.table.columns.filter((c) => !c.key.endsWith('_ar'));
  const rowIds = dataset.rows_meta.map((m) => m.row_id);
  const chart = dataset.charts[0];
  const column = chart?.series[0]?.column;
  const unit = chart?.unit ? (language === 'ar' ? chart.unit.label_ar : chart.unit.label_en) : '';
  const title = dataset.title[language];
  const labelOf = (row: Row) => (chart && language === 'ar' && row[`${chart.x}_ar`]) || (chart ? row[chart.x] : null) || '';

  return (
    <section aria-label={title} data-testid="dataset" data-dataset={dataset.dataset_id} data-state="reference"
      className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 shadow-card sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-pretty font-semibold">{title}</h3>
          {dataset.subtitle ? <p className="text-sm text-muted-foreground">{dataset.subtitle[language]}{unit ? ` · ${unit}` : ''}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <DataStatusBadge status={dataset.data_status} />
          {preview ? <PreviewBadge /> : null}
        </div>
      </header>
      {chart && column ? (
        chart.type === 'bar'
          ? <RankedBars rows={rows} column={column} labelOf={labelOf} unit={unit} />
          : <TrendLine rows={rows} column={column} labelOf={labelOf} unit={unit} title={title} />
      ) : null}
      {chart ? <p className="text-xs text-muted-foreground">{t('dashboard.chart.hint')}</p> : null}
      <details className="group rounded-md border border-border" open>
        <summary className="flex min-h-10 cursor-pointer items-center px-3 text-sm font-medium marker:text-muted-foreground">
          {t('dashboard.chart.table')}
        </summary>
        <div className="border-t border-border p-3">
          <StudyTable columns={columns} rows={rows} language={language} rowIds={rowIds} caption={title} filterAlways={rows.length > 6} />
        </div>
      </details>
    </section>
  );
}

function TrendLine({ rows, column, labelOf, unit, title }: {
  rows: Row[]; column: string; labelOf: (row: Row) => string; unit: string; title: string;
}) {
  const language = useAppLanguage();
  const rtl = language === 'ar';
  const gradient = useId();
  const [active, setActive] = useState<number | null>(null);
  const W = 640;
  const H = 240;
  const pad = { side: 56, end: 20, top: 20, bottom: 32 };
  const plotW = W - pad.side - pad.end;
  const plotH = H - pad.top - pad.bottom;
  const values = rows.map((r) => toNumber(r[column]));
  const { lo, hi, ticks } = niceScale(values.filter((v): v is number => v !== null));
  const n = rows.length;
  const xAt = (i: number) => {
    const offset = n === 1 ? plotW / 2 : (i / (n - 1)) * plotW;
    return rtl ? W - pad.side - offset : pad.side + offset;
  };
  const yAt = (v: number) => pad.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const points = values.flatMap((v, i) => (v === null ? [] : [{ i, x: xAt(i), y: yAt(v) }]));
  let line = '';
  values.forEach((v, i) => {
    if (v === null) return;
    line += `${i === 0 || values[i - 1] === null ? 'M' : 'L'}${xAt(i)},${yAt(v)} `;
  });
  const first = points[0];
  const last = points.at(-1);
  const contiguous = values.every((v) => v !== null);
  const area = contiguous && first && last ? `${line}L${last.x},${yAt(lo)} L${first.x},${yAt(lo)} Z` : '';
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  const activePoint = points.find((p) => p.i === active);
  const activeRow = active !== null ? rows[active] : undefined;

  return (
    <figure className="m-0" data-testid="dashboard-line-chart">
      <figcaption className="sr-only">{title}</figcaption>
      <div className="relative" onMouseLeave={() => setActive(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label={title} className="h-auto w-full overflow-visible">
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={pad.side} x2={W - pad.end} y1={yAt(tick)} y2={yAt(tick)} stroke="var(--chart-grid)" strokeDasharray={tick === lo ? undefined : '3 4'}
                transform={rtl ? `translate(${pad.end - pad.side} 0)` : undefined} />
              <text x={rtl ? W - pad.side + 8 : pad.side - 8} y={yAt(tick)} dy="0.32em" textAnchor={rtl ? 'start' : 'end'}
                className="fill-muted-foreground text-[11px] tabular-nums">{formatCompact(tick, language)}</text>
            </g>
          ))}
          {area ? <path d={area} fill={`url(#${gradient})`} /> : null}
          <path d={line} fill="none" stroke="var(--chart-1)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          {rows.map((r, i) => (i % labelEvery === 0 || i === n - 1 ? (
            <text key={i} x={xAt(i)} y={H - 10} textAnchor="middle" className="fill-muted-foreground text-[11px]">{labelOf(r)}</text>
          ) : null))}
          {activePoint ? <line x1={activePoint.x} x2={activePoint.x} y1={pad.top} y2={yAt(lo)} stroke="var(--copper)" strokeDasharray="3 3" /> : null}
          {rows.map((_, i) => (
            <rect key={`hit-${i}`} aria-hidden="true" x={xAt(i) - plotW / Math.max(1, n - 1) / 2} y={pad.top} width={plotW / Math.max(1, n - 1)} height={plotH}
              fill="transparent" onMouseEnter={() => setActive(i)} />
          ))}
          {points.map((p) => {
            const row = rows[p.i];
            const value = row ? formatDecimal(row[column] ?? null, language) : null;
            return (
              <circle key={p.i} data-point={p.i} cx={p.x} cy={p.y} r={active === p.i ? 6 : 4} tabIndex={0}
                role="img" aria-label={`${row ? labelOf(row) : ''}: ${value ?? ''} ${unit}`}
                fill="var(--card)" stroke={active === p.i ? 'var(--copper)' : 'var(--chart-1)'} strokeWidth="2.5"
                className="cursor-pointer outline-none transition-[r] duration-150 focus-visible:stroke-[var(--ring)] motion-reduce:transition-none"
                onMouseEnter={() => setActive(p.i)} onFocus={() => setActive(p.i)} onBlur={() => setActive(null)} />
            );
          })}
        </svg>
        {activePoint && activeRow ? (
          <div aria-hidden="true" className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+12px)] whitespace-nowrap rounded-md bg-nav px-3 py-2 text-xs text-nav-foreground shadow-raised"
            style={{ left: `${(activePoint.x / W) * 100}%`, top: `${(activePoint.y / H) * 100}%` }}>
            <p className="text-nav-muted">{labelOf(activeRow)}</p>
            <p className="text-sm font-semibold tabular-nums" dir="ltr">{formatDecimal(activeRow[column] ?? null, language)} <span className="font-normal text-nav-muted">{unit}</span></p>
          </div>
        ) : null}
      </div>
    </figure>
  );
}

function RankedBars({ rows, column, labelOf, unit }: { rows: Row[]; column: string; labelOf: (row: Row) => string; unit: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [active, setActive] = useState<number | null>(null);
  const ranked = rows.map((row, i) => ({ row, i, v: toNumber(row[column]) })).sort((a, b) => (b.v ?? -Infinity) - (a.v ?? -Infinity));
  const max = Math.max(0, ...ranked.map((r) => r.v ?? 0)) || 1;
  return (
    <ol className="flex flex-col gap-1" data-testid="dashboard-bar-chart" onMouseLeave={() => setActive(null)}>
      {ranked.map(({ row, i, v }) => (
        <li key={i} data-point={i} onMouseEnter={() => setActive(i)}
          className={cn('grid grid-cols-[minmax(6rem,9rem)_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-1.5 text-sm transition-colors',
            active === i && 'bg-muted')}>
          <span className="truncate">{labelOf(row)}</span>
          <span aria-hidden="true" className="h-2.5 overflow-hidden rounded-full bg-muted">
            <span className={cn('block h-full rounded-full transition-[width,background-color] duration-300 motion-reduce:transition-none', active === i ? 'bg-copper' : 'bg-primary')}
              style={{ width: `${((v ?? 0) / max) * 100}%` }} />
          </span>
          <span className="text-end tabular-nums font-medium" dir="ltr">
            {v === null ? <span className="italic text-muted-foreground">{t('states.missingValue')}</span> : `${formatDecimal(row[column] ?? null, language)} ${unit}`}
          </span>
        </li>
      ))}
    </ol>
  );
}
