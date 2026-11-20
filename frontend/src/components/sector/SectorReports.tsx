import { FileText, FolderOpen } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useReports } from '@/api/analysis';
import { NoFigure } from '@/components/common/NoFigure';
import { Badge } from '@/components/ui/badge';
import type { SectionCode } from '@/domain/types';
import { formatDate } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SHOWN = 5;

/**
 * The sector's saved reports (there is no Reports entry in the navigation): the platform reports
 * this person may open for this sector (published ones, and their own private ones), newest
 * first, each at its saved address (/reports/:id) with its PDF, Excel and CSV exports there. A
 * new report is asked of Al Mulhim (the Report button beside this) or saved from Tables and
 * charts; every saved report, including those made from answers and datasets, is at /reports.
 */
export function SectorReports({ section }: { section: SectionCode }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const reports = useReports();
  const mine = (reports.data ?? []).filter((r) => r.section === section);
  return (
    <section aria-labelledby={`${section}-reports-h`} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5"
      data-testid="sector-reports">
      <h2 id={`${section}-reports-h`} className="flex items-center gap-2 text-base font-semibold">
        <FileText aria-hidden="true" className="size-4 text-primary" />{t('sector.reports.heading')}
      </h2>
      <p className="text-sm text-muted-foreground">{t('sector.reports.lead')}</p>
      {reports.isPending ? <p className="text-sm text-muted-foreground">{t('states.loading')}</p>
        : reports.isError ? <NoFigure error={reports.error} />
          : mine.length ? (
            <ul className="flex flex-col divide-y divide-border">
              {mine.slice(0, SHOWN).map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <Link to={to(`/reports/${r.id}`)} className="min-w-0 flex-1 font-medium text-primary underline underline-offset-2" dir="auto"
                    data-testid="sector-report-link">{r.title}</Link>
                  <Badge variant="outline">{t(r.visibility === 'published' ? 'sector.reports.published' : 'sector.reports.private')}</Badge>
                  {r.generated_at ? <span className="text-xs text-muted-foreground">{formatDate(r.generated_at, language)}</span> : null}
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground" data-testid="sector-reports-empty">{t('sector.reports.empty')}</p>}
      <Link to={to('/reports')} className="inline-flex w-fit items-center gap-1.5 text-sm text-primary underline underline-offset-4" data-testid="sector-reports-all">
        <FolderOpen aria-hidden="true" className="size-4" />{t('sector.reports.all')}
      </Link>
    </section>
  );
}
