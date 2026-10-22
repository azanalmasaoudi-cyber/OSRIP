import { Download, ExternalLink, FileText, Volume2 } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { DataModeBadge } from '@/components/common/DataModeBadge';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { StudyBarChart, StudyHeatmap, StudyLineChart } from '@/components/studies/StudyCharts';
import { StudyTable, useLabels } from '@/components/studies/StudyView';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, tabPanelProps } from '@/components/workspace/Tabs';
import { download, modelToHtml, tableToCsv, type ReportLabels } from '@/lib/exportResults';
import { formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

import { periodRange, type ResultRecommendation, type ResultSource, type ResultTable, type ResultsModel } from './model';

/**
 * The results of the current analysis or assistant study, in five tabs. Tables and charts come
 * from the same validated rows; every chart says its unit, periods and sources; recommendations
 * are shown as decision support with their evidence, constraints and an unknown cost unless a
 * source states one. Content follows the interface language, except generated sentences of an
 * assistant study, which stay in the language the question was asked in.
 */

const TABS = ['summary', 'tables', 'charts', 'sources', 'recommendations', 'conclusion'] as const;
type Tab = (typeof TABS)[number];

export function ResultsPanel({ model, onListen, listenLabel, listening = false, transcript = null }: {
  model: ResultsModel;
  onListen?: () => void;
  listenLabel?: string;
  listening?: boolean;
  /** The exact words the voice reads (shown while and after it plays). */
  transcript?: string | null;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [tab, setTab] = useState<Tab>('summary');
  const idBase = `results-${model.kind}`;
  const chartCount = model.tables.reduce((n, x) => n + x.charts.length, 0);
  const counts: Record<Tab, number | null> = {
    summary: null, tables: model.tables.length, charts: chartCount, sources: model.sources.length, recommendations: model.recommendations.length,
    conclusion: null,
  };
  const reportLabels: ReportLabels = {
    summary: t('results.tabs.summary'), tables: t('results.tabs.tables'), sources: t('results.tabs.sources'),
    recommendations: t('results.tabs.recommendations'), dataGaps: t('balance.dataGaps'), decisionSupport: t('balance.decisionSupport'),
    charts: t('results.noCharts'),
    conclusion: {
      title: t('results.conclusion.title'), findings: t('results.conclusion.findings'), limits: t('results.conclusion.limits'),
      immediate: t('results.conclusion.immediate'), mediumTerm: t('results.conclusion.mediumTerm'), next: t('results.conclusion.next'),
      none: t('results.conclusion.none'),
    },
    columns: {
      problem: t('balance.columns.problem'), evidence: t('balance.columns.evidence'), action: t('balance.columns.action'),
      quantity: t('balance.columns.quantity'), horizon: t('balance.columns.horizon'), constraints: t('balance.columns.constraints'),
      cost: t('balance.columns.cost'), outcome: t('balance.columns.outcome'), priority: t('balance.columns.priority'), kpi: t('balance.columns.kpi'),
    },
  };
  return (
    <section className="flex min-w-0 flex-col gap-4" data-testid="results-panel" data-kind={model.kind} data-status={model.status.code}
      aria-labelledby={`${idBase}-heading`} aria-busy={model.running}>
      <header className="flex flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={model.status.tone} data-testid="results-status">{model.status.label}</Badge>
          {model.dataMode === 'synthetic' || model.dataMode === 'verified_source' ? <DataModeBadge mode={model.dataMode} /> : null}
        </p>
        <h2 id={`${idBase}-heading`} className="text-lg font-semibold leading-snug" dir="auto">{model.title}</h2>
        {model.running ? <p className="rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-sm" role="status">{t('results.provisional')}</p> : null}
        <div className="flex flex-wrap gap-2">
          {model.downloads.csv ? (
            <a href={model.downloads.csv} download className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium hover:bg-muted"
              data-testid="results-csv"><Download aria-hidden="true" className="size-4" />{t('balance.downloadCsv')}</a>
          ) : null}
          {model.downloads.report ? (
            <a href={model.downloads.report} download className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium hover:bg-muted"
              data-testid="results-report"><FileText aria-hidden="true" className="size-4" />{t('balance.downloadReport')}</a>
          ) : (
            <Button type="button" variant="outline" size="sm" disabled={model.running} data-testid="results-report"
              onClick={() => download(`osrip-results-${model.id.slice(0, 8)}-${language}.html`, modelToHtml(model, language, reportLabels), 'text/html;charset=utf-8')}>
              <FileText aria-hidden="true" />{t('results.downloadReport')}
            </Button>
          )}
          {onListen ? (
            <Button type="button" variant="outline" size="sm" onClick={onListen} disabled={listening} data-testid="results-listen">
              <Volume2 aria-hidden="true" />{listenLabel ?? t('balance.listen')}
            </Button>
          ) : null}
        </div>
        {transcript ? (
          <p className="rounded-md bg-muted/60 p-2 text-xs" dir="auto" data-testid="results-transcript">
            <span className="font-semibold">{t('voicePanel.transcript')}: </span>{transcript}
          </p>
        ) : null}
      </header>

      <Tabs tabs={TABS.map((id) => ({ id, label: t(`results.tabs.${id}`), badge: counts[id] ? String(counts[id]) : null }))}
        value={tab} onChange={setTab} idBase={idBase} label={t('results.heading')} className="overflow-x-auto" />

      <div {...tabPanelProps(idBase, 'summary', tab === 'summary')} data-testid="results-summary" className="flex flex-col gap-4 focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'summary' ? <SummaryTab model={model} /> : null}
      </div>
      <div {...tabPanelProps(idBase, 'tables', tab === 'tables')} data-testid="results-tables" className="flex flex-col gap-4 focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'tables' ? (model.tables.length ? model.tables.map((x) => <TableBlock key={x.id} table={x} />) : <Empty text={t('results.noTables')} />) : null}
      </div>
      <div {...tabPanelProps(idBase, 'charts', tab === 'charts')} data-testid="results-charts" className="flex flex-col gap-4 focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'charts' ? (chartCount ? model.tables.flatMap((x) => x.charts.map((_, i) => (
          <ChartBlock key={`${x.id}-${i}`} table={x} index={i} sources={model.sources} />
        ))) : <Empty text={t('results.noCharts')} />) : null}
      </div>
      <div {...tabPanelProps(idBase, 'sources', tab === 'sources')} data-testid="results-sources" className="focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'sources' ? (model.sources.length ? <SourcesList sources={model.sources} /> : <Empty text={t('results.noSources')} />) : null}
      </div>
      <div {...tabPanelProps(idBase, 'recommendations', tab === 'recommendations')} data-testid="results-recommendations" className="flex flex-col gap-3 focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'recommendations' ? <RecommendationsTab model={model} /> : null}
      </div>
      <div {...tabPanelProps(idBase, 'conclusion', tab === 'conclusion')} data-testid="results-conclusion" className="flex flex-col gap-3 focus-visible:outline-2 focus-visible:outline-ring">
        {tab === 'conclusion' ? <ConclusionTab model={model} /> : null}
      </div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground" role="status">{text}</p>;
}

