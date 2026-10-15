import { useTranslation } from 'react-i18next';

import type { Series } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatCompact, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Charts are drawn with HTML/CSS so they mirror with the text direction.
 * Numbers are parsed here for bar geometry only; displayed values come from
 * formatDecimal on the original decimal strings. The table next to every
 * chart carries the same values for assistive technology.
 */

/** Rounds the axis maximum up to 1, 2, 2.5 or 5 × 10^n and returns 4 evenly spaced ticks. */
function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(v);
  return ticks;
}

/** Columns over time for one series (single hue; no legend needed). */
export function ColumnChart({ series }: { series: Series }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const unit = series.unit.label[language];
  const observations = [...series.observations].sort((a, b) => a.periodStart.localeCompare(b.periodStart));
  const numeric = observations.map((o) => (o.value === null ? null : Number(o.value)));
  const ticks = niceTicks(Math.max(0, ...numeric.filter((v): v is number => v !== null && Number.isFinite(v))));
  const top = ticks.at(-1) ?? 1;

  return (
    <figure
      className="m-0"
      data-testid="column-chart"
      aria-label={t('chart.summary', { indicator: series.name[language], unit, n: observations.length })}
    >
      <div className="mt-6 flex gap-2" aria-hidden="true">
        {/* Value axis */}
        <div className="relative h-48 w-12 shrink-0 text-[11px] text-muted-foreground tabular-nums">
          {ticks.map((tick) => (
            <span key={tick} className="absolute end-0 translate-y-1/2 leading-none" style={{ bottom: `${(tick / top) * 100}%` }}>
              {formatCompact(tick, language)}
            </span>
          ))}
        </div>
        <div className="relative h-48 flex-1">
          {/* Recessive hairline grid */}
          {ticks.map((tick) => (
            <div
              key={tick}
              className={tick === 0 ? 'absolute inset-x-0 h-px bg-border-strong/60' : 'absolute inset-x-0 h-px bg-chart-grid'}
              style={{ bottom: `${(tick / top) * 100}%` }}
            />
          ))}
          <div className="absolute inset-0 flex items-end justify-around">
            {observations.map((obs, i) => {
              const value = numeric[i] ?? null;
              const formatted = formatDecimal(obs.value, language);
              const period = formatPeriod(obs.periodStart, obs.periodEnd, language);
              return (
                <div
                  key={obs.periodStart}
                  className="group relative flex h-full w-full max-w-24 justify-center"
                  title={`${period}: ${formatted ?? t('states.missingValue')} ${unit}`}
                >
                  {value === null ? (
                    <span className="absolute bottom-1 text-xs italic text-muted-foreground">{t('states.missingValue')}</span>
                  ) : (
                    <>
                      <span
                        className="absolute text-xs font-medium whitespace-nowrap text-foreground tabular-nums"
                        style={{ bottom: `calc(${(value / top) * 100}% + 4px)` }}
                      >
                        {formatCompact(value, language)}
                      </span>
                      <div
                        className="absolute bottom-0 w-6 rounded-t-[4px] bg-chart-1 transition-opacity group-hover:opacity-80"
                        style={{ height: `${(value / top) * 100}%` }}
                      />
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {/* Period axis */}
      <div className="ms-14 mt-2 flex justify-around text-xs text-muted-foreground" aria-hidden="true">
        {observations.map((obs) => (
          <span key={obs.periodStart} className="w-full max-w-24 text-center">
            {formatPeriod(obs.periodStart, obs.periodEnd, language)}
          </span>
        ))}
      </div>
    </figure>
  );
}

/**
 * Horizontal bars comparing partner rows of one indicator, flow and period.
 * Every value is printed, so the list itself is readable without the bars.
 */
export function PartnerBars({ rows, labelFor }: { rows: readonly Series[]; labelFor: (code: string) => string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const first = rows[0];
  const obs = first?.observations[0];
  const values = rows.map((s) => {
    const raw = s.observations[0]?.value ?? null;
    return raw === null ? null : Number(raw);
  });
  const max = Math.max(1, ...values.filter((v): v is number => v !== null));
  if (!first || !obs) return null;

  return (
    <figure className="m-0" data-testid="partner-bars">
      <figcaption className="mb-4">
        <p className="font-semibold">{t('chart.partnerTitle', { indicator: first.name[language] })}</p>
        <p className="text-sm text-muted-foreground">
          {t('chart.partnerSubtitle', {
            flow: first.flow ? t(FLOW_KEY[first.flow]) : '',
            period: formatPeriod(obs.periodStart, obs.periodEnd, language),
            unit: first.unit.label[language],
          })}
        </p>
      </figcaption>
      <ul className="flex flex-col gap-3">
        {rows.map((s, i) => {
          const value = values[i] ?? null;
          const formatted = formatDecimal(s.observations[0]?.value ?? null, language);
          return (
            <li key={s.partnerCode} className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 text-sm">
              <span className="truncate">{labelFor(s.partnerCode ?? '')}</span>
              <span className="h-5 rounded-e-[4px] bg-chart-grid/60" aria-hidden="true">
                {value !== null ? (
                  <span className="block h-full rounded-e-[4px] bg-chart-1" style={{ width: `${(value / max) * 100}%` }} />
                ) : null}
              </span>
              <span className="min-w-16 text-end tabular-nums" dir="ltr">
                {formatted ?? <span className="italic text-muted-foreground">{t('states.missingValue')}</span>}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-xs text-muted-foreground">{t('chart.partnerNote')}</p>
    </figure>
  );
}
