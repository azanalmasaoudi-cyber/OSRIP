import { Download, ExternalLink, FileText, Save } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { reportExportUrl, useCreateReport } from '@/api/analysis';
import { platformReportExportUrl } from '@/api/analysisReports';
import type { ReportBlock } from '@/api/assistant';
import { hasPermission, useMe } from '@/api/auth';
import { ForecastChart } from '@/components/forecast/ForecastChart';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { ChartOnRequest } from '@/components/ui/chart-on-request';
import { csvField, download, safeCell } from '@/lib/exportResults';
import { formatDate, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/*
 * A report Al Mulhim built for a request ("Create a report on water in Muscat for 2024"): the
 * backend's build_report tool reads it exactly as a saved platform report is read (published
 * observations, the section's calculations, its rule-based review cards and their sources), so
 * every figure here comes from the database, not from the model. It is shown in the reply with
 * headings, tables, charts, findings to review and, collapsed, its sources. Anyone can download
 * its tables as CSV; a person allowed to create reports saves it as a frozen platform report
 * (POST /reports, the same section and filters), which then exports as PDF, Excel and CSV.
 */

const SECTOR_KEY = {
  electricity: 'nav.electricity', water: 'nav.water', food_security: 'nav.foodSecurity', trade: 'nav.trade',
} as const;

type Lang = 'en' | 'ar';
const pick = (v: { en: string; ar: string } | null | undefined, language: Lang, fallback = ''): string => (v ? v[language] || v.en : fallback);

/** The report's tables as one CSV file (formula-safe text, numbers kept as numbers). */
function reportCsv(report: ReportBlock, language: Lang, labels: Record<string, string>): string {
  const lines: string[] = [];
  const line = (cells: (string | null | undefined)[], numeric: number[] = []) =>
    lines.push(cells.map((c, i) => csvField(numeric.includes(i) ? (c ?? '') : safeCell(c ?? ''))).join(','));
  line([`# OSRIP · ${pick(report.title, language)}`]);
  line([`# ${labels.built}`]);
  line([`# data_mode=${report.data_mode ?? ''}; section=${report.section}; ${Object.entries(report.filters).map(([k, v]) => `${k}=${v}`).join('; ')}`]);
  lines.push('');
  line(['indicator', 'area', 'unit', 'period_start', 'period_end', 'value', 'quality_status', 'dataset_version']);
  for (const s of report.series) {
    for (const r of s.rows) {
      line([pick(s.indicator_name, language, s.indicator), pick(s.area_name, language, s.area), pick(s.unit_label, language, s.unit),
        r.period_start, r.period_end, r.value, r.quality_status ?? '', s.dataset_version ?? ''], [5]);
    }
  }
  if (report.calculations.length) {
    lines.push('');
    line(['calculation', 'status', 'value', 'unit']);
    for (const c of report.calculations) line([pick(c.title, language), c.status ?? '', c.value ?? '', pick(c.unit_label, language, c.unit ?? '')], [2]);
  }
  if (report.review.length) {
    lines.push('');
    line(['rule', 'status', 'observation', 'next_steps']);
    for (const r of report.review) line([r.rule_code ?? '', r.status ?? '', pick(r.observation, language), pick(r.next_steps, language)]);
  }
  // A byte-order mark first, so spreadsheet programs read Arabic text as UTF-8.
  return `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`;
}

/** Save as a frozen platform report (with the permission), then its PDF, Excel and CSV. */
function ReportActions({ report }: { report: ReportBlock }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const me = useMe();
  const create = useCreateReport();
  const csv = () => download(`osrip-report-${report.section}-${report.evidence_id.toLowerCase()}-${language}.csv`,
    reportCsv(report, language, { built: t('chat.report.built') }), 'text/csv;charset=utf-8');
  const canSave = hasPermission(me.data, 'report.create') && (report.data_mode === 'verified_source' || report.data_mode === 'synthetic');
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3" data-testid="reply-report-actions">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={csv} data-testid="reply-report-csv">
          <Download aria-hidden="true" />{t('chat.report.downloadCsv')}
        </Button>
        {canSave && !create.isSuccess ? (
          <Button type="button" size="sm" disabled={create.isPending} data-testid="reply-report-save"
            onClick={() => create.mutate({
              title: pick(report.title, language).slice(0, 200), data_mode: report.data_mode === 'synthetic' ? 'synthetic' : 'verified_source',
              section: report.section, filters: report.filters, stock_assumption: 'assumed_zero', visibility: 'private',
            })}>
            <Save aria-hidden="true" />{create.isPending ? t('chat.report.saving') : t('chat.report.save')}
          </Button>
        ) : null}
      </div>
      {create.isSuccess ? (
        <div className="flex flex-wrap items-center gap-2 text-sm" role="status" data-testid="reply-report-saved" data-report={create.data.id}>
          <span>{t('chat.report.saved')}</span>
          <Link to={to(`/reports/${create.data.id}`)} className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="reply-report-open">
            <ExternalLink aria-hidden="true" />{t('chat.report.open')}
          </Link>
          <a href={platformReportExportUrl(create.data.id, 'pdf', language)} download className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="reply-report-pdf">{t('chat.report.pdf')}</a>
          <a href={platformReportExportUrl(create.data.id, 'xlsx', language)} download className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="reply-report-xlsx">{t('chat.report.xlsx')}</a>
          <a href={reportExportUrl(create.data.id)} download className={buttonVariants({ size: 'sm', variant: 'outline' })} data-testid="reply-report-export-csv">{t('chat.report.csv')}</a>
        </div>
      ) : null}
      {create.isError ? <p role="alert" className="text-sm text-destructive">{create.error.message}</p> : null}
      {!canSave && !me.isPending ? (
        <p className="text-xs text-muted-foreground" data-testid="reply-report-save-note">
          {me.data?.authenticated ? t('chat.report.noPermission') : (
            <>{t('chat.report.signIn')} <Link to={to('/sign-in')} className="text-primary underline underline-offset-2">{t('chat.report.signInLink')}</Link></>
          )}
        </p>
      ) : null}
    </div>
  );
}