function Appear({ children, className }: { children: ReactNode; className?: string }) {
  // A subtle fade; the global reduced-motion setting turns transitions off (MotionConfig).
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: 'easeOut' }} className={className}>
      {children}
    </motion.div>
  );
}

function SummaryTab({ model }: { model: ResultsModel }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <Appear className="flex flex-col gap-4">
      {model.summary.length ? (
        <ul className="flex flex-col gap-1.5 text-sm" lang={model.textLanguage} dir={model.textLanguage === 'ar' ? 'rtl' : 'ltr'} data-testid="results-summary-text">
          {model.summary.map((s, i) => <li key={i} className="rounded-md bg-muted/40 px-3 py-2">{s}</li>)}
        </ul>
      ) : <Empty text={model.running ? t('workspace.study.findingsPending') : t('workspace.study.noFindings')} />}
      {model.cards.length ? (
        <ul className="grid gap-3 sm:grid-cols-2" data-testid="results-cards">
          {model.cards.map((c) => (
            <li key={c.id} className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-3" data-testid="results-card" data-status={c.status.code}>
              <p className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-mono text-muted-foreground" dir="ltr">{c.id}</span>
                <Badge variant={c.status.tone}>{c.status.label}</Badge>
                {c.period ? <span className="text-muted-foreground" dir="ltr">{c.period}</span> : null}
              </p>
              <p className="font-medium" dir="auto">{c.title}</p>
              {c.gap !== null ? (
                <p className="text-lg font-semibold tabular-nums">
                  <span dir="ltr">{formatDecimal(c.gap, language, 3) ?? c.gap}</span>
                  {c.gapUnit ? <span className="ms-1 text-sm font-normal text-muted-foreground">{c.gapUnit}</span> : null}
                </p>
              ) : null}
              <p className="text-xs text-muted-foreground" dir="auto">{c.reason}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {model.dataGaps.length ? (
        <div data-testid="results-gaps">
          <h3 className="text-sm font-semibold">{t('balance.dataGaps')}</h3>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {model.dataGaps.map((g, i) => (
              <li key={i} className="rounded-md border border-dashed border-border-strong/60 px-3 py-2">
                <span className="font-medium" dir="auto">{g.missing}</span>
                {g.blocks ? <span className="text-muted-foreground"> — {t('balance.blocks')}: <bdi>{g.blocks}</bdi></span> : null}
                {g.where ? <span className="block text-xs text-muted-foreground">{t('balance.where')}: <bdi>{g.where}</bdi></span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {model.scenario && model.scenario.status !== 'ok' && model.scenario.text ? (
        <p className="text-sm text-muted-foreground" data-testid="results-scenario-note"><span className="font-medium text-foreground">{t('balance.scenarioResult')}:</span> {model.scenario.text}</p>
      ) : null}
      {model.forecast ? (
        <p className="text-sm text-muted-foreground" data-testid="results-forecast"><span className="font-medium text-foreground">{t('balance.forecast')}:</span> {model.forecast}</p>
      ) : null}
      {model.method.length || model.assumptions.length || model.limitations.length ? (
        <details className="rounded-md border border-border p-3 text-sm">
          <summary className="cursor-pointer font-medium">{t('balance.method')}</summary>
          <div className="mt-2 flex flex-col gap-2 text-muted-foreground">
            {model.method.map((m, i) => <p key={i}>{m}</p>)}
            {model.assumptions.length ? <p><span className="font-medium text-foreground">{t('balance.assumptions')}:</span> {model.assumptions.join(' ')}</p> : null}
            {model.limitations.length ? (
              <ul className="list-disc ps-5">{model.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
            ) : null}
          </div>
        </details>
      ) : null}
    </Appear>
  );
}

function NatureBadge({ nature }: { nature: ResultTable['nature'] | 'recommendation' }) {
  const { t } = useTranslation();
  return <Badge variant={nature === 'scenario' ? 'sand' : nature === 'calculated' ? 'outline' : 'muted'} data-testid="nature">{t(`results.nature.${nature}`)}</Badge>;
}

function TableBlock({ table }: { table: ResultTable }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const detailLabel: Record<string, string> = {
    reason: t('balance.reason'), interpretation: t('balance.interpretation'), constraints: t('balance.constraints'),
    notes: t('balance.notes'), method: t('balance.method'), assumptions: t('balance.assumptions'),
  };
  return (
    <Appear>
      <article className={cn('flex flex-col gap-3 rounded-lg border bg-card p-4', table.provisional ? 'border-dashed border-sand' : 'border-border')}
        data-testid="results-table" data-table={table.id} data-nature={table.nature}>
        <header className="flex flex-col gap-1">
          <p className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="font-mono text-muted-foreground" dir="ltr">{table.id}</span>
            {table.status ? <Badge variant={table.status.tone} data-testid="results-table-status">{table.status.label}</Badge> : null}
            <NatureBadge nature={table.nature} />
            {table.provisional ? <Badge variant="sand">{t('workspace.dataset.provisional')}</Badge> : null}
          </p>
          <h3 className="font-semibold" dir="auto">{table.title}</h3>
          {table.subtitle ? <p className="text-sm text-muted-foreground" dir="auto">{table.subtitle}</p> : null}
        </header>
        {table.rows.length ? (
          <StudyTable columns={table.columns} rows={table.rows} language={language} rowIds={table.rowIds} caption={table.title} />
        ) : <Empty text={t('results.noTables')} />}
        {table.details.length ? (
          <dl className="grid gap-1 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-3">
            {table.details.map((d, i) => (
              <div key={i} className="contents">
                <dt className="font-medium">{detailLabel[d.label] ?? d.label}</dt>
                <dd className="text-muted-foreground" dir="auto">{d.text}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {table.rows.length ? (
          <Button type="button" variant="ghost" size="sm" className="w-fit" data-testid="results-table-csv"
            onClick={() => download(`osrip-${table.id.toLowerCase()}-${language}.csv`, tableToCsv(table, language, [table.title]), 'text/csv;charset=utf-8')}>
            <Download aria-hidden="true" />{t('results.downloadTable')}
          </Button>
        ) : null}
      </article>
    </Appear>
  );
}

function ChartBlock({ table, index, sources }: { table: ResultTable; index: number; sources: ResultSource[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useLabels(language);
  const chart = table.charts[index];
  if (!chart) return null;
  const unit = chart.unit ? (language === 'ar' ? chart.unit.label_ar : chart.unit.label_en) : '—';
  const publishers = [...new Set(table.sourceIds.map((id) => sources.find((s) => s.id === id)).filter(Boolean)
    .map((s) => s?.publisher || s?.title || ''))].filter(Boolean);
  const sourceText = publishers.length ? publishers.join(language === 'ar' ? '، ' : ', ') : table.sourceIds.join(', ') || '—';
  return (
    <Appear>
      <figure className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-4" data-testid="results-chart" data-chart={chart.type} data-table={table.id}>
        {chart.type === 'line' ? <StudyLineChart chart={chart} rows={table.rows} labelFor={labels.text} />
          : chart.type === 'bar' ? <StudyBarChart chart={chart} rows={table.rows} labelFor={labels.text} />
            : <StudyHeatmap chart={chart} rows={table.rows} labelFor={labels.text} />}
        <figcaption className="text-xs text-muted-foreground" data-testid="results-chart-meta">
          {t('results.chartMeta', { unit, periods: periodRange(table) ?? t('results.noPeriods'), sources: sourceText })}
          {' · '}<NatureBadge nature={chart.series.some((s) => s.nature === 'scenario') ? 'scenario'
            : chart.series.every((s) => s.nature === 'observed') ? 'observed' : 'calculated'} />
        </figcaption>
        <p className="text-xs text-muted-foreground">{t('studies.chartNote')}</p>
      </figure>
    </Appear>
  );
}

function SourcesList({ sources }: { sources: ResultSource[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <ol className="flex flex-col gap-2" data-testid="results-source-list">
      {sources.map((s) => (
        <li key={s.id} className="rounded-md border border-border bg-background p-3 text-sm" data-testid="results-source" data-source={s.id}>
          <p className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="font-mono" dir="ltr">{s.id}</span>
            <DataStatusBadge status={s.dataStatus} showReference />
            {s.olderContext ? <Badge variant="sand">{t('balance.sourceFields.olderContext')}</Badge> : null}
          </p>
          <p className="mt-1 font-medium">
            {s.url && /^https?:\/\//.test(s.url) ? (
              <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                <bdi>{s.title}</bdi><ExternalLink aria-hidden="true" className="size-3" />
              </a>
            ) : <bdi>{s.title}</bdi>}
          </p>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            {([
              ['publisher', s.publisher], ['publication', s.publication], ['period', s.period],
              ['value', s.value != null ? `${s.valueOperator ?? ''}${formatDecimal(s.value, language, 4) ?? s.value}${s.unit ? ` ${s.unit}` : ''}` : null],
              ['dataset', s.dataset], ['record', s.record], ['accessed', s.accessed ?? s.published],
            ] as const).filter(([, v]) => v).map(([k, v]) => (
              <div key={k} className="contents">
                <dt>{t(`balance.sourceFields.${k}`)}</dt>
                <dd dir="auto" className="text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ol>
  );
}

const PRIORITY_TONE: Record<string, 'accent' | 'sand' | 'muted' | 'outline'> = { high: 'accent', medium: 'sand', low: 'muted', conditional: 'outline' };

function RecommendationsTab({ model }: { model: ResultsModel }) {
  const { t } = useTranslation();
  if (!model.recommendations.length) return <Empty text={t('results.noRecommendations')} />;
  return (
    <Appear className="flex flex-col gap-3">
      <p className="rounded-md border border-sand/60 bg-sand-subtle/50 p-2 text-sm" role="note" data-testid="results-decision-support">{t('balance.decisionSupport')}</p>
      {model.prioritization ? (
        <details className="text-sm"><summary className="cursor-pointer font-medium">{t('balance.prioritization')}</summary>
          <p className="mt-1 text-muted-foreground">{model.prioritization}</p></details>
      ) : null}
      <RecommendationTable rows={model.recommendations} />
      <ul className="flex flex-col gap-2 md:hidden" data-testid="results-recommendation-cards">
        {model.recommendations.map((r) => <RecommendationCard key={r.id} r={r} />)}
      </ul>
    </Appear>
  );
}

// Issue | Evidence | Proposed action | Quantity/unit | Feasibility constraints | Time horizon | Cost evidence |
// Expected effect and assumptions | Priority | Monitoring KPI.
const COLUMNS = ['problem', 'evidence', 'action', 'quantity', 'constraints', 'horizon', 'cost', 'outcome', 'priority', 'kpi'] as const;

function cell(r: ResultRecommendation, key: (typeof COLUMNS)[number], language: 'en' | 'ar', notQuantified: string): ReactNode {
  switch (key) {
    case 'problem': return <><span className="me-1 font-mono text-xs text-muted-foreground" dir="ltr">{r.id}</span><bdi>{r.problem}</bdi><span className="mt-1 block text-xs text-muted-foreground">{r.nature.label}{r.option ? ` · ${r.option.label}` : ''}</span></>;
    case 'evidence': return <><bdi>{r.evidence}</bdi>{r.evidenceIds.length ? <span className="block font-mono text-xs text-muted-foreground" dir="ltr">[{r.evidenceIds.join(', ')}]</span> : null}</>;
    case 'action': return <bdi className="font-medium">{r.action}</bdi>;
    case 'quantity': return r.quantity ? <><span dir="ltr" className="tabular-nums">{formatDecimal(r.quantity, language, 3) ?? r.quantity}</span> {r.quantityUnit}<span className="block text-xs text-muted-foreground">{r.quantityNote}</span></>
      : <><span>{notQuantified}</span>{r.quantityNote ? <span className="block text-xs text-muted-foreground">{r.quantityNote}</span> : null}</>;
    case 'horizon': return r.horizon ?? '—';
    case 'constraints': return r.constraints ?? '—';
    case 'cost': return r.cost ?? '—';
    case 'outcome': return r.outcome ?? '—';
    case 'priority': return r.priority ? <><Badge variant={PRIORITY_TONE[r.priority.code] ?? 'outline'} data-testid="priority" data-priority={r.priority.code}>{r.priority.label}</Badge>{r.priorityBasis ? <span className="mt-1 block text-xs text-muted-foreground">{r.priorityBasis}</span> : null}</> : '—';
    case 'kpi': return r.kpi ?? '—';
  }
}

function ConclusionTab({ model }: { model: ResultsModel }) {
  const { t } = useTranslation();
  const c = model.conclusion;
  if (!c) return <Empty text={model.kind === 'study' ? t('results.conclusion.studyNone') : t('results.conclusion.missing')} />;
  const list = (items: string[], testid: string) => (items.length
    ? <ul className="list-disc ps-5 text-sm" data-testid={testid}>{items.map((x, i) => <li key={i} dir="auto">{x}</li>)}</ul>
    : <p className="text-sm text-muted-foreground">{t('results.conclusion.none')}</p>);
  return (
    <Appear className="flex flex-col gap-3" data-testid="conclusion">
      <section><h3 className="text-sm font-semibold">{t('results.conclusion.findings')}</h3>{list(c.findings, 'conclusion-findings')}</section>
      <section><h3 className="text-sm font-semibold">{t('results.conclusion.limits')}</h3>{list(c.limitations, 'conclusion-limits')}</section>
      <section><h3 className="text-sm font-semibold">{t('results.conclusion.immediate')}</h3>{list(c.immediate.map((a) => `${a.id} · ${a.action}`), 'conclusion-immediate')}</section>
      <section><h3 className="text-sm font-semibold">{t('results.conclusion.mediumTerm')}</h3>{list(c.mediumTerm.map((a) => `${a.id} · ${a.action}`), 'conclusion-medium')}</section>
      <section><h3 className="text-sm font-semibold">{t('results.conclusion.next')}</h3>
        {list(c.nextStudy.map((n) => `${n.question} — ${n.data}${n.where ? ` (${n.where})` : ''}`), 'conclusion-next')}</section>
    </Appear>
  );
}

function RecommendationTable({ rows }: { rows: ResultRecommendation[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[64rem] border-collapse text-sm" data-testid="results-recommendation-table">
        <caption className="sr-only">{t('results.tabs.recommendations')}</caption>
        <thead>
          <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
            {COLUMNS.map((c) => <th key={c} scope="col" className="px-2 py-2 text-start font-medium">{t(`balance.columns.${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border align-top last:border-0" data-testid="recommendation-row" data-nature={r.nature.code}>
              {COLUMNS.map((c) => <td key={c} className="px-2 py-2">{cell(r, c, language, t('balance.notQuantified'))}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecommendationCard({ r }: { r: ResultRecommendation }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <li className="rounded-lg border border-border bg-card p-3 text-sm" data-testid="recommendation-card">
      <dl className="grid gap-1">
        {COLUMNS.map((c) => (
          <div key={c} className="grid grid-cols-[8rem_1fr] gap-2">
            <dt className="text-xs font-medium text-muted-foreground">{t(`balance.columns.${c}`)}</dt>
            <dd>{cell(r, c, language, t('balance.notQuantified'))}</dd>
          </div>
        ))}
      </dl>
    </li>
  );
}
