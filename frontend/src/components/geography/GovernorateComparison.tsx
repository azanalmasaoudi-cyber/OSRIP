import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAreaComparison, type CompareRow } from '@/api/library';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { SelectField } from '@/components/ui/select';
import type { DataMode } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

const STATUS_VARIANT = { published: 'verified', missing_in_source: 'sand', no_published_value: 'muted' } as const;
const FLOWS = ['import', 'domestic_export', 're_export'] as const;

/**
 * Each governorate's own published value for one indicator and period, from the server's
 * comparison (same unit and period length, or flagged as not comparable). Missing values
 * stay missing; national totals and combined figures are shown apart and never divided.
 */
export function GovernorateComparison({ mode, indicators }: {
  mode: DataMode;
  indicators: readonly { code: string; name_en: string; name_ar: string; frequency: string }[];
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [picked, setPicked] = useState<string | null>(null);
  const [period, setPeriod] = useState('');
  const [flow, setFlow] = useState<string | null>(null);
  const chosen = indicators.find((i) => i.code === picked) ?? indicators[0];
  const indicator = chosen?.code ?? null;
  const comparison = useAreaComparison(mode, indicator, period || null, flow, chosen?.frequency);
  if (!indicators.length) {
    return (
      <div data-testid="governorate-comparison">
        <p className="text-sm text-muted-foreground" role="status">{t('compare.noData')}</p>
      </div>
    );
  }
  const data = comparison.data;
  const unit = data?.unit ? (language === 'ar' ? data.unit.label_ar : data.unit.label_en) : '';
  const value = (row: { value: string | null; value_operator?: string | null }) =>
    row.value == null ? null : `${row.value_operator ?? ''}${formatDecimal(row.value, language, 4) ?? row.value}`;
  const name = (row: { name: { en: string; ar: string } }) => (language === 'ar' ? row.name.ar : row.name.en);
  const flows = data?.flows?.filter((f): f is (typeof FLOWS)[number] => (FLOWS as readonly string[]).includes(f)) ?? [];

  return (
    <div className="flex flex-col gap-3" data-testid="governorate-comparison">
      <p className="max-w-4xl text-sm text-muted-foreground">{t('compare.intro')}</p>
      <div className="flex flex-wrap items-end gap-3">
        <SelectField className="w-full sm:w-72" label={t('compare.indicator')} value={indicator ?? ''}
          onValueChange={(v) => { setPicked(v); setPeriod(''); setFlow(null); }}
          options={indicators.map((i) => ({ value: i.code, label: language === 'ar' ? i.name_ar : i.name_en }))}
          data-testid="compare-indicator" />
        <SelectField className="w-full sm:w-64" label={t('compare.period')} value={period} onValueChange={setPeriod}
          options={[
            { value: '', label: t('compare.latestComparable') },
            ...(data?.available_periods ?? []).map((p) => ({ value: p, label: p.slice(0, 7) === `${p.slice(0, 4)}-01` ? p.slice(0, 4) : p })),
          ]}
          data-testid="compare-period" />
        {flows.length || flow ? (
          <SelectField className="w-full sm:w-52" label={t('table.flow')} value={flow ?? ''} onValueChange={(v) => setFlow(v || null)}
            options={[{ value: '', label: '—' }, ...(flows.length ? flows : FLOWS).map((f) => ({ value: f, label: t(FLOW_KEY[f]) }))]} />
        ) : null}
      </div>
      {comparison.isPending ? <StatePanel kind="loading" skeleton="lines" />
        : comparison.isError ? <StatePanel kind="error" detail={comparison.error.message} onRetry={() => void comparison.refetch()} />
          : data?.status === 'no_data' ? <p className="text-sm" role="status">{t('compare.noData')}</p>
            : data?.status === 'choose_flow' ? <p className="text-sm" role="status">{t('compare.chooseFlow')}</p>
              : data ? (
                <>
                  {data.status === 'not_comparable' && data.reason ? (
                    <p className="rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-sm" role="status" data-testid="compare-not-comparable">
                      {t('compare.notComparable', { reason: t(`compare.reason.${data.reason}`) })}
                    </p>
                  ) : null}
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[19rem] text-sm" aria-busy={comparison.isFetching}>
                      <caption className="mb-2 text-start text-xs text-muted-foreground">
                        {data.indicator_name ? (language === 'ar' ? data.indicator_name.ar : data.indicator_name.en) : data.indicator}
                        {data.period_start && data.period_end ? ` · ${formatPeriod(data.period_start, data.period_end, language)}` : ''}
                        {unit ? ` · ${unit}` : ''}
                      </caption>
                      <thead>
                        <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                          <th scope="col" className="py-2 pe-4 text-start font-medium">{t('compare.area')}</th>
                          <th scope="col" className="py-2 pe-4 text-end font-medium">{t('compare.value')}{unit ? ` (${unit})` : ''}</th>
                          <th scope="col" className="py-2 text-start font-medium">{t('table.quality')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(data.rows ?? []).map((row: CompareRow) => (
                          <tr key={row.area} className="border-b border-border last:border-0" data-testid="compare-row" data-area={row.area} data-status={row.status}>
                            <th scope="row" className="py-2 pe-4 text-start font-normal">{name(row)}</th>
                            <td className="py-2 pe-4 text-end tabular-nums">
                              {value(row) ? <span dir="ltr">{value(row)}</span> : <span className="italic text-muted-foreground">{t(`compare.status.${row.status}`)}</span>}
                            </td>
                            <td className="py-2"><Badge variant={STATUS_VARIANT[row.status]}>{t(`compare.status.${row.status}`)}</Badge></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.areas_without_value ? <p className="text-xs text-muted-foreground">{t('compare.without', { count: data.areas_without_value })}</p> : null}
                  {data.national ? (
                    <p className="text-sm" data-testid="compare-national">
                      <span className="font-medium">{t('compare.national')}:</span>{' '}
                      {value(data.national) ? <span dir="ltr" className="tabular-nums">{value(data.national)}</span> : t(`compare.status.${data.national.status}`)} {unit}
                    </p>
                  ) : null}
                  {data.reporting_groups?.length ? (
                    <div className="text-sm">
                      <p className="font-medium">{t('compare.groups')}</p>
                      <ul className="list-disc ps-5">
                        {data.reporting_groups.map((g) => (
                          <li key={g.area}>{name(g)}: <span dir="ltr" className="tabular-nums">{g.value == null ? '—' : formatDecimal(g.value, language, 4)}</span> {unit}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </>
              ) : null}
    </div>
  );
}