export function ReplyReport({ report }: { report: ReportBlock }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const f = report.filters;
  // The period asked for, or else the years the published rows cover.
  const years = report.series.flatMap((s) => s.rows.map((r) => r.period_start.slice(0, 4))).sort();
  const first = years[0] ?? '';
  const last = years.at(-1) ?? '';
  const span = first === last ? first : `${first}–${last}`;
  const period = f.period_from || f.period_to
    ? `${f.period_from ? formatDate(f.period_from, language) : '…'} – ${f.period_to ? formatDate(f.period_to, language) : '…'}`
    : t('chat.report.allPeriods', { span });
  const area = report.series.find((s) => s.area === f.area)?.area_name;
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border border-s-4 border-s-primary bg-card/70 p-3 sm:p-4"
      data-testid="reply-report" data-type={report.report_type} data-section={report.section} aria-labelledby={`report-${report.evidence_id}`}>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-lg bg-primary-soft text-brand"><FileText className="size-4" /></span>
          <Badge variant="outline">{t('chat.report.badge')}</Badge>
          <Badge variant="outline">{t(`chat.report.types.${report.report_type}`)}</Badge>
        </div>
        <h3 id={`report-${report.evidence_id}`} className="text-lg font-semibold" dir="auto" data-testid="reply-report-title">{pick(report.title, language)}</h3>
        <p className="text-xs text-muted-foreground">{t('chat.report.built')}</p>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm" data-testid="reply-report-scope">
          <dt className="font-medium text-muted-foreground">{t('chat.report.sector')}</dt><dd>{t(SECTOR_KEY[report.section])}</dd>
          <dt className="font-medium text-muted-foreground">{t('chat.report.area')}</dt><dd>{area ? pick(area, language) : (f.area ?? t('chat.report.allAreas'))}</dd>
          <dt className="font-medium text-muted-foreground">{t('chat.report.period')}</dt><dd>{period}</dd>
          {report.generated_at ? (<><dt className="font-medium text-muted-foreground">{t('chat.report.generated')}</dt><dd>{formatDate(report.generated_at, language)}</dd></>) : null}
        </dl>
      </header>

      <section aria-labelledby={`report-${report.evidence_id}-data`} className="flex flex-col gap-3">
        <h4 id={`report-${report.evidence_id}-data`} className="text-base font-semibold">{t('chat.report.dataHeading')}</h4>
        {report.series_total > report.series.length ? (
          <p className="text-xs text-muted-foreground" data-testid="reply-report-more">{t('chat.report.seriesShown', { shown: report.series.length, total: report.series_total })}</p>
        ) : null}
        {report.series.map((s, i) => {
          const name = pick(s.indicator_name, language, s.indicator);
          const unit = pick(s.unit_label, language, s.unit);
          const detail = [pick(s.area_name, language, s.area), s.commodity_name ? pick(s.commodity_name, language) : null, s.partner_name ? pick(s.partner_name, language) : null, s.flow].filter(Boolean).join(' · ');
          return (
            <div key={`${s.indicator}-${s.area}-${i}`} className="flex min-w-0 flex-col gap-2 rounded-xl border border-border p-3" data-testid="reply-report-series" data-indicator={s.indicator}>
              <p className="text-sm font-semibold" dir="auto">{name} <span className="font-normal text-muted-foreground">· {detail} · {unit}</span></p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[16rem] text-sm" data-testid="reply-report-table">
                  <caption className="sr-only">{`${name} (${unit})`}</caption>
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th scope="col" className="py-1 text-start font-medium">{t('chat.report.periodColumn')}</th>
                      <th scope="col" className="py-1 text-end font-medium">{t('chat.report.value', { unit })}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.rows.map((r) => (
                      <tr key={r.period_start} className="border-b border-border last:border-0" data-testid="reply-report-row">
                        <td className="py-1">{formatPeriod(r.period_start, r.period_end, language)}</td>
                        <td className="py-1 text-end tabular-nums" dir="ltr">{r.value === null ? t('chat.report.missing') : (formatDecimal(r.value, language, 2) ?? r.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {s.rows.filter((r) => r.value !== null).length > 1 ? (
                <ChartOnRequest label={name} testId="reply-report-chart-toggle" defaultOpen={i === 0}>
                  <ForecastChart history={s.rows} unit={unit} title={`${name} · ${pick(s.area_name, language, s.area)}`} />
                </ChartOnRequest>
              ) : null}
              {s.dataset_version ? <p className="text-xs text-muted-foreground">{t('chat.report.version', { version: s.dataset_version })}</p> : null}
            </div>
          );
        })}
      </section>

      {report.calculations.length ? (
        <section aria-labelledby={`report-${report.evidence_id}-calc`} className="flex flex-col gap-2" data-testid="reply-report-calculations">
          <h4 id={`report-${report.evidence_id}-calc`} className="text-base font-semibold">{t('chat.report.calculations')}</h4>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[18rem] text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th scope="col" className="py-1 text-start font-medium">{t('chat.report.calculation')}</th>
                  <th scope="col" className="py-1 text-end font-medium">{t('chat.report.valueColumn')}</th>
                </tr>
              </thead>
              <tbody>
                {report.calculations.map((c, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="py-1" dir="auto">{pick(c.title, language)}</td>
                    <td className="py-1 text-end tabular-nums">
                      {c.value == null ? <span className="text-muted-foreground">{t('chat.report.notDetermined')}</span>
                        : <><bdi dir="ltr">{formatDecimal(c.value, language, 2) ?? c.value}</bdi> {pick(c.unit_label, language, c.unit ?? '')}</>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">{t('chat.report.calcNote')}</p>
        </section>
      ) : null}

      {report.review.length ? (
        <section aria-labelledby={`report-${report.evidence_id}-review`} className="flex flex-col gap-2" data-testid="reply-report-review">
          <h4 id={`report-${report.evidence_id}-review`} className="text-base font-semibold">{t('chat.report.review')}</h4>
          <p className="text-xs text-muted-foreground">{t('chat.report.reviewNote')}</p>
          <ul className="flex list-disc flex-col gap-2 ps-5 text-sm">
            {report.review.map((r, i) => (
              <li key={`${r.rule_code}-${i}`} dir="auto">
                {pick(r.observation, language)}
                {r.next_steps ? <span className="block text-muted-foreground">{t('chat.report.nextStep', { text: pick(r.next_steps, language) })}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {report.sources.length ? (
        <details className="rounded-lg border border-border p-3 text-sm" data-testid="reply-report-sources">
          <summary className="cursor-pointer font-medium">{t('chat.report.sources', { count: report.sources.length })}</summary>
          <ul className="mt-2 flex list-disc flex-col gap-1 ps-5">
            {report.sources.map((s, i) => (
              <li key={i} dir="auto">{s.title}{s.publisher ? ` · ${s.publisher}` : ''}{s.version ? ` · ${t('chat.report.version', { version: s.version })}` : ''}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <ReportActions report={report} />
    </section>
  );
}
