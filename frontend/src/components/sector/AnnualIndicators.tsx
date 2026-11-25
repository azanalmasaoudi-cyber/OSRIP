import { CalendarRange, Download } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { annualTableCsvUrl, useAnnualTable } from '@/api/outlook';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { SelectField } from '@/components/ui/select';
import { formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';

const ALL = 'all';
const AREAS = {
  'OM-MA': 'annual.areas.muscat', 'OM-ZU': 'annual.areas.dhofar', 'OM-GRP-OTHER-WATER': 'annual.areas.other', 'OM-GRP-NWS': 'annual.areas.utility',
} as const;

/**
 * Electricity's or water's annual indicators side by side for 2022-2025, each a distinct
 * published series (consumption by category, net actual consumption, distributed, produced; water
 * produced and distributed by region; the utility's own figures as a separate scope). One year or
 * all years can be shown; the year-on-year changes are the server's. Provisional years are marked,
 * missing ones stay empty (never zero), and nothing is subtracted between rows.
 */
export function AnnualIndicators({ section }: { section: 'electricity' | 'water' }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const captionId = useId();
  const [year, setYear] = useState<string>(ALL);
  const query = useAnnualTable(section, mode);
  if (query.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (query.isError) return <StatePanel kind="error" error={query.error} onRetry={() => void query.refetch()} />;
  const data = query.data;
  const shown = year === ALL ? data.years : [year];
  const index = (y: string) => data.years.indexOf(y);
  const anyRows = data.groups.some((g) => g.rows.length);
  return (
    <section aria-labelledby={`${section}-annual-h`} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5"
      data-testid="annual-indicators" data-section={section}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`${section}-annual-h`} className="flex items-center gap-2 text-base font-semibold">
            <CalendarRange aria-hidden="true" className="size-4 text-primary" />{t('annual.heading', { first: data.years[0] ?? '', last: data.years[data.years.length - 1] ?? '' })}
          </h2>
          <p className="text-sm text-muted-foreground">{t('annual.lead')}</p>
        </div>
        <div className="flex w-full flex-wrap items-end gap-2 sm:w-auto">
          <SelectField label={t('annual.years')} value={year} onValueChange={setYear} className="w-full sm:w-56" data-testid="annual-year"
            options={[{ value: ALL, label: t('annual.allYears') }, ...data.years.map((y) => ({ value: y, label: y }))]} />
          {anyRows ? (
            <a href={annualTableCsvUrl(section, mode, language)} download data-testid="annual-csv"
              className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border-strong/60 px-3 py-1.5 text-sm font-medium hover:bg-muted">
              <Download aria-hidden="true" className="size-3.5" />{t('annual.downloadCsv')}
            </a>
          ) : null}
        </div>
      </div>
      {!anyRows ? <p role="status" className="text-base">{t('annual.none')}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm" aria-describedby={captionId} data-testid="annual-table">
            <caption id={captionId} className="mb-2 text-start text-xs text-muted-foreground">{t('annual.caption')}</caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-2 pe-3 text-start font-medium">{t('annual.indicator')}</th>
                <th scope="col" className="py-2 pe-3 text-start font-medium">{t('annual.unit')}</th>
                {shown.map((y) => <th key={y} scope="col" className="py-2 pe-3 text-end font-medium tabular-nums" dir="ltr">{y}</th>)}
              </tr>
            </thead>
            {data.groups.filter((g) => g.rows.length).map((g) => (
              <tbody key={g.code} data-testid="annual-group" data-group={g.code}>
                <tr><th scope="colgroup" colSpan={2 + shown.length} className="pt-3 pb-1 text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.label[language]}</th></tr>
                {g.rows.map((r) => (
                  <tr key={`${r.indicator.code}-${r.area}`} className="border-b border-border last:border-0" data-testid="annual-row" data-indicator={r.indicator.code} data-area={r.area}>
                    <th scope="row" className="py-1.5 pe-3 text-start font-normal">
                      {r.indicator.name[language]}
                      {r.area !== 'OM' ? <span className="block text-xs text-muted-foreground">{r.area in AREAS ? t(AREAS[r.area as keyof typeof AREAS]) : r.area}</span> : null}
                    </th>
                    <td className="py-1.5 pe-3 text-xs text-muted-foreground">{r.unit ? r.unit[language] : '—'}</td>
                    {shown.map((y) => {
                      const c = r.cells[index(y)];
                      return (
                        <td key={y} className="py-1.5 pe-3 text-end tabular-nums" data-year={y} data-provisional={c?.provisional || undefined}>
                          {c?.value != null ? (
                            <>
                              <bdi dir="ltr">{c.value_operator ?? ''}{formatDecimal(c.value, language, 1)}</bdi>
                              {c.provisional ? <Badge variant="sand" className="ms-1 px-1 py-0 text-[0.65rem]" title={t('annual.provisional')}>{t('annual.provisionalShort')}</Badge> : null}
                              {year !== ALL || !c.change_percent ? null : (
                                <span className="block text-xs text-muted-foreground" dir="ltr">{Number(c.change_percent) > 0 ? '+' : ''}{formatDecimal(c.change_percent, language, 1)}%</span>
                              )}
                            </>
                          ) : <span className="italic text-muted-foreground" title={t('states.missingValue')}>—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
      <ul className="flex list-disc flex-col gap-1 ps-5 text-xs text-muted-foreground" data-testid="annual-notes">
        <li>{t('annual.provisionalNote')}</li>
        {data.notes.map((n) => <li key={n.en}>{n[language]}</li>)}
      </ul>
    </section>
  );
}
