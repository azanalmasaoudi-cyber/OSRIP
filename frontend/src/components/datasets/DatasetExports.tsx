import { Download, FileText } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { useCreateDatasetReport } from '@/api/analysisReports';
import { datasetExportUrl, type DatasetDetail } from '@/api/datasets';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Downloads built by the server (the rows as CSV; the rows with the analysis as Excel) and a
 * report frozen from the analysis, with the research questions the person writes. */
export function DatasetExports({ dataset }: { dataset: DatasetDetail }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const create = useCreateDatasetReport(dataset.id);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [questions, setQuestions] = useState('');
  const titleId = useId();
  const questionsId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const list = questions.split('\n').map((q) => q.trim()).filter(Boolean).slice(0, 5);
    create.mutate({ language, title: title.trim() || undefined, questions: list }, {
      onSuccess: (report) => void navigate(to(`/reports/analysis/${report.id}`)),
    });
  };

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap gap-2">
        <a href={datasetExportUrl(dataset.id, 'xlsx', language)} download className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="dataset-export-xlsx">
          <Download aria-hidden="true" />{t('datasets.exportExcel')}
        </a>
        <a href={datasetExportUrl(dataset.id, 'csv', language)} download className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="dataset-export-csv">
          <Download aria-hidden="true" />{t('datasets.exportCsv')}
        </a>
        <Button size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="dataset-report-open">
          <FileText aria-hidden="true" />{t('datasets.createReport')}
        </Button>
      </div>
      {open ? (
        <Card className="w-full max-w-xl p-4">
          <form onSubmit={submit} className="flex flex-col gap-3" data-testid="dataset-report-form">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={titleId} className="text-xs font-medium text-muted-foreground">{t('datasets.reportTitle')}</label>
              <input id={titleId} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={dataset.name}
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={questionsId} className="text-xs font-medium text-muted-foreground">{t('datasets.reportQuestions')}</label>
              <textarea id={questionsId} value={questions} rows={3} onChange={(e) => setQuestions(e.target.value)}
                className="rounded-md border border-border-strong bg-card px-3 py-2 text-sm" />
            </div>
            <p className="text-xs text-muted-foreground">{t('datasets.reportNote')}</p>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={create.isPending}>{create.isPending ? t('datasets.reportCreating') : t('datasets.reportCreate')}</Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>{t('datasets.cancel')}</Button>
            </div>
            {create.isError ? <p role="alert" className="text-sm text-destructive">{create.error.message}</p> : null}
          </form>
        </Card>
      ) : null}
    </div>
  );
}
