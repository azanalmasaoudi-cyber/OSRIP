import { FileSpreadsheet, Sparkles, Trash2, Upload } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { hasPermission, useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import {
  useDataset,
  useDatasetRows,
  useDatasets,
  useDeleteDataset,
  useSummariseDataset,
  useUploadDataset,
  type DatasetDetail,
} from '@/api/datasets';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { DataTable } from '@/components/datasets/DataTable';
import { ViewChart } from '@/components/datasets/ViewChart';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { formatDateTime, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Datasets people upload to analyse. Every figure on this page was computed by the server
 * from the file's own values (or is the file's own value); the page formats numbers for
 * reading and never calculates them. The AI summary is optional and labelled with the model
 * that wrote it.
 */

const ACCEPT = '.csv,.txt,.xlsx,.json,text/csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function Gate({ children }: { children: (allowed: boolean) => ReactNode }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const me = useMe();
  if (adapterKind !== 'http') {
    return <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('analysis.requiresApi')}</p></StatePanel>;
  }
  if (me.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (me.isError) return <StatePanel kind="error" detail={me.error.message} onRetry={() => void me.refetch()} />;
  if (!me.data.authenticated) {
    return (
      <StatePanel kind="restricted">
        <p className="text-sm text-muted-foreground">{t('datasets.signInPrompt')}</p>
        <Link to={to('/sign-in')} className={cn(buttonVariants({ size: 'sm' }), 'mt-3 w-fit')}>{t('auth.signIn')}</Link>
      </StatePanel>
    );
  }
  if (!hasPermission(me.data, 'dataset.analyze')) {
    return <StatePanel kind="restricted"><p className="text-sm text-muted-foreground">{t('datasets.noPermission')}</p></StatePanel>;
  }
  return <>{children(true)}</>;
}

function UploadCard() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const upload = useUploadDataset();
  const fileId = useId();
  const sheetId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    upload.mutate({ file, sheet: sheet.trim() || undefined }, {
      onSuccess: (detail) => void navigate(to(`/datasets/${detail.id}`)),
    });
  };
  const isExcel = file?.name.toLowerCase().endsWith('.xlsx') ?? false;
  return (
    <Card className="p-5">
      <form onSubmit={submit} className="flex flex-col gap-4" data-testid="dataset-upload">
        <div className="flex items-center gap-2">
          <Upload aria-hidden="true" className="size-5 text-primary" />
          <h2 className="text-base font-semibold">{t('datasets.uploadTitle')}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{t('datasets.uploadIntro')}</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-60 flex-1 flex-col gap-1.5">
            <label htmlFor={fileId} className="text-xs font-medium text-muted-foreground">{t('datasets.file')}</label>
            <input id={fileId} type="file" accept={ACCEPT} required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full rounded-md border border-border-strong bg-card text-sm file:me-3 file:h-10 file:border-0 file:bg-muted file:px-3 file:text-sm" />
          </div>
          {isExcel ? (
            <div className="flex min-w-40 flex-col gap-1.5">
              <label htmlFor={sheetId} className="text-xs font-medium text-muted-foreground">{t('datasets.sheet')}</label>
              <input id={sheetId} value={sheet} onChange={(e) => setSheet(e.target.value)} placeholder={t('datasets.sheetPlaceholder')}
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
            </div>
          ) : null}
          <Button type="submit" disabled={!file || upload.isPending}>
            <FileSpreadsheet aria-hidden="true" />{upload.isPending ? t('datasets.analysing') : t('datasets.uploadButton')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('datasets.limits')}</p>
        {upload.isError ? <p role="alert" className="text-sm text-destructive">{upload.error.message}</p> : null}
      </form>
    </Card>
  );
}

