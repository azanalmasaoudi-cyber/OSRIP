import { Download, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { changesOf, timelineCsvUrl, type SeriesChange, type SeriesRow, type Timeline, type TimelineQuery } from '@/api/series';
import { Badge } from '@/components/ui/badge';
import { formatCompact, formatDecimal, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * The chart and the table of one chronological series, drawn from the same rows (the
 * server's validated dataset, identified by its dataset id). Rows are in time order; a
 * period without a published value stays empty in the table and breaks the line in the
 * chart, never zero. Published, provisional, estimated, derived and forecast values are
 * told apart by marker shape, line style and a text label, never by colour alone.
 */

const LOCALES: Record<AppLanguage, string> = { en: 'en-GB', ar: 'ar-OM-u-nu-latn' };

/** "2024", "Q1 2024" / "الربع 1 2024", "Jan 2024" / "يناير 2024" (Latin digits in both). */
export function periodLabel(start: string, view: string, language: AppLanguage): string {
  const year = start.slice(0, 4);
  const month = Number(start.slice(5, 7));
  if (view === 'annual') return year;
  if (view === 'quarterly') {
    const q = Math.floor((month - 1) / 3) + 1;
    return language === 'ar' ? `الربع ${q} ${year}` : `Q${q} ${year}`;
  }
  if (view === 'monthly') {
    return new Intl.DateTimeFormat(LOCALES[language], { month: 'short', year: 'numeric', timeZone: 'UTC' })
      .format(new Date(`${start.slice(0, 7)}-01T00:00:00Z`));
  }
  return year;
}

/** A year-to-date period: "Jan–Aug 2026" / "يناير–أغسطس 2026". */
export function ytdLabel(start: string, end: string, language: AppLanguage): string {
  const fmt = new Intl.DateTimeFormat(LOCALES[language], { month: 'short', timeZone: 'UTC' });
  return `${fmt.format(new Date(`${start}T00:00:00Z`))}–${fmt.format(new Date(`${end}T00:00:00Z`))} ${end.slice(0, 4)}`;
}

function toNumber(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

type Shape = 'circle' | 'hollow' | 'square' | 'diamond' | 'forecast';
const SHAPE: Record<string, Shape> = { observed: 'circle', provisional: 'hollow', estimate: 'square', derived: 'diamond', forecast: 'forecast' };

function Marker({ x, y, shape }: { x: number; y: number; shape: Shape }) {
  const stroke = shape === 'forecast' ? 'var(--chart-2)' : 'var(--chart-1)';
  if (shape === 'square') return <rect x={x - 4} y={y - 4} width={8} height={8} fill="var(--card)" stroke={stroke} strokeWidth="2" />;
  if (shape === 'diamond') return <polygon points={`${x},${y - 5} ${x + 5},${y} ${x},${y + 5} ${x - 5},${y}`} fill={stroke} stroke={stroke} strokeWidth="1.5" />;
  return <circle cx={x} cy={y} r={4} fill={shape === 'circle' ? stroke : 'var(--card)'} stroke={stroke} strokeWidth="2" />;
}

function scale(values: number[]): { lo: number; hi: number; ticks: number[] } {
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

export function TimelineChart({ timeline }: { timeline: Timeline }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const rtl = language === 'ar';
  const rows = timeline.rows;
  const values = rows.flatMap((r) => [toNumber(r.value), toNumber(r.interval?.lower80), toNumber(r.interval?.upper80)])
    .filter((v): v is number => v !== null);
  const plotted = rows.filter((r) => r.value !== null).length;
  if (plotted < 2) {
    return <p className="text-sm text-muted-foreground" data-testid="series-chart-empty">{t('series.chartNeedsTwo')}</p>;
  }
  const W = 720, H = 260, T = 16, B = 40;
  // The value labels sit on the start side: left in English, right in Arabic.
  const L = rtl ? 24 : 64, R = rtl ? 64 : 24;
  const { lo, hi, ticks } = scale(values);
  const step = rows.length > 1 ? (W - L - R) / (rows.length - 1) : 0;
  const xAt = (i: number) => (rtl ? W - R - i * step : L + i * step);
  const yAt = (v: number) => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  // Lines: consecutive published points only (a missing period breaks the line).
  const segments: { path: string; forecast: boolean }[] = [];
  let current: string[] = [];
  let currentForecast = false;
  rows.forEach((r, i) => {
    const v = toNumber(r.value);
    const forecast = r.nature === 'forecast';
    if (v === null || forecast !== currentForecast) {
      if (current.length > 1) segments.push({ path: current.join(' '), forecast: currentForecast });
      current = [];
      currentForecast = forecast;
    }
    if (v !== null) current.push(`${current.length ? 'L' : 'M'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`);
  });
  if (current.length > 1) segments.push({ path: current.join(' '), forecast: currentForecast });
  const band = rows.map((r, i) => ({ i, lo: toNumber(r.interval?.lower80), hi: toNumber(r.interval?.upper80) }))
    .filter((p): p is { i: number; lo: number; hi: number } => p.lo !== null && p.hi !== null);
  const every = Math.max(1, Math.ceil(rows.length / 8));
  const natures = [...new Set(rows.filter((r) => r.value !== null).map((r) => r.nature))];
  const unit = timeline.unit?.label[language] ?? '';
  return (
    <figure className="flex flex-col gap-2" data-testid="series-chart" data-dataset-id={timeline.dataset_id ?? ''} data-points={plotted}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
        aria-label={t('series.chartLabel', { name: timeline.indicator.name[language], unit, count: plotted })}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={yAt(v)} y2={yAt(v)} stroke="var(--border)" strokeDasharray={v === 0 ? undefined : '2 4'} />
            <text x={rtl ? W - 4 : 4} y={yAt(v) + 4} fontSize="11" fill="var(--muted-foreground)" textAnchor={rtl ? 'end' : 'start'}
              direction="ltr" unicodeBidi="plaintext">
              {formatCompact(v, language)}
            </text>
          </g>
        ))}
        {band.length > 1 ? (
          <polygon fill="var(--chart-2)" opacity="0.15"
            points={[...band.map((p) => `${xAt(p.i)},${yAt(p.hi)}`), ...[...band].reverse().map((p) => `${xAt(p.i)},${yAt(p.lo)}`)].join(' ')} />
        ) : null}
        {segments.map((s, k) => (
          <path key={k} d={s.path} fill="none" stroke={s.forecast ? 'var(--chart-2)' : 'var(--chart-1)'} strokeWidth="2.5"
            strokeDasharray={s.forecast ? '6 4' : undefined} strokeLinejoin="round" />
        ))}
        {rows.map((r, i) => {
          const v = toNumber(r.value);
          if (v === null) {
            return <line key={r.period_start} x1={xAt(i)} x2={xAt(i)} y1={H - B - 6} y2={H - B} stroke="var(--muted-foreground)" data-missing="true" />;
          }
          return (
            <g key={r.period_start} data-nature={r.nature}>
              <title>{`${periodLabel(r.period_start, timeline.view, language)}: ${r.value_operator ?? ''}${formatDecimal(r.value, language) ?? ''} ${unit} · ${t(`series.nature.${r.nature}`)}`}</title>
              <Marker x={xAt(i)} y={yAt(v)} shape={SHAPE[r.nature] ?? 'circle'} />
            </g>
          );
        })}
        {rows.map((r, i) => (i % every === 0 || i === rows.length - 1 ? (
          <text key={`x-${r.period_start}`} x={xAt(i)} y={H - 14} fontSize="11" fill="var(--muted-foreground)"
            // The first and last labels are anchored inwards so they are never cut off.
            textAnchor={rows.length > 1 && i === 0 ? (rtl ? 'end' : 'start') : rows.length > 1 && i === rows.length - 1 ? (rtl ? 'start' : 'end') : 'middle'}>
            {periodLabel(r.period_start, timeline.view, language)}
          </text>
        ) : null))}
      </svg>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{t('series.unit')}: {unit}</span>
        {natures.map((n) => (
          <span key={n} className="inline-flex items-center gap-1.5" data-legend={n}>
            <svg width="14" height="14" aria-hidden="true"><Marker x={7} y={7} shape={SHAPE[n] ?? 'circle'} /></svg>
            {t(`series.nature.${n}`)}
          </span>
        ))}
        {rows.some((r) => r.value === null) ? <span>{t('series.gapNote')}</span> : null}
      </figcaption>
    </figure>
  );
}

function ChangeCell({ change }: { change: SeriesChange | null }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  if (!change) return <span className="text-muted-foreground">—</span>;
  if (change.absolute === null) {
    return <span className="text-muted-foreground" title={change.reason?.[language]}>{t('series.notCalculated')}</span>;
  }
  const n = Number(change.absolute);
  const sign = n > 0 ? '+' : n < 0 ? '−' : '';
  return (
    <span className="tabular-nums" dir="ltr" title={change.reason?.[language]}>
      {sign}{formatDecimal(change.absolute.replace('-', ''), language)}
      {change.percent !== null ? ` (${Number(change.percent) > 0 ? '+' : ''}${formatDecimal(change.percent, language, 1)}%)` : ''}
    </span>
  );
}

function SourceCell({ row }: { row: SeriesRow }) {
  const language = useAppLanguage();
  const src = row.source;
  if (!src) return <span className="text-muted-foreground">{row.nature === 'derived' ? row.components.join(', ') : '—'}</span>;
  const label = [src.publisher, src.source_code].filter(Boolean).join(' · ') || src.dataset_title || '—';
  return src.url && /^https?:\/\//.test(src.url) ? (
    <a href={src.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2"
      title={src.dataset_title ?? undefined} lang={language === 'ar' ? 'en' : undefined}>
      {label}<ExternalLink aria-hidden="true" className="size-3" />
    </a>
  ) : <span title={src.dataset_title ?? undefined}>{label}</span>;
}

export function TimelineTable({ timeline, query }: { timeline: Timeline; query: TimelineQuery }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const unit = timeline.unit?.label[language] ?? '';
  const prevLabel = timeline.view === 'monthly' ? t('series.change.month') : timeline.view === 'quarterly' ? t('series.change.quarter') : null;
  return (
    <div className="flex flex-col gap-3" data-testid="series-table-block">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t('series.tableNote', { unit })}</p>
        <a href={timelineCsvUrl(query, language)} download data-testid="series-csv"
          className="inline-flex items-center gap-1.5 rounded-md border border-border-strong/60 px-3 py-1.5 text-xs font-medium hover:bg-muted">
          <Download aria-hidden="true" className="size-3.5" />{t('series.downloadCsv')}
        </a>
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[40rem] text-sm" data-testid="series-table" data-dataset-id={timeline.dataset_id ?? ''}>
          <caption className="sr-only">{t('series.tableCaption', { name: timeline.indicator.name[language] })}</caption>
          <thead className="bg-muted/60 text-xs">
            <tr>
              <th scope="col" className="px-3 py-2 text-start">{t('series.period')}</th>
              <th scope="col" className="px-3 py-2 text-end">{t('series.value')} ({unit})</th>
              <th scope="col" className="px-3 py-2 text-start">{t('series.kind')}</th>
              {prevLabel ? <th scope="col" className="px-3 py-2 text-end">{prevLabel}</th> : null}
              <th scope="col" className="px-3 py-2 text-end">{t('series.change.year')}</th>
              <th scope="col" className="px-3 py-2 text-start">{t('series.source')}</th>
            </tr>
          </thead>
          <tbody>
            {timeline.rows.map((r) => {
              const { previous, yearAgo } = changesOf(r);
              const yearChange = timeline.view === 'annual' ? (r.changes[0] ?? null) : yearAgo;
              return (
                <tr key={r.period_start} className={cn('border-t border-border', r.value === null && 'text-muted-foreground')}
                  data-testid="series-row" data-period={r.period_start} data-nature={r.nature}>
                  <th scope="row" className="px-3 py-1.5 text-start font-medium">{periodLabel(r.period_start, timeline.view, language)}</th>
                  <td className="px-3 py-1.5 text-end tabular-nums" dir="ltr">
                    {r.value === null
                      ? <span title={r.reason?.[language]}>{t('series.notPublished')}</span>
                      : `${r.value_operator ?? ''}${formatDecimal(r.value, language, 3) ?? ''}`}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="inline-flex flex-wrap items-center gap-1">
                      <Badge variant={r.nature === 'observed' ? 'verified' : r.nature === 'missing' ? 'muted' : 'sand'}>{t(`series.nature.${r.nature}`)}</Badge>
                      {r.revised ? (
                        <Badge variant="outline" data-testid="series-revised"
                          title={r.other_publications.map((o) => `${o.value ?? '—'} (${o.source?.source_code ?? ''})`).join('; ')}>
                          {t('series.revised')}
                        </Badge>
                      ) : null}
                    </span>
                  </td>
                  {prevLabel ? <td className="px-3 py-1.5 text-end"><ChangeCell change={previous} /></td> : null}
                  <td className="px-3 py-1.5 text-end"><ChangeCell change={yearChange} /></td>
                  <td className="px-3 py-1.5 text-xs"><SourceCell row={r} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {timeline.year_to_date.length ? (
        <div data-testid="series-ytd">
          <h4 className="mb-1 text-sm font-semibold">{t('series.ytdHeading')}</h4>
          <p className="mb-2 text-xs text-muted-foreground">{t('series.ytdNote')}</p>
          <ul className="flex flex-col gap-1 text-sm">
            {timeline.year_to_date.map((r) => (
              <li key={`${r.period_start}-${r.period_end}`} className="flex flex-wrap items-center gap-2" data-testid="series-ytd-row">
                <span className="font-medium">{ytdLabel(r.period_start, r.period_end, language)}</span>
                <span className="tabular-nums" dir="ltr">{formatDecimal(r.value, language, 3) ?? t('series.notPublished')} {unit}</span>
                {r.changes[0] ? <ChangeCell change={r.changes[0]} /> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function TimelineRules({ timeline }: { timeline: Timeline }) {
  const language = useAppLanguage();
  if (!timeline.rules.length) return null;
  return (
    <ul className="flex list-disc flex-col gap-0.5 ps-4 text-xs text-muted-foreground" data-testid="series-rules">
      {timeline.rules.map((r) => <li key={r.code} data-rule={r.code}>{r[language]}</li>)}
    </ul>
  );
}

export function TimelineSources({ timeline }: { timeline: Timeline }) {
  const { t } = useTranslation();
  if (!timeline.sources.length) return null;
  return (
    <ul className="flex flex-col gap-1.5 text-sm" data-testid="series-sources">
      {timeline.sources.map((s, i) => (
        <li key={`${s.id ?? i}`} className="flex flex-wrap items-baseline gap-x-2">
          {s.url && /^https?:\/\//.test(s.url)
            ? <a href={s.url} target="_blank" rel="noreferrer noopener" className="text-primary underline underline-offset-2">{s.dataset_title}</a>
            : <span>{s.dataset_title}</span>}
          <span className="text-xs text-muted-foreground">
            {[s.publisher, s.source_code, s.access_date ? t('series.accessed', { date: s.access_date }) : null].filter(Boolean).join(' · ')}
          </span>
        </li>
      ))}
    </ul>
  );
}
