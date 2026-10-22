import { CheckCircle2, CircleDashed, CircleSlash, ExternalLink, FlaskConical, Loader2, RotateCcw, Square, XCircle } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { SECTORS, type Sector } from '@/api/balance';
import { useAreaRegistry } from '@/api/geography';
import {
  FINISHED, SOURCE_SCOPES, useCreateJob, useJob, useJobAction, useJobDocuments, useMyJobs,
  type JobStep, type ResearchJob, type SourceScope,
} from '@/api/researchJobs';
import { useTimeline, type SeriesView } from '@/api/series';
import { StatePanel } from '@/components/common/StatePanel';
import { TimelineChart } from '@/components/series/SeriesParts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import type { DataMode } from '@/domain/types';
import { formatDate } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * "Create study": a sector, an area, a period and a research question; the study then runs in
 * the background (discover, retrieve, extract, validate, calculate, build, conclude, next
 * steps) and this page reads its progress every two seconds. It can be stopped and retried;
 * a repeated study on the same published data comes from cache unless asked to run again.
 */
export function CreateStudy() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const [params, setParams] = useSearchParams();
  const me = useMe();
  const registry = useAreaRegistry();
  const create = useCreateJob();
  const formId = useId();
  const preset = params.get('create');
  const [sector, setSector] = useState<Sector>((SECTORS as readonly string[]).includes(preset ?? '') ? preset as Sector : 'electricity');
  const [area, setArea] = useState('OM');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [question, setQuestion] = useState('');
  const [scope, setScope] = useState<SourceScope>('none');
  const [refresh, setRefresh] = useState(false);
  const signedIn = Boolean(me.data?.authenticated);
  const governorates = (registry.data?.areas ?? []).filter((a) => a.level === 'governorate');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate({
      params: {
        sector, area, question: question.trim() || t(`jobs.defaultQuestion.${sector}`), language, data_mode: mode,
        source_scope: scope, period_from: from ? `${from}-01` : null, period_to: to ? `${to}-28` : null,
      },
      refresh,
    }, {
      onSuccess: (job) => {
        const next = new URLSearchParams(params);
        next.set('job', job.id);
        next.delete('create');
        setParams(next, { replace: false });
      },
    });
  };

  return (
    <section className="surface-card flex flex-col gap-4 p-4 sm:p-5" aria-labelledby={`${formId}-h`} data-testid="create-study">
      <div>
        <h2 id={`${formId}-h`} className="flex items-center gap-2 text-lg font-semibold"><FlaskConical aria-hidden="true" className="size-5" />{t('jobs.create')}</h2>
        <p className="text-sm text-muted-foreground">{t('jobs.intro')}</p>
      </div>
      {!signedIn ? <p className="text-sm" data-testid="create-study-sign-in">{t('jobs.signIn')}</p> : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SelectField label={t('balance.sector')} value={sector} onValueChange={(v) => setSector(v as Sector)} data-testid="job-sector"
              options={SECTORS.map((s) => ({ value: s, label: t(`balance.sectors.${s}`) }))} />
            <SelectField label={t('filters.area')} value={area} onValueChange={setArea} data-testid="job-area"
              options={[{ value: 'OM', label: t('filters.national') },
                ...governorates.map((g) => ({ value: g.code, label: language === 'ar' ? g.name_ar : g.name_en }))]} />
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('series.from')}
              <input type="month" value={from} onChange={(e) => setFrom(e.target.value)} className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm text-foreground" dir="ltr" data-testid="job-from" />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('series.to')}
              <input type="month" value={to} onChange={(e) => setTo(e.target.value)} className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm text-foreground" dir="ltr" data-testid="job-to" />
            </label>
          </div>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            {t('jobs.question')}
            <textarea value={question} onChange={(e) => setQuestion(e.target.value.slice(0, 1000))} rows={2} dir="auto"
              placeholder={t(`jobs.defaultQuestion.${sector}`)} className="rounded-md border border-border-strong bg-card px-3 py-2 text-sm text-foreground"
              data-testid="job-question" />
          </label>
          <div className="flex flex-col gap-1">
            <Segmented label={t('jobs.scope.label')} value={scope} onChange={(v) => setScope((SOURCE_SCOPES as readonly string[]).includes(v) ? v : 'none')}
              options={SOURCE_SCOPES.map((s) => ({ value: s, label: t(`jobs.scope.${s}`) }))} testId="job-scope" />
            <p className="text-xs text-muted-foreground">{t(`jobs.scopeNote.${scope}`)}</p>
          </div>
          <label className="flex items-center gap-2 text-xs font-medium">
            <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} className="size-4 accent-primary" data-testid="job-refresh" />
            {t('jobs.refresh')}
          </label>
          <Button type="submit" className="w-fit" disabled={create.isPending} data-testid="job-submit">
            <FlaskConical aria-hidden="true" />{create.isPending ? t('jobs.creating') : t('jobs.start')}
          </Button>
          {create.isError ? <p role="alert" className="text-sm text-destructive">{create.error.message}</p> : null}
        </form>
      )}
    </section>
  );
}

