import { Download, FileText, Printer, Snowflake } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { reportExportUrl, useReport, useReports, useSetReportVisibility, type ReportContent } from '@/api/analysis';
import { platformReportExportUrl, useAnalysisReports } from '@/api/analysisReports';
import { useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { CalculationCard } from '@/components/analysis/CalculationCard';
import { ReviewCardView } from '@/components/analysis/ReviewCards';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatDateTime, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTION_TITLE = {
  electricity: 'nav.electricity',
  water: 'nav.water',
  food_security: 'nav.foodSecurity',
  trade: 'nav.trade',
} as const;

function sectionTitle(section: string | null): 'nav.electricity' | 'nav.water' | 'nav.foodSecurity' | 'nav.trade' | null {
  return section && section in SECTION_TITLE ? SECTION_TITLE[section as keyof typeof SECTION_TITLE] : null;
}

function KeyValues({ values, empty }: { values: Record<string, string>; empty: string }) {
  const entries = Object.entries(values);
  if (entries.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  return (
    <span className="font-mono text-xs" dir="ltr">
      {entries.map(([k, v]) => `${k}=${v}`).join(' · ')}
    </span>
  );
}

export function ReportsPage() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const reports = useReports();

  let body;
  if (adapterKind !== 'http') {
    body = <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>;
  } else if (reports.isPending) {
    body = <StatePanel kind="loading" skeleton="lines" />;
  } else if (reports.isError) {
    body = <StatePanel kind="error" detail={reports.error.message} onRetry={() => void reports.refetch()} />;
  } else if (reports.data.length === 0) {
    body = (
      <StatePanel kind="empty">
        <p className="text-sm text-muted-foreground">{t('pages.reports.none')} {t('pages.reports.createHint')}</p>
      </StatePanel>
    );
  } else {
    body = (
      <ul className="flex flex-col gap-3" data-testid="reports-list">
        {reports.data.map((r) => {
          const section = sectionTitle(r.section);
          return (
            <li key={r.id}>
              <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="flex min-w-0 flex-col gap-1">
                  <Link to={to(`/reports/${r.id}`)} className="font-semibold text-primary underline underline-offset-2">
                    {r.title}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {section ? t(section) : null} · <span dir="ltr">{r.generated_at?.slice(0, 16).replace('T', ' ')}</span>
                  </p>
                </div>
                <div className="flex gap-2">
                  <DataModeBadge mode={r.data_mode} />
                  <Badge variant="muted">{r.visibility === 'published' ? t('pages.reports.published') : t('pages.reports.private')}</Badge>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <>
      <PageHeader title={t('pages.reports.title')} intro={t('pages.reports.intro')} />
      {reports.data && reports.data.length > 0 ? <p className="mb-4 text-sm text-muted-foreground">{t('pages.reports.createHint')}</p> : null}
      {body}
      <AnalysisReportList />
    </>
  );
}

/** The signed-in person's research and dataset reports (private, frozen). */
function AnalysisReportList() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated);
  const reports = useAnalysisReports(signedIn);
  if (!signedIn || adapterKind !== 'http') return null;
  let body;
  if (reports.isPending) body = <StatePanel kind="loading" skeleton="lines" />;
  else if (reports.isError) body = <StatePanel kind="error" detail={reports.error.message} onRetry={() => void reports.refetch()} />;
  else if (reports.data.length === 0) body = <p className="text-sm text-muted-foreground">{t('reportsAi.none')}</p>;
  else {
    body = (
      <ul className="flex flex-col gap-3">
        {reports.data.map((r) => (
          <li key={r.id}>
            <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex min-w-0 flex-col gap-1">
                <Link to={to(`/reports/analysis/${r.id}`)} className="font-semibold text-primary underline underline-offset-2" dir="auto">{r.title}</Link>
                <p className="text-xs text-muted-foreground">{formatDateTime(r.created_at, language)}</p>
              </div>
              <Badge variant="muted">{r.kind === 'dataset' ? t('reportsAi.kindDataset') : t('reportsAi.kindResearch')}</Badge>
            </Card>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <section className="mt-10 flex flex-col gap-3" data-testid="analysis-reports">
      <h2 className="text-lg font-semibold">{t('reportsAi.listTitle')}</h2>
      <p className="text-sm text-muted-foreground">{t('reportsAi.listIntro')}</p>
      {body}
    </section>
  );
}

function FrozenObservations({ content }: { content: ReportContent }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <div className="flex flex-col gap-4">
      {content.series.map((s, n) => (
        <Card key={n} className="p-4 break-inside-avoid">
          <p className="font-semibold">{language === 'ar' ? s.indicator.name_ar : s.indicator.name_en}</p>
          <p className="text-xs text-muted-foreground">
            {language === 'ar' ? s.indicator.definition_ar : s.indicator.definition_en}
          </p>
          <p className="mt-1 text-xs">
            <span className="font-semibold">{t('table.limitation')}: </span>
            {language === 'ar' ? s.indicator.limitation_ar : s.indicator.limitation_en}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {language === 'ar' ? s.area.name_ar : s.area.name_en} · {s.frequency} · {language === 'ar' ? s.unit.label_ar : s.unit.label_en}
            {[s.commodity?.code, s.partner?.code, s.flow].filter(Boolean).map((x) => ` · ${x}`)}
            {' · '}{t('analysis.version')} <span dir="ltr">{s.dataset_version.label}</span>
          </p>
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-1 text-start font-medium">{t('table.period')}</th>
                <th scope="col" className="py-1 text-end font-medium">{t('table.value')}</th>
                <th scope="col" className="py-1 ps-3 text-start font-medium">{t('table.sourceRow')}</th>
              </tr>
            </thead>
            <tbody>
              {s.observations.map((o) => (
                <tr key={o.period_start} className="border-b border-border last:border-0">
                  <td className="py-1">{formatPeriod(o.period_start, o.period_end, language)}</td>
                  <td className="py-1 text-end tabular-nums" dir="ltr">
                    {o.value === null ? <span className="italic text-muted-foreground">{t('states.missingValue')}</span> : formatDecimal(o.value, language, 4)}
                  </td>
                  <td className="py-1 ps-3 font-mono text-xs break-all text-muted-foreground" dir="ltr">{o.source_row}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ))}
    </div>
  );
}

/** Print-friendly frozen report. Everything shown comes from the stored snapshot. */
export function ReportPage() {
  const { t } = useTranslation();
  const { reportId = '' } = useParams();
  const to = usePreservedSearch();
  const report = useReport(reportId);
  const visibility = useSetReportVisibility(reportId);
  const language = useAppLanguage();
  useDocumentTitle(report.data?.content.title ?? t('pages.reports.title'));

  if (adapterKind !== 'http') {
    return <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>;
  }
  if (report.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (report.isError) {
    return (
      <>
        <PageHeader title={t('pages.reports.title')} />
        <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('pages.reports.notFound')}</p></StatePanel>
      </>
    );
  }
  const r = report.data;
  const c = r.content;
  const section = sectionTitle(c.section);

  return (
    <article className="flex flex-col gap-8" data-testid="report" data-mode={c.data_mode}>
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link to={to('/reports')} className="text-sm text-primary underline underline-offset-2">{t('pages.reports.title')}</Link>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer aria-hidden="true" />{t('pages.reports.print')}
          </Button>
          <a href={reportExportUrl(r.id)} download className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="report-export">
            <Download aria-hidden="true" />{t('pages.reports.download')}
          </a>
          <a href={platformReportExportUrl(r.id, 'pdf', language)} download className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="report-export-pdf">
            <Download aria-hidden="true" />{t('reportsAi.download.pdf')}
          </a>
          <a href={platformReportExportUrl(r.id, 'xlsx', language)} download className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="report-export-xlsx">
            <Download aria-hidden="true" />{t('reportsAi.download.xlsx')}
          </a>
          {r.owned ? (
            <Button variant="ghost" size="sm" disabled={visibility.isPending}
              onClick={() => visibility.mutate(r.visibility === 'published' ? 'private' : 'published', { onSuccess: () => void report.refetch() })}>
              {r.visibility === 'published' ? t('pages.reports.makePrivate') : t('pages.reports.makePublic')}
            </Button>
          ) : null}
        </div>
      </div>

      <header className="flex flex-col gap-3 border-b-2 border-sand/50 pb-5">
        <p className="rounded-md border border-synthetic-border bg-synthetic px-3 py-2 text-sm font-semibold text-synthetic-foreground data-[mode=verified_source]:border-verified-border data-[mode=verified_source]:bg-verified data-[mode=verified_source]:text-verified-foreground"
          data-mode={c.data_mode} data-testid="report-label">
          {c.label}
        </p>
        <h1 className="flex items-center gap-2 text-2xl font-semibold sm:text-3xl">
          <FileText aria-hidden="true" className="size-6 text-accent print:hidden" />{c.title}
        </h1>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Snowflake aria-hidden="true" className="size-4" />{t('pages.reports.frozenNote')}
        </p>
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          <dt className="text-muted-foreground">{t('pages.reports.section')}</dt>
          <dd>{section ? t(section) : c.section}</dd>
          <dt className="text-muted-foreground">{t('table.dataMode')}</dt>
          <dd><DataModeBadge mode={c.data_mode} /></dd>
          <dt className="text-muted-foreground">{t('pages.reports.generated', { date: '' })}</dt>
          <dd dir="ltr" className="text-start">{c.generated_at.slice(0, 19).replace('T', ' ')} UTC</dd>
          <dt className="text-muted-foreground">{t('pages.reports.filters')}</dt>
          <dd data-testid="report-filters"><KeyValues values={c.filters} empty={t('pages.reports.noFilters')} /></dd>
          <dt className="text-muted-foreground">{t('pages.reports.assumptions')}</dt>
          <dd data-testid="report-assumptions"><KeyValues values={c.assumptions} empty="—" /></dd>
          <dt className="text-muted-foreground">{t('pages.reports.sources')}</dt>
          <dd data-testid="report-sources">
            {c.sources.map((s) => (
              <span key={s.id} className="block">{s.source.dataset_title} · {t('analysis.version')} <span dir="ltr">{s.label}</span></span>
            ))}
          </dd>
        </dl>
      </header>

      <section aria-labelledby="report-calcs" className="flex flex-col gap-4">
        <h2 id="report-calcs" className="text-xl font-semibold">{t('pages.reports.calculations')}</h2>
        {c.calculations.length === 0 ? <p className="text-sm text-muted-foreground">{t('analysis.none')}</p> : (
          <div className="grid gap-4 xl:grid-cols-2 print:block print:space-y-4">
            {c.calculations.map((calc) => <div key={calc.id} className="break-inside-avoid"><CalculationCard calc={calc} /></div>)}
          </div>
        )}
      </section>

      <section aria-labelledby="report-obs" className="flex flex-col gap-4">
        <h2 id="report-obs" className="text-xl font-semibold">{t('pages.reports.observations')}</h2>
        <FrozenObservations content={c} />
      </section>

      {c.review_cards.length > 0 ? (
        <section aria-labelledby="report-cards" className="flex flex-col gap-4">
          <h2 id="report-cards" className="text-xl font-semibold">{t('pages.reports.cards')}</h2>
          <div className="grid gap-4 xl:grid-cols-2 print:block print:space-y-4">
            {c.review_cards.map((card) => <div key={card.id} className="break-inside-avoid"><ReviewCardView card={card} withReviews={false} /></div>)}
          </div>
        </section>
      ) : null}

      <p className="border-t border-border pt-4 text-xs text-muted-foreground">{c.label} · {t('pages.reports.frozenNote')}</p>
    </article>
  );
}
