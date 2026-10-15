import { useTranslation } from 'react-i18next';

import { formatCompact, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * History and model estimates in one SVG, with distinct styles that do not rely on
 * colour alone: observations are a solid line with filled dots; estimates are a
 * dashed line with hollow dots over shaded 80% and 95% intervals, after a labelled
 * training-cutoff line. Hypothetical scenarios use a third style (dotted, square
 * markers). The time axis runs left to right in both languages; every value is also
 * in the table that accompanies the chart.
 */

export interface ChartPoint { period_start: string; period_end: string; value: string | null }
export interface EstimatePoint {
  period_start: string; period_end: string; estimate: string;
  lower80: string | null; upper80: string | null; lower95: string | null; upper95: string | null;
}
export interface ScenarioPoint { label: string; value: string }

const W = 640;
const H = 260;
const PAD = { top: 16, right: 16, bottom: 34, left: 56 };

function ticks(min: number, max: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) { min -= 1; max += 1; }
  const rough = (max - min) / 4;
  const mag = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= rough) ?? rough;
  const out: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= max + step / 2; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

export function ForecastChart({ history, estimates = [], scenario = [], unit, title }: {
  history: ChartPoint[]; estimates?: EstimatePoint[]; scenario?: ScenarioPoint[]; unit: string; title: string;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const hist = history.filter((p) => p.value !== null).map((p) => ({ label: p.period_start, v: Number(p.value) }));
  const est = estimates.map((e) => ({
    label: e.period_start, v: Number(e.estimate),
    l80: e.lower80 === null ? null : Number(e.lower80), u80: e.upper80 === null ? null : Number(e.upper80),
    l95: e.lower95 === null ? null : Number(e.lower95), u95: e.upper95 === null ? null : Number(e.upper95),
  }));
  const scen = scenario.map((s) => ({ label: s.label, v: Number(s.value) }));
  const labels = [...hist.map((p) => p.label), ...est.map((p) => p.label), ...scen.map((p) => p.label)];
  const all = [...hist.map((p) => p.v), ...est.flatMap((p) => [p.v, p.l95 ?? p.v, p.u95 ?? p.v]), ...scen.map((p) => p.v)];
  const yt = ticks(Math.min(...all), Math.max(...all));
  const y0 = yt[0] ?? 0;
  const y1 = yt.at(-1) ?? 1;
  const n = Math.max(labels.length - 1, 1);
  const x = (i: number) => PAD.left + (i / n) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - y0) / (y1 - y0 || 1)) * (H - PAD.top - PAD.bottom);
  const path = (pts: { i: number; v: number }[]) => pts.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
  const histPts = hist.map((p, i) => ({ i, v: p.v }));
  const lastHist = histPts.at(-1);
  const estPts = est.map((p, k) => ({ i: hist.length + k, v: p.v }));
  const band = (lo: 'l80' | 'l95', hi: 'u80' | 'u95') => {
    const ok = est.every((p) => p[lo] !== null && p[hi] !== null);
    if (!ok || est.length === 0 || !lastHist) return null;
    const upper = [{ i: lastHist.i, v: lastHist.v }, ...est.map((p, k) => ({ i: hist.length + k, v: p[hi] as number }))];
    const lower = [...est.map((p, k) => ({ i: hist.length + k, v: p[lo] as number })).reverse(), { i: lastHist.i, v: lastHist.v }];
    return `${path(upper)} ${lower.map((p) => `L${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')} Z`;
  };
  const scenPts = scen.map((p, k) => ({ i: hist.length + k, v: p.v }));
  const every = Math.ceil(labels.length / 8);

  return (
    <figure className="m-0" data-testid="forecast-chart" aria-label={t('forecasts.chartLabel', { title, unit })}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" aria-hidden="true" style={{ direction: 'ltr' }}>
        {yt.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="stroke-chart-grid" strokeWidth="1" />
            <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" className="fill-muted-foreground text-[11px]">{formatCompact(v, language)}</text>
          </g>
        ))}
        {labels.map((l, i) => (i % every === 0 || i === labels.length - 1 ? (
          <text key={l + i} x={x(i)} y={H - 12} textAnchor="middle" className="fill-muted-foreground text-[11px]">{l.slice(0, l.endsWith('-01-01') ? 4 : 7)}</text>
        ) : null))}
        {band('l95', 'u95') ? <path d={band('l95', 'u95') ?? ''} className="fill-accent/10" data-testid="band-95" /> : null}
        {band('l80', 'u80') ? <path d={band('l80', 'u80') ?? ''} className="fill-accent/20" data-testid="band-80" /> : null}
        {lastHist && (est.length || scen.length) ? (
          <g data-testid="cutoff-line">
            <line x1={x(lastHist.i)} x2={x(lastHist.i)} y1={PAD.top} y2={H - PAD.bottom} className="stroke-muted-foreground" strokeDasharray="2 3" />
            <text x={x(lastHist.i) + 4} y={PAD.top + 10} className="fill-muted-foreground text-[10px]">{est.length ? t('forecasts.cutoff') : t('forecasts.scenarioStart')}</text>
          </g>
        ) : null}
        <path d={path(histPts)} className="fill-none stroke-primary" strokeWidth="2.5" />
        {histPts.map((p) => <circle key={p.i} cx={x(p.i)} cy={y(p.v)} r="3" className="fill-primary" />)}
        {lastHist && estPts.length ? (
          <>
            <path d={path([lastHist, ...estPts])} className="fill-none stroke-accent" strokeWidth="2.5" strokeDasharray="7 5" data-testid="estimate-line" />
            {estPts.map((p) => <circle key={p.i} cx={x(p.i)} cy={y(p.v)} r="4" className="fill-card stroke-accent" strokeWidth="2" />)}
          </>
        ) : null}
        {lastHist && scenPts.length ? (
          <>
            <path d={path([lastHist, ...scenPts])} className="fill-none stroke-sand-foreground" strokeWidth="2" strokeDasharray="2 4" data-testid="scenario-line" />
            {scenPts.map((p) => <rect key={p.i} x={x(p.i) - 3.5} y={y(p.v) - 3.5} width="7" height="7" className="fill-sand-foreground" />)}
          </>
        ) : null}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-0.5 w-6 bg-primary" />{t('forecasts.legendObserved')}</span>
        {est.length ? <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="inline-block w-6 border-t-2 border-dashed border-accent" />{t('forecasts.legendEstimate')}</span> : null}
        {est.some((e) => e.l80 !== null) ? <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-3 w-6 bg-accent/20" />{t('forecasts.legendInterval')}</span> : null}
        {scen.length ? <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="inline-block w-6 border-t-2 border-dotted border-sand-foreground" />{t('forecasts.legendScenario')}</span> : null}
      </figcaption>
    </figure>
  );
}

