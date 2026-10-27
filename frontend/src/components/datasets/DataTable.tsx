import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { SelectField } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { csvField, download, safeCell } from '@/lib/exportResults';
import { cn } from '@/lib/utils';

/**
 * A table of text cells as the file holds them, with search, a filter on one column, sorting
 * and pages. Values are shown exactly as written (never reformatted or rounded); sorting reads
 * numbers for order only. A missing cell is shown as missing and sorts last either way. The
 * download contains the rows currently found, with spreadsheet formulas neutralised.
 */

export interface DataColumn {
  key: string;
  label: string;
  numeric?: boolean;
}

type Cell = string | null;
type Sort = { index: number; direction: 'asc' | 'desc' } | null;

const PAGE_SIZE = 50;
const MAX_FILTER_VALUES = 50;
const ARABIC_DIGITS = /[٠-٩۰-۹]/g;

function normalise(text: string): string {
  return text
    .replace(ARABIC_DIGITS, (d) => String((d.charCodeAt(0) & 0xf) % 10))
    .toLocaleLowerCase();
}

/** A number for ordering only: "1,234.5", "١٢٣", "12%"; null when the text is not one. */
export function sortNumber(text: Cell): number | null {
  if (text === null) return null;
  const t = normalise(text).replace(/[\s\u00a0,\u066c%]/g, '').replace('\u066b', '.');
  if (!/^[+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function DataTable({ columns, rows, caption, fileName, testId }: {
  columns: DataColumn[];
  rows: Cell[][];
  caption: string;
  fileName: string;
  testId?: string;
}) {
  const { t } = useTranslation();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const [filterColumn, setFilterColumn] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [sort, setSort] = useState<Sort>(null);
  const [page, setPage] = useState(0);

  // Columns with a short list of values can be filtered by value.
  const filterable = useMemo(() => columns.map((c, i) => {
    const values = new Set<string>();
    for (const r of rows) {
      const v = r[i];
      if (v != null) values.add(v);
      if (values.size > MAX_FILTER_VALUES) break;
    }
    return { index: i, column: c, values: values.size <= MAX_FILTER_VALUES && values.size > 1 ? [...values].sort() : null };
  }).filter((f) => f.values !== null), [columns, rows]);

  const found = useMemo(() => {
    const q = normalise(query.trim());
    const fi = filterColumn === '' ? -1 : Number(filterColumn);
    const out = rows
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => (fi < 0 || filterValue === '' || r[fi] === filterValue)
        && (q === '' || r.some((c) => c !== null && normalise(c).includes(q))));
    if (sort) {
      const numeric = columns[sort.index]?.numeric ?? false;
      const sign = sort.direction === 'asc' ? 1 : -1;
      out.sort((a, b) => {
        const x = a.r[sort.index] ?? null;
        const y = b.r[sort.index] ?? null;
        if (x === null || y === null) return x === y ? a.i - b.i : x === null ? 1 : -1;
        if (numeric) {
          const nx = sortNumber(x);
          const ny = sortNumber(y);
          if (nx !== null && ny !== null && nx !== ny) return (nx - ny) * sign;
        }
        return (x.localeCompare(y) || a.i - b.i) * sign;
      });
    }
    return out;
  }, [rows, columns, query, filterColumn, filterValue, sort]);

  const pages = Math.max(1, Math.ceil(found.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const shown = found.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  const toggleSort = (index: number) => {
    setPage(0);
    setSort((s) => (s?.index !== index ? { index, direction: 'asc' } : s.direction === 'asc' ? { index, direction: 'desc' } : null));
  };

  const exportFound = () => {
    const lines = [columns.map((c) => csvField(safeCell(c.label))).join(',')];
    for (const { r } of found) lines.push(r.map((v) => csvField(safeCell(v))).join(','));
    download(fileName, `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`, 'text/csv;charset=utf-8');
  };

  const filterInfo = filterable.find((f) => String(f.index) === filterColumn);

  return (
    <div className="flex flex-col gap-3" data-testid={testId}>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-48 flex-1 flex-col gap-1.5">
          <label htmlFor={searchId} className="text-xs font-medium text-muted-foreground">{t('datasets.table.search')}</label>
          <div className="relative">
            <Search aria-hidden="true" className="pointer-events-none absolute inset-y-0 start-3 my-auto size-4 text-muted-foreground" />
            <input id={searchId} type="search" value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(0); }}
              className="h-10 w-full rounded-md border border-border-strong bg-card ps-9 pe-3 text-sm" />
          </div>
        </div>
        {filterable.length > 0 ? (
          <SelectField label={t('datasets.table.filterColumn')} value={filterColumn} className="min-w-40"
            options={[{ value: '', label: t('datasets.table.noFilter') }, ...filterable.map((f) => ({ value: String(f.index), label: f.column.label }))]}
            onValueChange={(v) => { setFilterColumn(v); setFilterValue(''); setPage(0); }} />
        ) : null}
        {filterInfo?.values ? (
          <SelectField label={t('datasets.table.filterValue')} value={filterValue} className="min-w-40"
            options={[{ value: '', label: t('datasets.table.anyValue') }, ...filterInfo.values.map((v) => ({ value: v, label: v }))]}
            onValueChange={(v) => { setFilterValue(v); setPage(0); }} />
        ) : null}
        <Button variant="outline" size="sm" className="h-10" onClick={exportFound} disabled={found.length === 0}>
          <Download aria-hidden="true" />{t('datasets.table.downloadFound')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {t('datasets.table.count', { shown: found.length, total: rows.length })}
      </p>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-max text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-muted/60">
            <tr>
              {columns.map((c, i) => {
                const active = sort?.index === i;
                const Icon = !active ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown;
                return (
                  <th key={c.key} scope="col" aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                    className={cn('px-3 py-2 font-medium', c.numeric ? 'text-end' : 'text-start')}>
                    <button type="button" onClick={() => toggleSort(i)}
                      className="inline-flex items-center gap-1 rounded-sm hover:text-primary">
                      <span dir="auto">{c.label}</span>
                      <Icon aria-hidden="true" className={cn('size-3.5', !active && 'text-muted-foreground')} />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ r, i }) => (
              <tr key={i} className="border-t border-border">
                {columns.map((c, ci) => {
                  const v = r[ci] ?? null;
                  return (
                    <td key={c.key} className={cn('px-3 py-1.5', c.numeric ? 'text-end tabular-nums' : 'text-start')} dir={c.numeric ? 'ltr' : 'auto'}>
                      {v === null ? <span className="text-muted-foreground" title={t('datasets.table.missing')}>—<span className="sr-only">{t('datasets.table.missing')}</span></span> : v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 ? (
        <nav className="flex items-center justify-end gap-2" aria-label={t('datasets.table.pages')}>
          <Button variant="outline" size="sm" onClick={() => setPage(current - 1)} disabled={current === 0} aria-label={t('datasets.table.previous')}>
            <ChevronLeft aria-hidden="true" className="rtl:rotate-180" />
          </Button>
          <span className="text-xs text-muted-foreground">{t('datasets.table.page', { page: current + 1, pages })}</span>
          <Button variant="outline" size="sm" onClick={() => setPage(current + 1)} disabled={current >= pages - 1} aria-label={t('datasets.table.next')}>
            <ChevronRight aria-hidden="true" className="rtl:rotate-180" />
          </Button>
        </nav>
      ) : null}
    </div>
  );
}