const STEP_ICON = {
  pending: <CircleDashed aria-hidden="true" className="size-4 text-muted-foreground" />,
  running: <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />,
  done: <CheckCircle2 aria-hidden="true" className="size-4 text-verified-foreground" />,
  skipped: <CircleSlash aria-hidden="true" className="size-4 text-muted-foreground" />,
  failed: <XCircle aria-hidden="true" className="size-4 text-destructive" />,
  cancelled: <CircleSlash aria-hidden="true" className="size-4 text-muted-foreground" />,
} as const;

function Steps({ steps }: { steps: JobStep[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <ol className="flex flex-col gap-2" data-testid="job-steps">
      {steps.map((s, i) => (
        <li key={s.stage} className="flex items-start gap-2 text-sm" data-stage={s.stage} data-state={s.state}>
          <span className="mt-0.5">{STEP_ICON[s.state]}</span>
          <span className="min-w-0 flex-1">
            <span className="font-medium">{i + 1}. {s.label[language]}</span>
            <span className="ms-2 text-xs text-muted-foreground">{t(`jobs.stepState.${s.state}`)}</span>
            {s.detail ? <span className="block text-xs text-muted-foreground">{s.detail[language]}</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

function SeriesPreview({ table }: { table: NonNullable<NonNullable<ResearchJob['result']>['tables']>[number] }) {
  const q = useTimeline({ dataMode: table.params.data_mode as DataMode, indicator: table.indicator, area: table.params.area,
    view: table.params.view as SeriesView, periodFrom: table.params.period_from, periodTo: table.params.period_to });
  const language = useAppLanguage();
  if (!q.data || q.data.status !== 'ok') return null;
  return (
    <div className="rounded-md border border-border p-3" data-testid="job-series" data-dataset-id={table.dataset_id}>
      <p className="mb-1 text-sm font-semibold">{table.name[language]}</p>
      <TimelineChart timeline={q.data} />
    </div>
  );
}

function Documents({ job }: { job: ResearchJob }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const docs = useJobDocuments(job.id, FINISHED.includes(job.state) && job.source_scope !== 'none');
  if (job.source_scope === 'none') return null;
  return (
    <details className="rounded-md border border-border p-3 text-sm" data-testid="job-documents">
      <summary className="cursor-pointer font-semibold">{t('jobs.documents', { count: docs.data?.length ?? 0 })}</summary>
      <p className="mt-1 text-xs text-muted-foreground">{t('jobs.untrusted')}</p>
      <ul className="mt-2 flex flex-col gap-2">
        {(docs.data ?? []).map((d) => (
          <li key={d.id} className="flex flex-col gap-0.5" data-testid="job-document" data-status={d.status}>
            <span className="flex flex-wrap items-center gap-1.5">
              <Badge variant={d.status === 'ok' ? 'verified' : 'muted'}>{d.status === 'ok' ? t('jobs.retrieved') : d.status}</Badge>
              <a href={d.final_url ?? d.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2" dir="ltr">
                {d.title || d.host}<ExternalLink aria-hidden="true" className="size-3" />
              </a>
              {d.duplicate_of ? <Badge variant="outline">{t('jobs.duplicate')}</Badge> : null}
              {d.revision_of ? <Badge variant="sand">{t('jobs.revision')}</Badge> : null}
            </span>
            <span className="text-xs text-muted-foreground">
              {[d.publisher, t(`web.sourceClass.${d.source_class}`, { defaultValue: d.source_class }),
                d.retrieved_at ? t('jobs.retrievedAt', { date: formatDate(d.retrieved_at, language) }) : null,
                d.published ? t('jobs.publishedOn', { date: formatDate(d.published, language) }) : t('jobs.publishedUnknown'),
                d.reporting_period ? t('jobs.period', { period: d.reporting_period }) : t('jobs.periodUnknown')].filter(Boolean).join(' · ')}
            </span>
          </li>
        ))}
      </ul>
      {job.result?.excerpts?.length ? (
        <div className="mt-3" data-testid="job-excerpts">
          <p className="text-xs font-semibold">{t('jobs.excerpts')}</p>
          <ul className="mt-1 flex flex-col gap-1">
            {job.result.excerpts.map((e, i) => (
              <li key={i} className="rounded bg-muted/50 px-2 py-1 text-xs" dir="auto"><Badge variant="muted">{t('jobs.unreviewed')}</Badge> {e.text}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </details>
  );
}

export function JobView({ id }: { id: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const link = usePreservedSearch();
  const job = useJob(id);
  const action = useJobAction();
  if (job.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (job.isError) return <StatePanel kind="error" detail={job.error.message} />;
  const j = job.data;
  const finished = FINISHED.includes(j.state);
  const r = j.result ?? {};
  return (
    <section className="surface-card flex flex-col gap-4 p-4 sm:p-5" aria-labelledby={`job-${j.id}`} data-testid="job-view" data-state={j.state}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`job-${j.id}`} className="text-lg font-semibold" dir="auto">{j.question}</h2>
          <p className="text-xs text-muted-foreground">
            {t(`balance.sectors.${j.sector}`, { defaultValue: j.sector })} · {j.area} · {t(`jobs.scope.${j.source_scope}`)}
            {j.cached ? ` · ${t('jobs.cached')}` : ''}
          </p>
        </div>
        <Badge variant={j.state === 'succeeded' ? 'verified' : j.state === 'failed' ? 'outline' : 'sand'} data-testid="job-state">{t(`jobs.state.${j.state}`)}</Badge>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={j.progress}
        aria-label={t('jobs.progress')}>
        <div className={cn('h-full bg-primary transition-[width] motion-reduce:transition-none')} style={{ width: `${j.progress}%` }} />
      </div>
      <Steps steps={j.steps} />
      <div className="flex flex-wrap gap-2">
        {!finished ? (
          <Button type="button" variant="outline" size="sm" disabled={action.isPending || j.cancel_requested} onClick={() => action.mutate({ id: j.id, action: 'cancel' })} data-testid="job-cancel">
            <Square aria-hidden="true" />{j.cancel_requested ? t('jobs.stopping') : t('jobs.stop')}
          </Button>
        ) : null}
        {j.state === 'failed' || j.state === 'partial' || j.state === 'cancelled' ? (
          <Button type="button" variant="outline" size="sm" disabled={action.isPending} onClick={() => action.mutate({ id: j.id, action: 'retry' })} data-testid="job-retry">
            <RotateCcw aria-hidden="true" />{t('jobs.retry')}
          </Button>
        ) : null}
        {j.analysis_id ? (
          <Link to={link(`/assistant?analysis=${j.analysis_id}`)} className="inline-flex items-center gap-1.5 rounded-md border border-border-strong/60 px-3 py-1.5 text-sm hover:bg-muted" data-testid="job-analysis">
            {t('jobs.openAnalysis')}
          </Link>
        ) : null}
      </div>
      {j.error_code ? <p className="text-sm text-destructive" role="alert">{t('jobs.failed', { code: j.error_code })}</p> : null}

      {r.conclusion ? (
        <div className="flex flex-col gap-3" data-testid="job-conclusion">
          <h3 className="text-base font-semibold">{t('results.conclusion.title')}</h3>
          <div><p className="text-sm font-semibold">{t('results.conclusion.findings')}</p>
            <ul className="list-disc ps-5 text-sm">{r.conclusion.main_findings.map((f, i) => <li key={i}>{f.text[language]}</li>)}</ul></div>
          <div><p className="text-sm font-semibold">{t('results.conclusion.limits')}</p>
            <ul className="list-disc ps-5 text-sm">{r.conclusion.evidence_limitations.map((f, i) => <li key={i}>{f[language]}</li>)}</ul></div>
          <div><p className="text-sm font-semibold">{t('results.conclusion.immediate')}</p>
            {r.conclusion.immediate_actions.length
              ? <ul className="list-disc ps-5 text-sm">{r.conclusion.immediate_actions.map((a) => <li key={a.id}>{a.action[language]}</li>)}</ul>
              : <p className="text-sm text-muted-foreground">{t('results.conclusion.none')}</p>}</div>
          <div><p className="text-sm font-semibold">{t('results.conclusion.mediumTerm')}</p>
            {r.conclusion.medium_term_options.length
              ? <ul className="list-disc ps-5 text-sm">{r.conclusion.medium_term_options.map((a) => <li key={a.id}>{a.action[language]}</li>)}</ul>
              : <p className="text-sm text-muted-foreground">{t('results.conclusion.none')}</p>}</div>
          <p className="text-xs text-muted-foreground">{t('jobs.writtenByRules')}</p>
        </div>
      ) : null}
      {r.next_steps?.length ? (
        <div data-testid="job-next-steps">
          <h3 className="text-base font-semibold">{t('results.conclusion.next')}</h3>
          <ul className="list-disc ps-5 text-sm">
            {r.next_steps.map((n, i) => <li key={i}>{n.question[language]} <span className="text-muted-foreground">— {n.data[language]}</span></li>)}
          </ul>
        </div>
      ) : null}
      {r.tables?.length ? <div className="grid gap-3 lg:grid-cols-2">{r.tables.slice(0, 4).map((tb) => <SeriesPreview key={tb.dataset_id} table={tb} />)}</div> : null}
      <Documents job={j} />
    </section>
  );
}

export function MyJobs({ activeId }: { activeId: string | null }) {
  const { t } = useTranslation();
  const me = useMe();
  const [params, setParams] = useSearchParams();
  const jobs = useMyJobs(Boolean(me.data?.authenticated));
  if (!me.data?.authenticated) return null;
  return (
    <section className="surface-card p-4" data-testid="my-jobs">
      <h2 className="mb-2 text-sm font-semibold">{t('jobs.mine')}</h2>
      {!jobs.data?.length ? <p className="text-sm text-muted-foreground">{t('jobs.mineEmpty')}</p> : (
        <ul className="flex flex-col divide-y divide-border">
          {jobs.data.map((j) => (
            <li key={j.id} className="py-1.5 text-sm">
              <button type="button" aria-current={j.id === activeId ? 'true' : undefined} dir="auto"
                className="w-full truncate text-start text-primary underline-offset-2 hover:underline aria-[current=true]:font-semibold"
                onClick={() => { const next = new URLSearchParams(params); next.set('job', j.id); setParams(next); }}>
                {j.question}
              </button>
              <span className="text-xs text-muted-foreground">{t(`jobs.state.${j.state}`)} · {j.progress}%</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