/** Accessible table of the same values; estimates and scenarios are labelled row by row. */
export function ForecastTable({ history, estimates = [], unit }: { history: ChartPoint[]; estimates?: EstimatePoint[]; unit: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[30rem] text-sm" data-testid="forecast-table">
        <caption className="mb-1 text-start text-xs font-semibold">{t('forecasts.tableCaption', { unit })}</caption>
        <thead>
          <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
            <th scope="col" className="py-1 text-start font-medium">{t('table.period')}</th>
            <th scope="col" className="py-1 text-start font-medium">{t('forecasts.kind')}</th>
            <th scope="col" className="py-1 text-end font-medium">{t('table.value')}</th>
            <th scope="col" className="py-1 text-end font-medium">{t('forecasts.interval80')}</th>
            <th scope="col" className="py-1 text-end font-medium">{t('forecasts.interval95')}</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.period_start} className="border-b border-border">
              <td className="py-1">{formatPeriod(h.period_start, h.period_end, language)}</td>
              <td className="py-1 text-xs">{t('forecasts.observed')}</td>
              <td className="py-1 text-end tabular-nums" dir="ltr">{h.value === null ? t('states.dataUnavailable') : formatDecimal(h.value, language, 2)}</td>
              <td className="py-1 text-end">—</td><td className="py-1 text-end">—</td>
            </tr>
          ))}
          {estimates.map((e) => (
            <tr key={e.period_start} className="border-b border-border bg-accent/5" data-row="estimate">
              <td className="py-1">{formatPeriod(e.period_start, e.period_end, language)}</td>
              <td className="py-1 text-xs font-semibold text-accent">{t('forecasts.estimate')}</td>
              <td className="py-1 text-end tabular-nums" dir="ltr">{formatDecimal(e.estimate, language, 2)}</td>
              <td className="py-1 text-end tabular-nums text-xs" dir="ltr">{e.lower80 === null ? t('forecasts.noInterval') : `${formatDecimal(e.lower80, language, 2)} – ${formatDecimal(e.upper80, language, 2)}`}</td>
              <td className="py-1 text-end tabular-nums text-xs" dir="ltr">{e.lower95 === null ? t('forecasts.noInterval') : `${formatDecimal(e.lower95, language, 2)} – ${formatDecimal(e.upper95, language, 2)}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
