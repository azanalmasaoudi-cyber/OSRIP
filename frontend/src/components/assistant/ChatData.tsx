import { CheckCircle2, Download, ExternalLink, FileSearch, Table2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { DataChartBlock, DataRow, DataTableBlock, ResearchFigure, ResearchSummaryBlock } from '@/api/assistant';
import { StudyBarChart, StudyLineChart } from '@/components/studies/StudyCharts';
import { useLabels } from '@/components/studies/StudyView';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { csvField, download, safeCell } from '@/lib/exportResults';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Tables, charts and the research summary of an answer, as the server built them from
 * published observations and from what research actually did. The model never writes these
 * figures: a table's rows and a chart's points are the same validated rows, in period order,
 * with a missing value shown as missing (never zero). A chart appears only for a question that
 * asked for one; its data are also given as a table for assistive technology.
 */

const safeUrl = (url: string | null | undefined) => (url && /^https?:\/\//.test(url) ? url : null);
const COLUMNS = ['period', 'indicator', 'value', 'unit', 'geography', 'source'] as const;
const STATUSES = ['approved', 'duplicate', 'conflict', 'pending', 'rejected', 'accepted'] as const;
type Status = (typeof STATUSES)[number];
const KINDS = ['monthly', 'quarterly', 'annual', 'year_to_date'] as const;
const isStatus = (value: string): value is Status => (STATUSES as readonly string[]).includes(value);
const isKind = (value: string): value is (typeof KINDS)[number] => (KINDS as readonly string[]).includes(value);

function name(value: { en?: string | null; ar?: string | null } | null | undefined, language: 'en' | 'ar', fallback: string) {
  return (language === 'ar' ? value?.ar : value?.en) || value?.en || fallback;
}

function periodLabel(row: DataRow, language: 'en' | 'ar', ytd: string) {
  const text = formatPeriod(row.period_start, row.period_end, language);
  return row.period_kind === 'year_to_date' ? `${text} · ${ytd}` : text;
}

function tableCsv(rows: DataRow[], language: 'en' | 'ar', header: string[], ytd: string): string {
  const lines = [header.map((h) => csvField(safeCell(h))).join(',')];
  for (const r of rows) {
    lines.push([
      periodLabel(r, language, ytd),
      name(r.indicator_name, language, r.indicator_code),
      r.value ?? '',
      name(r.unit_label, language, r.unit),
      name(r.area_name, language, r.area),
      `${r.source.title}${r.source.url ? ` (${r.source.url})` : ''}`,
    ].map((cell, i) => csvField(i === 2 ? cell : safeCell(cell))).join(','));
  }
  // A byte-order mark first, so spreadsheet programs read Arabic text as UTF-8.
  return `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`;
}

export function ChatDataTables({ blocks, messageId }: { blocks: DataTableBlock[]; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const header = COLUMNS.map((k) => t(`chat.table.col.${k}`));
  const ytd = t('chat.table.ytd');
  return (
    <>
      {blocks.flatMap((block) => block.tables.map((table, i) => (
        <figure key={`${block.id}-${i}`} className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-3"
          data-testid="chat-data-table" data-table={block.id} data-rows={table.rows.length} data-message={messageId}>
          <figcaption className="flex flex-wrap items-center gap-2 text-xs font-semibold">
            <Table2 aria-hidden="true" className="size-3.5" />
            {t('chat.table.title')}
            <span className="font-normal text-muted-foreground">({name({ en: table.unit.label_en, ar: table.unit.label_ar }, language, table.unit.code)})</span>
          </figcaption>
          <div className="max-w-full overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-start text-muted-foreground">
                  {COLUMNS.map((k, i) => (
                    <th key={k} scope="col" className="px-2 py-1.5 text-start font-medium">{header[i]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r) => (
                  <tr key={r.evidence_id} className="border-b border-border/60 last:border-0" data-testid="chat-data-row"
                    data-evidence={r.evidence_id} data-value={r.value ?? ''} data-period={r.period_start}>
                    <td className="px-2 py-1.5 whitespace-nowrap tabular-nums" dir="auto">{periodLabel(r, language, ytd)}</td>
                    <td className="px-2 py-1.5"><bdi>{name(r.indicator_name, language, r.indicator_code)}</bdi></td>
                    <td className="px-2 py-1.5 tabular-nums" dir="ltr">
                      {r.value == null
                        ? <span className="text-muted-foreground"><span aria-hidden="true">—</span><span className="sr-only">{t('studies.noValue')}</span></span>
                        : `${r.value_operator ?? ''}${formatDecimal(r.value, language, 4) ?? r.value}`}
                    </td>
                    <td className="px-2 py-1.5"><bdi>{name(r.unit_label, language, r.unit)}</bdi></td>
                    <td className="px-2 py-1.5"><bdi>{name(r.area_name, language, r.area)}</bdi></td>
                    <td className="px-2 py-1.5">
                      {safeUrl(r.source.url) ? (
                        <a href={safeUrl(r.source.url)!} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                          <bdi>{r.source.title}</bdi><ExternalLink aria-hidden="true" className="size-3" />
                        </a>
                      ) : <bdi>{r.source.title}</bdi>}
                      {r.revision_status ? <span className="ms-1 text-muted-foreground">({r.revision_status})</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button type="button" variant="ghost" size="sm" className="w-fit" data-testid="chat-table-csv"
            onClick={() => download(`osrip-${block.id.toLowerCase()}-${messageId}-${language}.csv`, tableCsv(table.rows, language, header, ytd), 'text/csv;charset=utf-8')}>
            <Download aria-hidden="true" />{t('chat.table.csv')}
          </Button>
        </figure>
      )))}
    </>
  );
}

export function ChatDataCharts({ charts, messageId }: { charts: DataChartBlock[]; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useLabels(language);
  return (
    <>
      {charts.map((c, i) => {
        const unit = c.chart.unit ? (language === 'ar' ? c.chart.unit.label_ar : c.chart.unit.label_en) : '—';
        const rows = c.table.rows;
        const periods = rows.map((r) => r[c.chart.x] ?? '').filter(Boolean);
        return (
          <figure key={i} className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="chat-data-chart"
            data-chart={c.chart.type} data-points={c.points} data-message={messageId} data-table={c.table_id ?? ''}>
            {c.chart.type === 'line'
              ? <StudyLineChart chart={c.chart} rows={rows} labelFor={labels.text} />
              : <StudyBarChart chart={c.chart} rows={rows} labelFor={labels.text} />}
            <figcaption className="text-xs text-muted-foreground" data-testid="chat-chart-meta">
              {t('chat.chart.meta', {
                unit,
                periods: periods.length ? `${periods[0]} – ${periods[periods.length - 1]}` : '—',
                kind: isKind(c.period_kind) ? t(`chat.table.kind.${c.period_kind}`) : c.period_kind,
                sources: c.sources.join(language === 'ar' ? '، ' : ', '),
              })}
            </figcaption>
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">{t('chat.chart.data')}</summary>
              <table className="mt-1 text-xs" data-testid="chat-chart-data">
                <thead><tr>{c.table.columns.map((col) => <th key={col.key} scope="col" className="px-2 py-1 text-start font-medium">{col.label[language]}</th>)}</tr></thead>
                <tbody>
                  {rows.map((r, j) => (
                    <tr key={j}>{c.table.columns.map((col) => (
                      <td key={col.key} className="px-2 py-1 tabular-nums" dir={col.kind === 'number' ? 'ltr' : 'auto'}>
                        {col.kind === 'number' ? (r[col.key] == null ? '—' : formatDecimal(r[col.key] ?? null, language, 4)) : labels.text(r, col.key)}
                      </td>
                    ))}</tr>
                  ))}
                </tbody>
              </table>
            </details>
          </figure>
        );
      })}
    </>
  );
}

function FigureLine({ f }: { f: ResearchFigure }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const url = safeUrl(f.source_url);
  return (
    <li className="flex flex-col gap-0.5" data-testid="research-figure" data-status={f.status} data-observation={f.observation_id ?? ''}>
      <span className="flex flex-wrap items-center gap-1.5">
        <Badge variant={f.saved ? 'accent' : 'sand'}>{isStatus(f.status) ? t(`chat.research.status.${f.status}`) : f.status}</Badge>
        <span dir="auto">{f.indicator_code} · {f.area_code} · {f.period}</span>
        {f.value ? <span className="tabular-nums" dir="ltr">{formatDecimal(f.value, language, 4)} {f.unit}</span> : null}
      </span>
      {f.saved && f.observation_id ? <span className="text-muted-foreground">{t('chat.research.record')}: <span className="font-mono" dir="ltr">{f.observation_id}</span></span> : null}
      {!f.saved && f.reasons.length ? <span className="text-muted-foreground" dir="auto">{f.reasons.join(' · ')}</span> : null}
      {url ? (
        <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex w-fit items-center gap-1 text-primary underline underline-offset-2">
          <bdi>{f.source_title || f.publisher || url}</bdi><ExternalLink aria-hidden="true" className="size-3" />
        </a>
      ) : null}
    </li>
  );
}

export function ResearchSummary({ summary }: { summary: ResearchSummaryBlock }) {
  const { t } = useTranslation();
  const saved = summary.saved.length;
  return (
    <details className="text-xs" data-testid="research-summary" data-saved={saved} data-read={summary.sources_read.length} open={summary.submitted > 0}>
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
        <FileSearch aria-hidden="true" className="me-1 inline size-3.5" />
        <span className="font-semibold">{t('chat.research.title')}</span>
        <span className="ms-1">· {t('chat.research.read', { count: summary.sources_read.length })}</span>
        {summary.submitted ? <span className="ms-1">· {t('chat.research.savedCount', { count: saved })}</span> : null}
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        {summary.sources_read.length ? (
          <ul className="flex flex-col gap-1">
            {summary.sources_read.map((s) => (
              <li key={s.evidence_id} data-testid="research-source">
                <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                  <bdi>{s.title || s.url}</bdi><ExternalLink aria-hidden="true" className="size-3" />
                </a>
                <span className="ms-1 text-muted-foreground">
                  {[s.publisher, s.published ? t('chat.research.published', { date: s.published }) : t('chat.research.noPublished'),
                    s.retrieved_at ? t(s.cached ? 'chat.research.readEarlier' : 'chat.research.readAt', { date: s.retrieved_at.slice(0, 10) }) : null]
                    .filter(Boolean).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {summary.submitted ? (
          <>
            <p className="flex items-center gap-1 font-medium">
              <CheckCircle2 aria-hidden="true" className="size-3.5" />
              {STATUSES.filter((k) => summary.counts[k])
                .map((k) => `${t(`chat.research.status.${k}`)}: ${String(summary.counts[k] ?? 0)}`).join(' · ')}
            </p>
            {summary.latest_saved_period ? <p>{t('chat.research.latest', { period: summary.latest_saved_period })}</p> : null}
            <ul className="flex flex-col gap-2">
              {[...summary.saved, ...summary.not_saved].map((f, i) => <FigureLine key={f.candidate_id ?? i} f={f} />)}
            </ul>
            <p className="text-muted-foreground">{t('chat.research.note')}</p>
          </>
        ) : null}
      </div>
    </details>
  );
}
