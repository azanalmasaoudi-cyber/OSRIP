import { CircleAlert, Info, Sigma } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { CalcInput, Calculation } from '@/api/analysis';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useCodeLabels } from '@/lib/useLabels';
import { cn } from '@/lib/utils';

const STATUS_VARIANT = {
  ok: 'verified',
  missing: 'accent',
  undefined: 'accent',
  incompatible: 'accent',
  not_calculated: 'muted',
  unavailable: 'muted',
} as const;

/** Rounds for display only; the unrounded value stays visible beside it. */
export function ResultValue({ value, unitCode, unitLabel }: { value: string; unitCode: string | undefined; unitLabel: string }) {
  const language = useAppLanguage();
  const digits = unitCode === 'fraction' ? 3 : 2;
  const shown = formatDecimal(value, language, digits) ?? value;
  const exact = formatDecimal(value, language, 12) ?? value;
  const suffix = unitCode === 'percent' ? '%' : ` ${unitLabel}`;
  return (
    <p className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-3xl font-semibold" dir="ltr" data-testid="calc-value">
        {shown}
        {suffix}
      </span>
      {exact !== shown ? (
        <span className="text-xs text-muted-foreground" dir="ltr" data-testid="calc-exact">
          = {exact}
        </span>
      ) : null}
    </p>
  );
}

export function InputsTable({ inputs }: { inputs: CalcInput[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  if (inputs.length === 0) return null;
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full text-xs" data-testid="calc-inputs">
        <caption className="sr-only">{t('analysis.inputs')}</caption>
        <thead>
          <tr className="border-b border-border-strong/40 text-muted-foreground">
            <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('analysis.role')}</th>
            <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('table.period')}</th>
            <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('table.value')}</th>
            <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('table.geography')}</th>
            <th scope="col" className="py-1.5 text-start font-medium">{t('analysis.version')}</th>
          </tr>
        </thead>
        <tbody>
          {inputs.map((i, n) => {
            const who = [i.commodity ? labels.commodity(i.commodity) : null, i.partner ? labels.partner(i.partner) : null]
              .filter(Boolean)
              .join(' · ');
            return (
              <tr key={`${i.role}-${n}`} className="border-b border-border align-top last:border-0">
                <td className="py-1.5 pe-3">
                  <span className="font-medium">{language === 'ar' ? i.indicator.name_ar : i.indicator.name_en}</span>
                  <br />
                  <span className="font-mono text-muted-foreground" dir="ltr">{i.role}</span>
                  {who ? <span className="block text-muted-foreground">{who}</span> : null}
                </td>
                <td className="py-1.5 pe-3">
                  {formatPeriod(i.period_start, i.period_end, language)}
                  {i.period_complete ? null : (
                    <span className="text-muted-foreground">
                      {' '}({i.period_kind === 'year_to_date' ? t('frequency.year_to_date') : t('table.incompletePeriod')})
                    </span>
                  )}
                </td>
                <td className="py-1.5 pe-3 text-end tabular-nums" dir="ltr">
                  {i.value === null ? (
                    <span className="italic text-muted-foreground" data-missing="true">{t('states.missingValue')}</span>
                  ) : (
                    <>
                      {formatDecimal(i.value, language, 4)} {language === 'ar' ? i.unit.label_ar : i.unit.label_en}
                    </>
                  )}
                </td>
                <td className="py-1.5 pe-3">{language === 'ar' ? i.area.name_ar : i.area.name_en}</td>
                <td className="py-1.5">
                  <span dir="ltr">{i.dataset_version.label}</span>
                  {i.record_ref ? (
                    <span className="block font-mono whitespace-nowrap text-muted-foreground" dir="ltr">
                      {i.record_ref}{i.source_locator ? ` · ${i.source_locator}` : ''}
                    </span>
                  ) : (
                    <span className="block font-mono break-all text-muted-foreground" dir="ltr">{i.source_row}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Limitations({ items }: { items: Array<{ code?: string; en: string; ar: string }> }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-sand-foreground">{t('analysis.caveats')}</p>
      <ul className="flex flex-col gap-1 text-xs" data-testid="calc-caveats">
        {items.map((c, n) => (
          <li key={`${c.code ?? n}`} className="flex gap-1.5" data-code={c.code}>
            <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-sand-foreground" />
            <span>{language === 'ar' ? c.ar : c.en}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One transparent calculation: result or reason, formula, inputs with provenance, limitations. */
export function CalculationCard({ calc }: { calc: Calculation }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  const l = (x: { en: string; ar: string }) => (language === 'ar' ? x.ar : x.en);
  const { result } = calc;
  const unitLabel = result.unit ? (language === 'ar' ? result.unit.label_ar : result.unit.label_en) : '';

  return (
    <Card className="flex flex-col gap-4 p-5" data-testid="calculation" data-kind={calc.kind} data-status={result.status}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-semibold">{l(calc.title)}</h3>
        <Badge variant={STATUS_VARIANT[result.status]}>{t(`analysis.status.${result.status}`)}</Badge>
      </div>

      {result.status === 'ok' && result.value !== null ? (
        <ResultValue value={result.value} unitCode={result.unit?.code} unitLabel={unitLabel} />
      ) : calc.reason ? (
        <div className={cn('flex gap-2 rounded-md border p-3 text-sm',
          result.status === 'unavailable' || result.status === 'not_calculated'
            ? 'border-border bg-muted/40' : 'border-accent/40 bg-card')} data-testid="calc-reason">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-accent" />
          <div>
            <p className="text-xs font-semibold">{t('analysis.reason')}</p>
            <p>{l(calc.reason)}</p>
          </div>
        </div>
      ) : null}

      <p className="flex items-start gap-2 text-sm">
        <Sigma aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <span>
          <span className="sr-only">{t('analysis.formula')}: </span>
          <span data-testid="calc-formula">{l(calc.formula)}</span>
        </span>
      </p>

      {calc.breakdown.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-semibold">{t('analysis.partnerShares')}</p>
          <ul className="grid gap-1 text-sm sm:grid-cols-3" data-testid="calc-breakdown">
            {calc.breakdown.map((b) => (
              <li key={b.partner} className="flex justify-between gap-2 rounded-md border border-border px-2 py-1">
                <span>{labels.partner(b.partner)}</span>
                <span className="tabular-nums" dir="ltr">
                  {b.value === null ? t('states.missingValue') : `${formatDecimal(b.value, language, 2)}%`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {calc.notes.length > 0 ? (
        <div className="rounded-md bg-sand-subtle/60 p-3 text-sm" data-testid="calc-notes">
          <p className="mb-1 text-xs font-semibold text-sand-foreground">{t('analysis.notes')}</p>
          {calc.notes.map((n, i) => <p key={i}>{l(n)}</p>)}
        </div>
      ) : null}

      <InputsTable inputs={calc.inputs} />
      <Limitations items={calc.caveats} />
    </Card>
  );
}
