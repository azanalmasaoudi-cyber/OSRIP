import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react';
import { useId, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Sorting key; columns without one are not sortable. */
  sortValue?: (row: T) => string | number | null;
  /** Plain text for the CSV export (defaults to the sort value). */
  csv?: (row: T) => string;
  align?: 'start' | 'end';
  className?: string;
}

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/**
 * A table with search, sorting, paging, an explained empty state and an optional CSV export of the
 * rows as filtered and sorted. Everything happens in the browser over the rows it is given; the
 * caption names what the table holds and its unit or period.
 */
export function DataTable<T>({ rows, columns, rowKey, caption, search, pageSize = 25, empty, exportName, toolbar, testId, initialSort }: {
  rows: readonly T[];
  columns: readonly Column<T>[];
  rowKey: (row: T) => string;
  caption: string;
  /** Text searched for each row; without it there is no search box. */
  search?: (row: T) => string;
  pageSize?: number;
  empty: string;
  /** File name (without .csv) to offer a CSV export. */
  exportName?: string;
  /** Extra controls (filters) shown before the search box. */
  toolbar?: ReactNode;
  testId?: string;
  initialSort?: { key: string; direction: 'asc' | 'desc' };
}) {
  const { t } = useTranslation();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState(initialSort ?? null);
  const [page, setPage] = useState(0);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const found = needle && search ? rows.filter((row) => search(row).toLowerCase().includes(needle)) : [...rows];
    const column = sort ? columns.find((c) => c.key === sort.key) : undefined;
    if (column?.sortValue) {
      const value = column.sortValue;
      found.sort((a, b) => {
        const x = value(a);
        const y = value(b);
        if (x === y) return 0;
        if (x === null) return 1; // missing values last, whichever the direction
        if (y === null) return -1;
        const order = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
        return sort?.direction === 'desc' ? -order : order;
      });
    }
    return found;
  }, [rows, query, search, sort, columns]);

  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const current = Math.min(page, pages - 1);
  const visible = shown.slice(current * pageSize, (current + 1) * pageSize);

  const toggleSort = (key: string) => {
    setSort((now) => (now?.key === key ? { key, direction: now.direction === 'asc' ? 'desc' : 'asc' } : { key, direction: 'asc' }));
    setPage(0);
  };

  const download = () => {
    const header = columns.map((c) => csvCell(c.header)).join(',');
    const lines = shown.map((row) => columns.map((c) => csvCell(c.csv?.(row) ?? String(c.sortValue?.(row) ?? ''))).join(','));
    const blob = new Blob([`\uFEFF${[header, ...lines].join('\r\n')}\r\n`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportName ?? 'osrip-table'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-3" data-testid={testId}>
      <div className="flex flex-wrap items-end gap-3">
        {toolbar}
        {search ? (
          <div className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-xs">
            <label htmlFor={searchId} className="text-sm font-medium">{t('table.search')}</label>
            <span className="relative">
              <Search aria-hidden="true" className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input id={searchId} type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                className="h-10 w-full rounded-lg border border-border-strong bg-card ps-9 pe-3 text-sm" data-testid="table-search" />
            </span>
          </div>
        ) : null}
        {exportName && shown.length ? (
          <Button type="button" variant="outline" size="sm" onClick={download} className="ms-auto" data-testid="table-export">
            <Download aria-hidden="true" />{t('table.exportCsv')}
          </Button>
        ) : null}
      </div>
      <div className="relative overflow-x-auto rounded-xl border border-border glass-card">
        <table className="w-full min-w-[36rem] text-sm">
          <caption className="px-4 pt-3 text-start text-xs text-muted-foreground">
            {caption} · {t('table.rowsShown', { count: shown.length })}
          </caption>
          <thead>
            <tr className="border-b border-border-strong/30 text-xs text-muted-foreground">
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = !active ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown;
                return (
                  <th key={c.key} scope="col" className={cn('px-3 py-2.5 font-medium', c.align === 'end' ? 'text-end' : 'text-start')}
                    aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}>
                    {c.sortValue ? (
                      <button type="button" onClick={() => toggleSort(c.key)} className="inline-flex items-center gap-1 rounded-md hover:text-foreground">
                        {c.header}<Icon aria-hidden="true" className={cn('size-3.5', !active && 'opacity-50')} />
                      </button>
                    ) : c.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-muted-foreground" data-testid="table-empty">{empty}</td></tr>
            ) : visible.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border transition-colors last:border-0 hover:bg-primary-soft/60">
                {columns.map((c) => (
                  <td key={c.key} className={cn('px-3 py-2 align-top', c.align === 'end' && 'text-end tabular-nums', c.className)}>{c.cell(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 ? (
        <nav aria-label={t('table.pages')} className="flex items-center justify-end gap-2 text-sm">
          <Button type="button" variant="outline" size="sm" disabled={current === 0} onClick={() => setPage(current - 1)} aria-label={t('table.previous')}>
            <ChevronLeft aria-hidden="true" className="rtl:-scale-x-100" />
          </Button>
          <span className="tabular-nums" aria-live="polite">{t('table.page', { page: current + 1, pages })}</span>
          <Button type="button" variant="outline" size="sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} aria-label={t('table.next')}>
            <ChevronRight aria-hidden="true" className="rtl:-scale-x-100" />
          </Button>
        </nav>
      ) : null}
    </div>
  );
}