function DatasetList() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const datasets = useDatasets(true);
  if (datasets.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (datasets.isError) return <StatePanel kind="error" detail={datasets.error.message} onRetry={() => void datasets.refetch()} />;
  if (datasets.data.length === 0) {
    return <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('datasets.none')}</p></StatePanel>;
  }
  return (
    <ul className="flex flex-col gap-3" data-testid="datasets-list">
      {datasets.data.map((d) => (
        <li key={d.id}>
          <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="flex min-w-0 flex-col gap-1">
              <Link to={to(`/datasets/${d.id}`)} className="truncate font-semibold text-primary underline underline-offset-2" dir="auto">{d.name}</Link>
              <p className="text-xs text-muted-foreground">
                {t('datasets.rowsColumns', { rows: d.row_count, columns: d.columns.length })} · {formatDateTime(d.created_at, language)}
              </p>
            </div>
            <Badge variant="muted">{d.file_type.toUpperCase()}{d.sheet ? ` · ${d.sheet}` : ''}</Badge>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function Kpi({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xl font-semibold tabular-nums">{value}</span>
    </Card>
  );
}

function Summary({ dataset }: { dataset: DatasetDetail }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const summarise = useSummariseDataset(dataset.id);
  const summary = dataset.summary[language];
  return (
    <Card className="p-5" data-testid="dataset-summary">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles aria-hidden="true" className="size-5 text-primary" />
          <h2 className="text-base font-semibold">{t('datasets.summaryTitle')}</h2>
        </div>
        <Button variant="outline" size="sm" onClick={() => summarise.mutate(language)} disabled={summarise.isPending}>
          {summarise.isPending ? t('datasets.summaryWriting') : summary ? t('datasets.summaryAgain') : t('datasets.summaryButton')}
        </Button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t('datasets.summaryNote')}</p>
      {summarise.isError ? <p role="alert" className="mt-3 text-sm text-destructive">{summarise.error.message}</p> : null}
      {summary ? (
        summary.status === 'withheld' ? (
          <p className="mt-3 text-sm">{t('datasets.summaryWithheld')}</p>
        ) : (
          <div className="mt-3 flex flex-col gap-3 text-sm">
            <p>{summary.overview}</p>
            {summary.highlights.length > 0 ? (
              <ul className="list-disc ps-5">{summary.highlights.map((h) => <li key={h}>{h}</li>)}</ul>
            ) : null}
            {summary.caveats.length > 0 ? (
              <div>
                <p className="text-xs font-semibold">{t('datasets.caveats')}</p>
                <ul className="list-disc ps-5 text-muted-foreground">{summary.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">
              {t('datasets.summaryBy', { model: summary.model, provider: summary.provider })}
              {summary.removed > 0 ? ` ${t('datasets.summaryRemoved', { count: summary.removed })}` : ''}
            </p>
          </div>
        )
      ) : null}
    </Card>
  );
}

function num(value: string | null | undefined, language: 'en' | 'ar', digits = 4) {
  return value == null ? '—' : <span dir="ltr">{formatDecimal(value, language, digits)}</span>;
}

function SimpleTable({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-max text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-muted/60">
          <tr>{head.map((h, i) => <th key={i} scope="col" className="px-3 py-2 text-start font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              {r.map((c, j) => <td key={j} className="px-3 py-1.5">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Statistics({ dataset }: { dataset: DatasetDetail }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const a = dataset.analysis;
  const kindLabel = { number: t('datasets.kind.number'), period: t('datasets.kind.period'), text: t('datasets.kind.text') };
  const comma = language === 'ar' ? '، ' : ', ';
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('datasets.columnsTitle')}</h2>
        <SimpleTable caption={t('datasets.columnsTitle')}
          head={[t('datasets.col.name'), t('datasets.col.kind'), t('datasets.col.unit'), t('datasets.col.filled'), t('datasets.col.missing'), t('datasets.col.distinct'), t('datasets.col.unreadable')]}
          rows={a.profile.map((c) => [
            <span dir="auto">{c.name}</span>,
            `${kindLabel[c.kind]}${c.period_kind ? ` · ${t(`datasets.periodKind.${c.period_kind}`)}` : ''}`,
            c.unit ? (language === 'ar' ? c.unit.label_ar : c.unit.label_en) : '—',
            c.count, c.missing, c.distinct,
            c.unreadable ? `${c.unreadable} (${t('datasets.rowsList', { rows: c.unreadable_rows?.join(', ') ?? '' })})` : '—',
          ])} />
      </section>
      {a.statistics.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{t('datasets.statisticsTitle')}</h2>
          <SimpleTable caption={t('datasets.statisticsTitle')}
            head={[t('datasets.col.name'), t('datasets.stat.count'), t('datasets.stat.sum'), t('datasets.stat.mean'), t('datasets.stat.median'), t('datasets.stat.min'), t('datasets.stat.max'), t('datasets.stat.std')]}
            rows={a.statistics.map((s) => [
              <span dir="auto">{s.column}</span>, s.count, num(s.sum, language), num(s.mean, language), num(s.median, language),
              <>{num(s.min.value, language)} <span className="text-xs text-muted-foreground">({t('datasets.row', { row: s.min.row })})</span></>,
              <>{num(s.max.value, language)} <span className="text-xs text-muted-foreground">({t('datasets.row', { row: s.max.row })})</span></>,
              num(s.std, language),
            ])} />
        </section>
      ) : null}
      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('datasets.trendsTitle')}</h2>
        {a.trends.length === 0 ? (
          <p className="text-sm text-muted-foreground">{a.trend_notes.some((n) => n.startsWith('repeated_periods')) ? t('datasets.noTrendRepeated') : t('datasets.noTrend')}</p>
        ) : (
          <SimpleTable caption={t('datasets.trendsTitle')}
            head={[t('datasets.col.name'), t('datasets.trend.group'), t('datasets.trend.first'), t('datasets.trend.last'), t('datasets.trend.change'), t('datasets.trend.cagr'), t('datasets.trend.jumps')]}
            rows={a.trends.map((tr) => [
              <span dir="auto">{tr.column}</span>,
              tr.group ? <span dir="auto">{tr.group.value}</span> : '—',
              <>{num(tr.first.value, language)} <span className="text-xs text-muted-foreground">{tr.first.period}</span></>,
              <>{num(tr.last.value, language)} <span className="text-xs text-muted-foreground">{tr.last.period}</span></>,
              <>{num(tr.change, language)}{tr.change_pct ? <span className="text-xs text-muted-foreground"> ({num(tr.change_pct, language, 2)}%)</span> : null}</>,
              tr.cagr_pct ? <>{num(tr.cagr_pct, language, 2)}%</> : '—',
              tr.jumps.length ? tr.jumps.map((j) => `${j.from.period}→${j.to.period}`).join(', ') : '—',
            ])} />
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('datasets.anomaliesTitle')}</h2>
        <p className="text-xs text-muted-foreground">{t('datasets.anomaliesNote')}</p>
        <SimpleTable caption={t('datasets.anomaliesTitle')}
          head={[t('datasets.col.name'), t('datasets.anomaly.status'), t('datasets.anomaly.values')]}
          rows={a.anomalies.map((x) => [
            <span dir="auto">{x.column}</span>,
            t(`datasets.anomaly.${x.status}`),
            x.items.length
              ? x.items.map((i) => `${i.value} (${t('datasets.row', { row: i.row })}${i.period ? `${comma}${i.period}` : ''})`).join(language === 'ar' ? '؛ ' : '; ')
              : '—',
          ])} />
      </section>
      {a.comparisons.map((c) => (
        <section key={`${c.category}|${c.column}`} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold" dir="auto">{t('datasets.comparisonTitle', { column: c.column, category: c.category })}</h2>
          <SimpleTable caption={c.column}
            head={[c.category, t('datasets.stat.count'), t('datasets.stat.sum'), t('datasets.stat.mean'), t('datasets.stat.min'), t('datasets.stat.max'), t('datasets.stat.share')]}
            rows={c.groups.map((g) => [
              <span dir="auto">{g.group}</span>, g.count, num(g.sum, language), num(g.mean, language), num(g.min, language), num(g.max, language),
              g.share_pct ? <>{num(g.share_pct, language, 2)}%</> : '—',
            ])} />
        </section>
      ))}
      {a.correlations.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{t('datasets.correlationsTitle')}</h2>
          <p className="text-xs text-muted-foreground">{t('datasets.correlationNote')}</p>
          <SimpleTable caption={t('datasets.correlationsTitle')}
            head={[t('datasets.corr.pair'), 'r', t('datasets.corr.pairs'), t('datasets.corr.strength')]}
            rows={a.correlations.map((c) => [<span dir="auto">{c.x} · {c.y}</span>, <span dir="ltr">{c.r}</span>, c.pairs, t(`datasets.strength.${c.strength}`)])} />
        </section>
      ) : null}
    </div>
  );
}

function DataTab({ dataset }: { dataset: DatasetDetail }) {
  const { t } = useTranslation();
  const rows = useDatasetRows(dataset.id);
  if (rows.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (rows.isError) return <StatePanel kind="error" detail={rows.error.message} onRetry={() => void rows.refetch()} />;
  const kinds = new Map(dataset.analysis.profile.map((p) => [p.index, p.kind]));
  return (
    <div className="flex flex-col gap-2">
      {rows.data.truncated ? <p className="text-xs text-muted-foreground">{t('datasets.truncated', { shown: rows.data.rows.length, total: rows.data.row_count })}</p> : null}
      <DataTable caption={dataset.name} testId="dataset-table"
        fileName={`${dataset.name.replace(/\.[^.]+$/, '')}-rows.csv`}
        columns={rows.data.columns.map((c, i) => ({ key: String(i), label: c, numeric: kinds.get(i) === 'number' }))}
        rows={rows.data.rows} />
    </div>
  );
}

type Tab = 'overview' | 'statistics' | 'data';

function DatasetDetailView({ id }: { id: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const dataset = useDataset(id);
  const remove = useDeleteDataset();
  const [tab, setTab] = useState<Tab>('overview');
  if (dataset.isPending) return <StatePanel kind="loading" />;
  if (dataset.isError) return <StatePanel kind="error" detail={dataset.error.message} onRetry={() => void dataset.refetch()} />;
  const d = dataset.data;
  const a = d.analysis;
  const missing = a.profile.reduce((sum, c) => sum + c.missing, 0);
  const numeric = a.profile.filter((c) => c.kind === 'number').length;
  const period = a.profile.find((c) => c.kind === 'period');
  const notes = [
    d.notes.encoding ? t('datasets.note.encoding') : null,
    typeof d.notes.delimiter === 'string' ? t('datasets.note.delimiter', { delimiter: d.notes.delimiter }) : null,
    d.notes.columns_renamed ? t('datasets.note.renamed') : null,
    d.notes.rows_padded ? t('datasets.note.padded', { count: Number(d.notes.rows_padded) }) : null,
    d.notes.cells_truncated ? t('datasets.note.truncated', { count: Number(d.notes.cells_truncated) }) : null,
  ].filter(Boolean);
  const onDelete = () => {
    if (!window.confirm(t('datasets.deleteConfirm', { name: d.name }))) return;
    remove.mutate(d.id, { onSuccess: () => void navigate(to('/datasets')) });
  };
  return (
    <div className="flex flex-col gap-6" data-testid="dataset-detail">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="truncate text-lg font-semibold" dir="auto">{d.name}</h2>
          <p className="text-xs text-muted-foreground">
            {d.file_type.toUpperCase()}{d.sheet ? ` · ${d.sheet}` : ''} · {formatDateTime(d.created_at, language)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={onDelete} disabled={remove.isPending}>
            <Trash2 aria-hidden="true" />{t('datasets.delete')}
          </Button>
        </div>
      </div>
      {notes.length > 0 ? <p className="text-xs text-muted-foreground">{notes.join(' ')}</p> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label={t('datasets.kpi.rows')} value={formatDecimal(String(a.rows), language, 0)} />
        <Kpi label={t('datasets.kpi.columns')} value={a.columns} />
        <Kpi label={t('datasets.kpi.numeric')} value={numeric} />
        <Kpi label={t('datasets.kpi.missing')} value={formatDecimal(String(missing), language, 0)} />
        <Kpi label={t('datasets.kpi.periods')} value={period ? t(`datasets.periodKind.${period.period_kind ?? 'year'}`) : '—'} />
      </div>
      <Segmented label={t('datasets.tabs')} value={tab} className="w-fit" testId="dataset-tabs"
        options={[{ value: 'overview', label: t('datasets.tab.overview') }, { value: 'statistics', label: t('datasets.tab.statistics') }, { value: 'data', label: t('datasets.tab.data') }]}
        onChange={setTab} />
      {tab === 'overview' ? (
        <div className="flex flex-col gap-6">
          <Card className="p-5">
            <h2 className="text-base font-semibold">{t('datasets.findingsTitle')}</h2>
            <p className="mt-1 text-xs text-muted-foreground">{t('datasets.findingsNote')}</p>
            {a.findings.length ? (
              <ul className="mt-3 flex list-disc flex-col gap-1.5 ps-5 text-sm" data-testid="dataset-findings">
                {a.findings.map((f, i) => <li key={i} data-kind={f.kind}>{f.text[language]}</li>)}
              </ul>
            ) : <p className="mt-3 text-sm text-muted-foreground">{t('datasets.noFindings')}</p>}
          </Card>
          <Summary dataset={d} />
          {a.views.length ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {a.views.map((v) => <Card key={v.id} className="p-4"><ViewChart view={v} /></Card>)}
            </div>
          ) : <p className="text-sm text-muted-foreground">{t('datasets.noCharts')}</p>}
        </div>
      ) : tab === 'statistics' ? <Statistics dataset={d} /> : <DataTab dataset={d} />}
    </div>
  );
}

export function DatasetsPage() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const { datasetId } = useParams();
  return (
    <>
      <PageHeader title={t('datasets.title')} intro={t('datasets.intro')} />
      <Gate>
        {() => (datasetId ? (
          <div className="flex flex-col gap-4">
            <Link to={to('/datasets')} className="w-fit text-sm text-primary underline underline-offset-2">{t('datasets.back')}</Link>
            <DatasetDetailView id={datasetId} />
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <UploadCard />
            <DatasetList />
          </div>
        ))}
      </Gate>
    </>
  );
}
