import { Download, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import {
  analysisReportExportUrl,
  useAnalysisReport,
  useDeleteAnalysisReport,
  type ReportBlock,
  type ReportDocument,
} from '@/api/analysisReports';
import { adapterKind } from '@/api/config';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { ViewChart } from '@/components/datasets/ViewChart';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatDateTime } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * A research or dataset report as frozen by the server: the page shows its stored text,
 * tables and charts in the report's own language and direction, and links to the server's
 * PDF, Excel and CSV files. Nothing on the page is recalculated.
 */

function Block({ block, index, rtl }: { block: ReportBlock; index: number; rtl: boolean }) {
  const { t } = useTranslation();
  if (block.type === 'paragraph') {
    return <p className={block.note ? 'text-xs text-muted-foreground' : 'text-sm leading-relaxed'}>{block.text}</p>;
  }
  if (block.type === 'bullets') {
    return <ul className="flex list-disc flex-col gap-1 ps-5 text-sm">{block.items.map((item, i) => <li key={i}>{item}</li>)}</ul>;
  }
  if (block.type === 'chart') {
    const view = {
      id: `report-${index}`,
      title: { en: block.title, ar: block.title },
      table: block.table,
      chart: block.chart,
      alternatives: [block.chart.type],
      note: block.note ? { en: block.note, ar: block.note } : null,
    };
    return <Card className="p-4" dir={rtl ? 'rtl' : 'ltr'}><ViewChart view={view} /></Card>;
  }
  return (
    <div className="flex flex-col gap-1">
      {block.title ? <p className="text-sm font-semibold">{block.title}</p> : null}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-max text-sm">
          {block.title ? <caption className="sr-only">{block.title}</caption> : null}
          <thead className="bg-muted/60">
            <tr>{block.columns.map((c, i) => <th key={i} scope="col" className={c.numeric ? 'px-3 py-2 text-end font-medium' : 'px-3 py-2 text-start font-medium'}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {block.rows.map((row, r) => (
              <tr key={r} className="border-t border-border">
                {row.map((cell, i) => (
                  <td key={i} className={block.columns[i]?.numeric ? 'px-3 py-1.5 text-end tabular-nums' : 'px-3 py-1.5'} dir={block.columns[i]?.numeric ? 'ltr' : 'auto'}>
                    {cell ?? <span className="text-muted-foreground">—<span className="sr-only">{t('datasets.table.missing')}</span></span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.note ? <p className="text-xs text-muted-foreground">{block.note}</p> : null}
    </div>
  );
}

function ReportBody({ doc }: { doc: ReportDocument }) {
  const { t } = useTranslation();
  const rtl = doc.language === 'ar';
  return (
    <article dir={rtl ? 'rtl' : 'ltr'} lang={doc.language} className="flex flex-col gap-8" data-testid="analysis-report">
      <header className="flex flex-col gap-1 border-b-2 border-primary pb-4">
        <h2 className="text-2xl font-semibold text-primary">{doc.title}</h2>
        {doc.subtitle ? <p className="text-sm text-muted-foreground">{doc.subtitle}</p> : null}
        {doc.meta.map(([label, value]) => <p key={label} className="text-xs text-muted-foreground">{label}: <span dir="auto">{value}</span></p>)}
      </header>
      {doc.sections.map((section, s) => (
        <section key={section.heading} className="flex flex-col gap-3">
          <h3 className="text-lg font-semibold text-primary">{section.heading}</h3>
          {section.blocks.map((block, b) => <Block key={b} block={block} index={s * 100 + b} rtl={rtl} />)}
        </section>
      ))}
      {doc.references.length ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-lg font-semibold text-primary">{t('reportsAi.references')}</h3>
          <ol className="flex list-decimal flex-col gap-2 ps-5 text-sm">
            {doc.references.map((r, i) => (
              <li key={i}>
                <span>{[r.title, r.publisher, r.published, r.note].filter(Boolean).join(' · ')}</span>
                {r.url ? <><br /><a href={r.url} target="_blank" rel="noopener noreferrer" className="break-all text-primary underline underline-offset-2" dir="ltr">{r.url}</a></> : null}
                {r.retrieved ? <span className="block text-xs text-muted-foreground">{t('reportsAi.retrieved', { date: r.retrieved })}</span> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {doc.notice ? <p className="text-xs text-muted-foreground">{doc.notice}</p> : null}
    </article>
  );
}

export function AnalysisReportPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const { reportId } = useParams();
  const report = useAnalysisReport(reportId);
  const remove = useDeleteAnalysisReport();

  let body;
  if (adapterKind !== 'http') {
    body = <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>;
  } else if (report.isPending) {
    body = <StatePanel kind="loading" skeleton="lines" />;
  } else if (report.isError) {
    body = <StatePanel kind="error" detail={report.error.message} onRetry={() => void report.refetch()} />;
  } else {
    const r = report.data;
    const onDelete = () => {
      if (!window.confirm(t('reportsAi.deleteConfirm'))) return;
      remove.mutate(r.id, { onSuccess: () => void navigate(to('/reports')) });
    };
    body = (
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="muted">{r.kind === 'dataset' ? t('reportsAi.kindDataset') : t('reportsAi.kindResearch')}</Badge>
            <span>{formatDateTime(r.created_at, language)}</span>
            <Badge variant="outline">{t('reportsAi.frozen')}</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            {(['pdf', 'xlsx', 'csv'] as const).map((format) => (
              <a key={format} href={analysisReportExportUrl(r.id, format)} download data-testid={`analysis-report-export-${format}`}
                className={buttonVariants({ variant: format === 'pdf' ? 'default' : 'outline', size: 'sm' })}>
                <Download aria-hidden="true" />{t(`reportsAi.download.${format}`)}
              </a>
            ))}
            <Button variant="ghost" size="sm" onClick={onDelete} disabled={remove.isPending}>
              <Trash2 aria-hidden="true" />{t('datasets.delete')}
            </Button>
          </div>
        </div>
        <ReportBody doc={r.content} />
      </div>
    );
  }
  return (
    <>
      <PageHeader title={t('reportsAi.title')} intro={t('reportsAi.intro')} />
      <Link to={to('/reports')} className="mb-4 block w-fit text-sm text-primary underline underline-offset-2">{t('pages.reports.title')}</Link>
      {body}
    </>
  );
}
