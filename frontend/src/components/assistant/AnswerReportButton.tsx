import { FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { useCreateAnswerReport } from '@/api/analysisReports';
import { Button } from '@/components/ui/button';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Freeze a verified answer (with its tables, charts and sources) as a report that can be
 * downloaded as PDF, Excel or CSV. Only offered for answers that passed the evidence check. */
export function AnswerReportButton({ messageId }: { messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const create = useCreateAnswerReport();
  if (create.isSuccess) {
    return (
      <p className="text-xs" role="status" data-testid="answer-report-created">
        {t('reportsAi.created')} ·{' '}
        <Link to={to(`/reports/analysis/${create.data.id}`)} className="text-primary underline underline-offset-2">{t('reportsAi.open')}</Link>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Button variant="outline" size="sm" className="w-fit" disabled={create.isPending} data-testid="answer-report"
        onClick={() => create.mutate({ messageId, language })}>
        <FileText aria-hidden="true" />{create.isPending ? t('reportsAi.creating') : t('reportsAi.fromAnswer')}
      </Button>
      {create.error ? <p className="text-xs text-destructive" role="alert">{create.error.message}</p> : null}
    </div>
  );
}
