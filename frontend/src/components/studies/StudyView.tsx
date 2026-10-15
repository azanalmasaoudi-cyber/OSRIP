import { ArrowDown, ArrowUp, ArrowUpDown, Download, ExternalLink, RefreshCw } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { studyExportUrl, useReproduceStudy, type StoredStudy, type StudyColumn } from '@/api/studies';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { en } from '@/i18n/locales/en';
import { formatDecimal, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

import { StudyBarChart, StudyHeatmap, StudyLineChart, type LabelFor } from './StudyCharts';

/**
 * One stored study result: cards, findings, chart, table, method, assumptions, limitations,
 * sources and downloads, all read from the same validated document (osrip.study/1). The
 * table can be sorted and filtered without changing any value.
 */

type Row = Record<string, string | null>;
type StatusCode = keyof typeof en.studies.status;
type CellCode = keyof typeof en.studies.code;

const isStatus = (v: string): v is StatusCode => Object.hasOwn(en.studies.status, v);
const isCode = (v: string): v is CellCode => Object.hasOwn(en.studies.code, v);
const STATUS_VARIANT: Partial<Record<StatusCode, 'verified' | 'sand' | 'muted' | 'outline'>> = {
  published: 'verified',
  eligible: 'verified',
  missing_in_source: 'sand',
  withheld: 'sand',
  no_published_value: 'muted',
};

export function useLabels(language: AppLanguage) {
  const { t } = useTranslation();
  /** A text cell in the reader's language: an Arabic sibling column, a known code, or as published. */
  const text: LabelFor = (row, key) => {
    const value = (language === 'ar' ? row[`${key}_ar`] : undefined) ?? row[key] ?? '';
    return isCode(value) ? t(`studies.code.${value}`) : value;
  };
  const status = (value: string | null) => {
    if (value == null) return '';
    const code = value.replaceAll(' ', '_');
    return isStatus(code) ? t(`studies.status.${code}`) : value;
  };
  return { text, status };
}

function Cell({ column, row, language }: { column: StudyColumn; row: Row; language: AppLanguage }) {
  const { t } = useTranslation();
  const labels = useLabels(language);
  const value = row[column.key] ?? null;
  if (column.kind === 'number') {
    // An empty cell is "no value" (missing in the source, or nothing to calculate); the
    // status and note columns say which. It is never shown as zero.
    return value === null
      ? <span className="text-muted-foreground"><span aria-hidden="true">—</span><span className="sr-only">{t('studies.noValue')}</span></span>
      : <span dir="ltr" className="tabular-nums">{formatDecimal(value, language, 4) ?? value}</span>;
  }
  if (column.kind === 'status') {
    if (value === null) return null;
    const code = value.replaceAll(' ', '_');
    return <Badge variant={isStatus(code) ? (STATUS_VARIANT[code] ?? 'outline') : 'outline'}>{labels.status(value)}</Badge>;
  }
  if (column.kind === 'period') return <span dir="ltr" className="tabular-nums">{labels.text(row, column.key)}</span>;
  return <bdi>{labels.text(row, column.key)}</bdi>;
}

/**
 * A sortable, filterable table of validated rows. Sorting and filtering never change a value.
 * ``rowIds`` give each row a stable id (``data-row``) and ``highlighted`` marks the rows a
 * spoken sentence is about; ``filterAlways`` shows the filter even for short tables.
 */
export function StudyTable({ columns, rows, language, rowIds, highlighted, filterAlways = false, caption }: {
  columns: StudyColumn[];
  rows: Row[];
  language: AppLanguage;
  rowIds?: readonly string[];
  highlighted?: ReadonlySet<string>;
  filterAlways?: boolean;
  caption?: string;
}) {
  const { t } = useTranslation();
  const labels = useLabels(language);
  const filterId = useId();
  const [needle, setNeedle] = useState('');
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(null);
  const shown = useMemo(() => {
    const indexed = rows.map((row, index) => ({ row, index }));
    const q = needle.trim().toLowerCase();
    const matching = q
      ? indexed.filter(({ row: r }) => columns.some((c) => `${labels.text(r, c.key)} ${labels.status(r[c.key] ?? null)}`.toLowerCase().includes(q)))
      : indexed;
    if (!sort) return matching;
    const column = columns.find((c) => c.key === sort.key);
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...matching].sort(({ row: a }, { row: b }) => {
      const x = a[sort.key] ?? null;
      const y = b[sort.key] ?? null;
      if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1; // missing always last
      if (column?.kind === 'number') return sign * (Number(x) - Number(y));
      return sign * labels.text(a, sort.key).localeCompare(labels.text(b, sort.key), language);
    });
  }, [rows, columns, needle, sort, labels, language]);

  const toggle = (key: string) =>
    setSort((s) => (s?.key !== key ? { key, dir: 'asc' } : s.dir === 'asc' ? { key, dir: 'desc' } : null));

  return (
    <div className="flex flex-col gap-2">
      {rows.length > 6 || filterAlways ? (
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor={filterId} className="text-sm font-medium">{t('studies.filterRows')}</label>
          <input id={filterId} type="search" value={needle} onChange={(e) => setNeedle(e.target.value)}
            className="h-9 w-full max-w-60 rounded-md border border-border-strong bg-card px-2 text-sm" data-testid="study-filter" />
          <span className="text-xs text-muted-foreground" role="status">{t('studies.rowsShown', { shown: shown.length, total: rows.length })}</span>
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[20rem] text-sm" data-testid="study-table">
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = !active ? ArrowUpDown : sort.dir === 'asc' ? ArrowUp : ArrowDown;
                const unit = c.unit ? ` (${language === 'ar' ? c.unit.label_ar : c.unit.label_en})` : '';
                return (
                  <th key={c.key} scope="col" className={cn('py-2 pe-3 font-medium first:ps-2', c.kind === 'number' ? 'text-end' : 'text-start')}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" onClick={() => toggle(c.key)} className="inline-flex items-center gap-1 rounded-sm hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                      aria-label={t('studies.sortBy', { column: c.label[language] })}>
                      <span>{c.label[language]}{unit}</span><Icon aria-hidden="true" className="size-3" />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ row: r, index }) => {
              const id = rowIds?.[index];
              const on = id !== undefined && Boolean(highlighted?.has(id));
              return (
                <tr key={id ?? index} data-testid="study-row" data-row={id} data-highlighted={on ? 'true' : undefined}
                  aria-current={on ? 'true' : undefined}
                  className={cn('border-b border-border last:border-0 transition-colors motion-reduce:transition-none', on && 'bg-copper-subtle/70 shadow-[inset_3px_0_0_var(--copper)] rtl:shadow-[inset_-3px_0_0_var(--copper)]')}>
                  {columns.map((c) => (
                    <td key={c.key} className={cn('py-2 pe-3 align-top first:ps-2', c.kind === 'number' && 'text-end')}>
                      <Cell column={c} row={r} language={language} />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Download_({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} download className="inline-flex items-center gap-1.5 rounded-md border border-border-strong px-3 py-1.5 text-sm font-medium hover:bg-muted">
      <Download aria-hidden="true" className="size-4" />{label}
    </a>
  );
}

export function StudyView({ stored, headingLevel = 2 }: { stored: StoredStudy; headingLevel?: 2 | 3 }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useLabels(language);
  const reproduce = useReproduceStudy();
  const study = stored.study;
  const H = headingLevel === 2 ? 'h2' : 'h3';
  const Sub = headingLevel === 2 ? 'h3' : 'h4';
  // Arabic sibling columns (area_ar, month_ar) are folded into their English column.
  const columns = study.table.columns.filter((c) => !c.key.endsWith('_ar'));
  const rows = study.table.rows;
  const unitLabel = (u?: { label_en: string; label_ar: string } | null) => (u ? (language === 'ar' ? u.label_ar : u.label_en) : '');

  return (
    <article className="flex flex-col gap-5" data-testid="study-view" data-kind={study.kind} data-status={study.status}>
      <header className="flex flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">{t(`studies.kinds.${study.kind}`)}</Badge>
          <DataModeBadge mode={study.data_mode} />
          <Badge variant={study.status === 'ok' ? 'verified' : 'sand'} data-testid="study-status">{t(`studies.statusLabel.${study.status}`)}</Badge>
        </p>
        <H className="text-lg font-semibold">{study.title[language]}</H>
        <p className="text-sm text-muted-foreground"><span className="font-medium">{t('studies.question')}:</span> {study.question[language]}</p>
        {study.data_mode === 'synthetic' ? <p className="text-xs text-synthetic-foreground">{t('studies.synthetic')}</p> : null}
      </header>

      {study.reason ? (
        <p className="rounded-md border border-sand/60 bg-sand-subtle/60 p-3 text-sm" role="status" data-testid="study-reason">{study.reason[language]}</p>
      ) : null}

      {study.cards.length ? (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {study.cards.map((c, i) => (
            <li key={i} className="rounded-lg border border-border bg-card p-3" data-testid="study-card" data-nature={c.nature}>
              <p className="text-xs text-muted-foreground">{c.label[language]}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {c.value === null ? <span className="text-base italic text-muted-foreground">{t('studies.missing')}</span>
                  : <span dir="ltr">{formatDecimal(c.value, language, 3) ?? c.value}</span>}
                <span className="ms-1 text-sm font-normal text-muted-foreground">{unitLabel(c.unit)}</span>
              </p>
              <p className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {c.period ? <span dir="ltr">{c.period}</span> : null}
                {c.nature !== 'observed' ? <Badge variant={c.nature === 'scenario' ? 'sand' : 'outline'}>{t(`studies.nature.${c.nature}`)}</Badge> : null}
              </p>
            </li>
          ))}
        </ul>
      ) : null}

      {study.findings.length ? (
        <section className="flex flex-col gap-2">
          <Sub className="font-semibold">{t('studies.findings')}</Sub>
          <ul className="list-disc ps-5 text-sm" data-testid="study-findings">
            {study.findings.map((f, i) => (
              <li key={i}>{f.text[language]}{f.evidence.length ? <span className="ms-1 font-mono text-xs text-muted-foreground" dir="ltr">[{f.evidence.join(', ')}]</span> : null}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {study.charts.map((chart, i) => (
        <section key={i} className="rounded-lg border border-border bg-card p-3">
          {chart.type === 'line' ? <StudyLineChart chart={chart} rows={rows} labelFor={labels.text} />
            : chart.type === 'bar' ? <StudyBarChart chart={chart} rows={rows} labelFor={labels.text} />
              : <StudyHeatmap chart={chart} rows={rows} labelFor={labels.text} />}
          {chart.type !== 'heatmap' ? <p className="mt-2 text-xs text-muted-foreground">{t('studies.chartNote')}</p> : null}
        </section>
      ))}

      {rows.length ? (
        <section className="flex flex-col gap-2">
          <Sub className="font-semibold">{t('studies.tableHeading')}</Sub>
          <StudyTable columns={columns} rows={rows} language={language} />
        </section>
      ) : null}

      <section className="grid gap-4 text-sm md:grid-cols-2">
        <div>
          <Sub className="font-semibold">{t('studies.method')}</Sub>
          <p className="mt-1 text-muted-foreground">{study.method[language]}</p>
        </div>
        {study.assumptions.length ? (
          <div>
            <Sub className="font-semibold">{t('studies.assumptions')}</Sub>
            <ul className="mt-1 list-disc ps-5 text-muted-foreground">{study.assumptions.map((a, i) => <li key={i}>{a[language]}</li>)}</ul>
          </div>
        ) : null}
        {study.limitations.length ? (
          <div data-testid="study-limitations">
            <Sub className="font-semibold">{t('studies.limitations')}</Sub>
            <ul className="mt-1 list-disc ps-5 text-muted-foreground">{study.limitations.map((a, i) => <li key={i}>{a[language]}</li>)}</ul>
          </div>
        ) : null}
        {study.next_questions.length ? (
          <div>
            <Sub className="font-semibold">{t('studies.nextQuestions')}</Sub>
            <ul className="mt-1 list-disc ps-5 text-muted-foreground">{study.next_questions.map((a, i) => <li key={i}>{a[language]}</li>)}</ul>
          </div>
        ) : null}
      </section>

      {study.evidence.length ? (
        <details className="rounded-lg border border-border p-3 text-sm" data-testid="study-sources">
          <summary className="cursor-pointer font-medium">{t('studies.sources')} ({study.evidence.length})</summary>
          {study.dataset_versions.length ? (
            <p className="mt-2 text-xs text-muted-foreground">{t('studies.datasetVersions')}: <span dir="ltr">{study.dataset_versions.join(', ')}</span></p>
          ) : null}
          <ul className="mt-2 flex flex-col gap-2">
            {study.evidence.map((e) => (
              <li key={e.id} className="rounded-md bg-muted/40 p-2">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs" dir="ltr">{e.id}</span>
                  <span dir="ltr" className="tabular-nums">{e.indicator} · {e.area} · {e.period_start} – {e.period_end}</span>
                  <span dir="ltr" className="tabular-nums">{e.value ?? '—'} {e.unit}</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {e.source_url ? (
                    <a href={e.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                      <bdi>{e.source_title}</bdi><ExternalLink aria-hidden="true" className="size-3" />
                    </a>
                  ) : <bdi>{e.source_title}</bdi>}
                  {' · '}<span dir="ltr">{e.dataset_version}</span>
                  {e.record_ref ? <> · {t('studies.record')}: <span dir="ltr" className="font-mono">{e.record_ref}</span></> : null}
                </p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <footer className="flex flex-wrap items-center gap-2">
        <Download_ href={studyExportUrl(stored.id, 'csv', language)} label={t('studies.exportCsv')} />
        <Download_ href={studyExportUrl(stored.id, 'json', language)} label={t('studies.exportJson')} />
        <Button type="button" variant="ghost" size="sm" onClick={() => reproduce.mutate(stored.id)} disabled={reproduce.isPending} data-testid="study-reproduce">
          <RefreshCw aria-hidden="true" className={cn('size-4', reproduce.isPending && 'motion-safe:animate-spin')} />{t('studies.reproduce')}
        </Button>
        {reproduce.data ? (
          <p className="basis-full text-sm" role="status" data-testid="study-reproduced">
            {reproduce.data.identical ? t('studies.reproduceSame') : t('studies.reproduceChanged', { versions: reproduce.data.current_versions.join(', ') })}
          </p>
        ) : null}
        {reproduce.isError ? <p className="basis-full text-sm text-destructive" role="alert">{reproduce.error.message}</p> : null}
      </footer>
    </article>
  );
}
