import { FileText } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useCreateReport, type SectionFilters } from '@/api/analysis';
import { hasPermission, useMe } from '@/api/auth';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { SelectField } from '@/components/ui/select';
import type { DataMode, SectionCode } from '@/domain/types';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Freeze the current section view (filters, assumption, versions, results) as a report. */
export function SaveReportButton({ section, mode, filters, defaultTitle }: {
  section: SectionCode; mode: DataMode; filters: SectionFilters; defaultTitle: string;
}) {
  const { t } = useTranslation();
  const me = useMe();
  const create = useCreateReport();
  const to = usePreservedSearch();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(defaultTitle);
  const [visibility, setVisibility] = useState<'private' | 'published'>('private');

  if (!hasPermission(me.data, 'report.create')) return null;

  const { stock_assumption: stock, ...rest } = filters;
  const reportFilters = Object.fromEntries(Object.entries(rest).filter(([, v]) => v && v !== 'all')) as Record<string, string>;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate({ title, data_mode: mode, section, filters: reportFilters, stock_assumption: stock ?? 'assumed_zero', visibility });
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => { create.reset(); setOpen(true); }} data-testid="save-report" className="print:hidden">
        <FileText aria-hidden="true" />
        {t('saveReport.button')}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title={t('saveReport.title')} description={t('saveReport.note')}>
        {create.isSuccess ? (
          <div className="flex flex-col gap-3" role="status">
            <p>{t('saveReport.created')}</p>
            <Link to={to(`/reports/${create.data.id}`)} className={buttonVariants({ size: 'sm' })} data-testid="open-new-report">
              {t('saveReport.view')}
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3" data-testid="save-report-form">
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('saveReport.titleLabel')}
              <input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3}
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm text-foreground" />
            </label>
            <SelectField label={t('saveReport.visibility')} value={visibility}
              onValueChange={(v) => setVisibility(v === 'published' ? 'published' : 'private')}
              options={[{ value: 'private', label: t('saveReport.private') }, { value: 'published', label: t('saveReport.published') }]} />
            {create.isError ? <p role="alert" className="text-sm text-destructive">{create.error.message}</p> : null}
            <Button type="submit" disabled={create.isPending || title.trim().length < 3} className="w-fit">{t('saveReport.create')}</Button>
          </form>
        )}
      </Dialog>
    </>
  );
}
