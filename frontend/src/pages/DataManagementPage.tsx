import { ArrowLeft, Check, Download, FileUp, ShieldCheck, Upload } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { hasPermission, useMe, type Me } from '@/api/auth';
import { adapterKind } from '@/api/config';
import {
  errorReportUrl,
  useApprove,
  useImport,
  useImportRows,
  useImports,
  usePublish,
  useRegisterSource,
  useReject,
  useSaveMapping,
  useSources,
  useUpload,
  useValidate,
  type ImportRecord,
  type SourceRecord,
  type VersionStatus,
} from '@/api/imports';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { PageHeader } from '@/components/common/PageHeader';
import { ResearchQueue } from '@/components/research/ResearchQueue';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { ProgressBar } from '@/components/ui/progress';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SourceFeedsAdmin } from '@/components/sources/SourceFeeds';
import { SelectField } from '@/components/ui/select';
import { VERSION_STATUS_KEY } from '@/i18n/keys';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

// ------------------------------------------------------------------ small building blocks

function ErrorText({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-destructive">
      {error.message}
    </p>
  );
}

function TextField({ label, value, onChange, type = 'text', required = false, dir, testId }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; required?: boolean;
  dir?: 'ltr' | 'auto'; testId?: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <input id={id} type={type} value={value} required={required} dir={dir} data-testid={testId}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
    </div>
  );
}

function StatusBadge({ status }: { status: VersionStatus }) {
  const { t } = useTranslation();
  const variant = status === 'published' ? 'verified' : status === 'rejected' ? 'accent' : 'muted';
  return <Badge variant={variant} data-testid="import-status">{t(VERSION_STATUS_KEY[status])}</Badge>;
}

const STEPS = ['upload', 'map', 'validate', 'review', 'approve', 'publish'] as const;
const STEP_DONE: Record<VersionStatus, number> = {
  draft: 1, validated: 4, approved: 5, published: 6, superseded: 6, rejected: 0,
};

function Stepper({ status }: { status: VersionStatus }) {
  const { t } = useTranslation();
  const done = STEP_DONE[status];
  return (
    <ol aria-label={t('dm.steps.label')} className="flex flex-wrap gap-x-2 gap-y-2 text-xs">
      {STEPS.map((step, i) => {
        const complete = i < done;
        const current = i === done && status !== 'rejected';
        return (
          <li key={step} aria-current={current ? 'step' : undefined}
            className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1',
              complete && 'border-verified-border bg-verified text-verified-foreground',
              current && 'border-primary font-semibold text-foreground',
              !complete && !current && 'border-border text-muted-foreground')}>
            {complete ? <Check aria-hidden="true" className="size-3.5" /> : <span aria-hidden="true">{i + 1}</span>}
            {t(`dm.steps.${step}`)}
          </li>
        );
      })}
    </ol>
  );
}

// ------------------------------------------------------------------ sources and upload

function RegisterSourceForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const register = useRegisterSource();
  const [mode, setMode] = useState<'synthetic' | 'verified_source'>('synthetic');
  const [f, setF] = useState({ title: '', publisher: '', url: '', locator: 'direct_file', accessDate: '',
    referencePeriod: '', coverage: 'OM (national)', reuse: '' });
  const set = (key: keyof typeof f) => (value: string) => setF((prev) => ({ ...prev, [key]: value }));
  const verified = mode === 'verified_source';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate({
      data_mode: mode, dataset_title: f.title, geographic_coverage: f.coverage,
      reference_period: f.referencePeriod || null, reuse_conditions: f.reuse || null,
      publisher: verified ? f.publisher || null : null, url: verified ? f.url || null : null,
      locator_kind: verified ? f.locator : null, access_date: verified ? f.accessDate || null : null,
    }, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" data-testid="register-source-form">
      <SelectField label={t('dm.form.mode')} value={mode}
        onValueChange={(v) => setMode(v === 'verified_source' ? 'verified_source' : 'synthetic')}
        options={[{ value: 'synthetic', label: t('dataMode.synthetic') },
          { value: 'verified_source', label: t('dataMode.verified_source') }]} />
      <TextField label={t('dm.form.title')} value={f.title} onChange={set('title')} required />
      {verified ? (
        <>
          <TextField label={t('dm.form.publisher')} value={f.publisher} onChange={set('publisher')} required />
          <TextField label={t('dm.form.url')} value={f.url} onChange={set('url')} type="url" dir="ltr" required />
          <SelectField label={t('dm.form.locator')} value={f.locator} onValueChange={set('locator')}
            options={[{ value: 'direct_file', label: t('dm.form.locatorDirect') },
              { value: 'statistical_table', label: t('dm.form.locatorTable') },
              { value: 'catalogue_page', label: t('dm.form.locatorCatalogue') }]} />
          <TextField label={t('dm.form.accessDate')} value={f.accessDate} onChange={set('accessDate')} type="date" required />
        </>
      ) : null}
      <TextField label={t('dm.form.referencePeriod')} value={f.referencePeriod} onChange={set('referencePeriod')} />
      <TextField label={t('dm.form.coverage')} value={f.coverage} onChange={set('coverage')} required />
      <TextField label={t('dm.form.reuse')} value={f.reuse} onChange={set('reuse')} required={verified} />
      <p className="text-xs text-muted-foreground sm:col-span-2">
        {verified ? t('dm.form.catalogueNote') : t('dm.form.syntheticNote')}
      </p>
      <div className="flex flex-col gap-2 sm:col-span-2">
        <ErrorText error={register.error} />
        <Button type="submit" disabled={register.isPending || !f.title} className="w-fit">
          {t('dm.form.submit')}
        </Button>
      </div>
    </form>
  );
}

function UploadForm({ sources, onUploaded }: { sources: SourceRecord[]; onUploaded: (id: string) => void }) {
  const { t } = useTranslation();
  const upload = useUpload();
  const [sourceId, setSourceId] = useState('');
  const [label, setLabel] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const fileId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    upload.mutate({ sourceId, versionLabel: label, file }, { onSuccess: (imp) => onUploaded(imp.id) });
  };

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3" data-testid="upload-form">
      <SelectField label={t('dm.source')} value={sourceId} onValueChange={setSourceId} data-testid="upload-source"
        options={[{ value: '', label: t('dm.chooseSource') },
          ...sources.map((s) => ({ value: s.id, label: s.dataset_title }))]} />
      <TextField label={t('dm.versionLabel')} value={label} onChange={setLabel} required dir="ltr" testId="upload-label" />
      <div className="flex flex-col gap-1.5">
        <label htmlFor={fileId} className="text-xs font-medium text-muted-foreground">{t('dm.file')}</label>
        <input id={fileId} type="file" accept=".csv,text/csv" data-testid="upload-file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm file:me-3 file:rounded-md file:border file:border-border-strong file:bg-card file:px-3 file:py-2" />
      </div>
      <div className="flex flex-col gap-2 sm:col-span-3">
        <ErrorText error={upload.error} />
        <Button type="submit" disabled={upload.isPending || !sourceId || !label || !file} className="w-fit">
          <Upload aria-hidden="true" />
          {t('dm.uploadSubmit')}
        </Button>
        {upload.isPending ? <ProgressBar label={t('dm.progressUpload')} className="max-w-sm" /> : null}
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ import detail

/** Keyed by the saved mapping at its call sites, so a new server mapping resets the local draft. */
function MappingStep({ imp }: { imp: ImportRecord }) {
  const { t } = useTranslation();
  const saveMapping = useSaveMapping(imp.id);
  const validate = useValidate(imp.id);
  const [mapping, setMapping] = useState<Record<string, string>>(imp.column_mapping ?? {});
  const fields = [...imp.required_fields, ...imp.optional_fields];
  const busy = saveMapping.isPending || validate.isPending;

  const run = () => {
    saveMapping.mutate(mapping, { onSuccess: () => validate.mutate() });
  };

  return (
    <section aria-labelledby="mapping-heading" className="flex flex-col gap-3">
      <h3 id="mapping-heading" className="font-semibold">{t('dm.mappingHeading')}</h3>
      <p className="text-sm text-muted-foreground">{t('dm.mappingIntro')}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="mapping">
        {fields.map((field) => {
          const required = imp.required_fields.includes(field);
          return (
            <SelectField key={field} value={mapping[field] ?? ''}
              label={`${field}${required ? ` (${t('dm.required')})` : ''}`}
              onValueChange={(v) => setMapping((m) => ({ ...m, [field]: v }))}
              options={[{ value: '', label: t('dm.notMapped') }, ...imp.header.map((h) => ({ value: h, label: h }))]} />
          );
        })}
      </div>
      <ErrorText error={saveMapping.error ?? validate.error} />
      <Button onClick={run} disabled={busy} className="w-fit" data-testid="validate-button">
        {busy ? t('dm.working') : t('dm.saveAndValidate')}
      </Button>
      {busy ? (
        <ProgressBar className="max-w-sm"
          label={saveMapping.isPending ? t('dm.progressMapping') : t('dm.progressValidate')} />
      ) : null}
    </section>
  );
}

function Summary({ imp }: { imp: ImportRecord }) {
  const { t } = useTranslation();
  const items: Array<[string, number | null, string]> = [
    [t('dm.valid'), imp.valid_row_count, 'valid'],
    [t('dm.warnings'), imp.warning_row_count, 'warning'],
    [t('dm.rejectedRows'), imp.rejected_row_count, 'rejected'],
  ];
  return (
    <section aria-labelledby="summary-heading">
      <h3 id="summary-heading" className="mb-2 font-semibold">{t('dm.summaryHeading')}</h3>
      <dl className="grid gap-3 sm:grid-cols-3" data-testid="validation-summary">
        {items.map(([label, n, key]) => (
          <div key={key} className="rounded-md border border-border bg-muted/40 p-3" data-count={key}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-2xl font-semibold" dir="ltr">{n ?? '—'}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ErrorPreview({ imp }: { imp: ImportRecord }) {
  const { t } = useTranslation();
  const [outcome, setOutcome] = useState<'rejected' | 'warning'>('rejected');
  const rows = useImportRows(imp.id, outcome, imp.row_count !== null);
  return (
    <section aria-labelledby="preview-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="preview-heading" className="font-semibold">{t('dm.previewHeading')}</h3>
        <a href={errorReportUrl(imp.id)} className={buttonVariants({ variant: 'outline', size: 'sm' })} download>
          <Download aria-hidden="true" />
          {t('dm.downloadErrors')}
        </a>
      </div>
      <p className="text-sm text-muted-foreground">{t('dm.previewIntro')}</p>
      <div role="group" aria-label={t('dm.previewHeading')} className="flex gap-2">
        {(['rejected', 'warning'] as const).map((o) => (
          <Button key={o} size="sm" variant={outcome === o ? 'default' : 'outline'} aria-pressed={outcome === o}
            onClick={() => setOutcome(o)}>
            {o === 'rejected' ? t('dm.showRejected') : t('dm.showWarnings')}
          </Button>
        ))}
      </div>
      {rows.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
      {rows.isError ? <StatePanel kind="error" detail={rows.error.message} /> : null}
      {rows.data && rows.data.rows.length === 0 ? <p className="text-sm text-muted-foreground">{t('dm.noIssues')}</p> : null}
      {rows.data && rows.data.rows.length > 0 ? (
        // Phones: one stacked item per issue. Wider screens: the table below.
        <ul className="flex flex-col gap-3 sm:hidden">
          {rows.data.rows.flatMap((row) =>
            row.issues.map((issue, i) => (
              <li key={`${row.row_number}-${i}`} className="rounded-md border border-border p-3 text-sm">
                <p className="font-medium">
                  {t('dm.rowNumber')} <span dir="ltr">{row.row_number}</span>
                  {issue.field ? <span className="font-mono text-xs text-muted-foreground" dir="ltr"> · {issue.field}</span> : null}
                </p>
                {issue.value ? (
                  <p className="text-xs text-muted-foreground">
                    {t('dm.originalValue')}: <span className="font-mono break-all" dir="ltr">{issue.value}</span>
                  </p>
                ) : null}
                <p className="mt-1 break-words" lang="en" dir="ltr">{issue.message}</p>
              </li>
            )),
          )}
        </ul>
      ) : null}
      {rows.data && rows.data.rows.length > 0 ? (
        <div className="relative hidden overflow-x-auto sm:block">
          <table className="w-full text-sm" data-testid="error-preview">
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.rowNumber')}</th>
                <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.field')}</th>
                <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.originalValue')}</th>
                <th scope="col" className="py-2 text-start font-medium">{t('dm.reason')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.rows.flatMap((row) =>
                row.issues.map((issue, i) => (
                  <tr key={`${row.row_number}-${i}`} className="border-b border-border align-top last:border-0">
                    <td className="py-2 pe-3 tabular-nums" dir="ltr">{row.row_number}</td>
                    <td className="py-2 pe-3 font-mono text-xs" dir="ltr">{issue.field ?? '—'}</td>
                    <td className="py-2 pe-3 font-mono text-xs" dir="ltr">{issue.value ?? ''}</td>
                    <td className="py-2" lang="en" dir="ltr">
                      <span className="font-mono text-xs text-muted-foreground">{issue.code}</span>
                      <br />
                      {issue.message}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function ApproveStep({ imp, me }: { imp: ImportRecord; me: Me }) {
  const { t } = useTranslation();
  const approve = useApprove(imp.id);
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState('');
  const rejected = imp.rejected_row_count ?? 0;
  const noteId = useId();
  if (!hasPermission(me, 'import.approve')) {
    return <p className="text-sm text-muted-foreground">{t('dm.approveNeedsGrant')}</p>;
  }
  return (
    <section aria-labelledby="approve-heading" className="flex flex-col gap-3">
      <h3 id="approve-heading" className="font-semibold">{t('dm.approveHeading')}</h3>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-1 size-4"
          data-testid="approve-ack" />
        {t('dm.approveAck', { n: rejected })}
      </label>
      <label htmlFor={noteId} className="text-xs font-medium text-muted-foreground">{t('dm.approveNote')}</label>
      <textarea id={noteId} value={note} onChange={(e) => setNote(e.target.value)} rows={2}
        className="rounded-md border border-border-strong bg-card p-2 text-sm" />
      <ErrorText error={approve.error} />
      <Button className="w-fit" disabled={!ack || approve.isPending} data-testid="approve-button"
        onClick={() => approve.mutate({ acknowledged: rejected, note })}>
        <ShieldCheck aria-hidden="true" />
        {t('dm.approveSubmit')}
      </Button>
    </section>
  );
}

function PublishStep({ imp, me }: { imp: ImportRecord; me: Me }) {
  const { t } = useTranslation();
  const publish = usePublish(imp.id);
  if (!hasPermission(me, 'import.publish')) {
    return <p className="text-sm text-muted-foreground">{t('dm.publishNeedsGrant')}</p>;
  }
  return (
    <section aria-labelledby="publish-heading" className="flex flex-col gap-3">
      <h3 id="publish-heading" className="font-semibold">{t('dm.publishHeading')}</h3>
      <p className="text-sm text-muted-foreground">{t('dm.publishIntro')}</p>
      <ErrorText error={publish.error} />
      <Button className="w-fit" disabled={publish.isPending} onClick={() => publish.mutate()} data-testid="publish-button">
        {publish.isPending ? t('dm.working') : t('dm.publishSubmit', { label: imp.version.label })}
      </Button>
      {publish.isPending ? <ProgressBar label={t('dm.progressPublish')} className="max-w-sm" /> : null}
    </section>
  );
}

function RejectControl({ imp }: { imp: ImportRecord }) {
  const { t } = useTranslation();
  const reject = useReject(imp.id);
  const [reason, setReason] = useState('');
  const [open, setOpen] = useState(false);
  if (!open) {
    return <Button variant="ghost" size="sm" className="w-fit" onClick={() => setOpen(true)}>{t('dm.reject')}</Button>;
  }
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); reject.mutate(reason); }}>
      <TextField label={t('dm.rejectReason')} value={reason} onChange={setReason} required />
      <Button type="submit" variant="outline" size="sm" disabled={!reason || reject.isPending}>{t('dm.reject')}</Button>
      <ErrorText error={reject.error} />
    </form>
  );
}

function ImportDetail({ id, me, onBack }: { id: string; me: Me; onBack: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const query = useImport(id);
  if (query.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (query.isError) return <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />;
  const imp = query.data;
  const status = imp.version.status;
  const open = status === 'draft' || status === 'validated' || status === 'approved';

  return (
    <Card data-testid="import-detail">
      <CardHeader>
        <Button variant="ghost" size="sm" className="-ms-2 mb-2 w-fit" onClick={onBack}>
          <ArrowLeft aria-hidden="true" className="rtl:-scale-x-100" />
          {t('dm.back')}
        </Button>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle>
            <span dir="ltr">{imp.original_filename}</span> · <span dir="ltr">{imp.version.label}</span>
          </CardTitle>
          <div className="flex gap-2">
            <DataModeBadge mode={imp.data_mode} />
            <StatusBadge status={status} />
          </div>
        </div>
        <CardDescription>{imp.source_title}</CardDescription>
        <div className="mt-3"><Stepper status={status} /></div>
      </CardHeader>
      <CardContent className="flex flex-col gap-8">
        {imp.last_error_code ? <p role="alert" className="text-sm text-destructive">{t('dm.lastError')}</p> : null}
        {status === 'rejected' ? (
          <p className="text-sm">{t('dm.rejectedNote', { reason: imp.rejection_reason ?? '' })}</p>
        ) : null}
        {status === 'draft' ? <MappingStep key={JSON.stringify(imp.column_mapping)} imp={imp} /> : null}
        {status === 'validated' ? (
          // After validation the mapping stays editable but out of the way of the review.
          <details className="rounded-md border border-border p-4">
            <summary className="cursor-pointer text-sm font-medium">{t('dm.mappingHeading')}</summary>
            <div className="mt-4"><MappingStep key={JSON.stringify(imp.column_mapping)} imp={imp} /></div>
          </details>
        ) : null}
        {imp.row_count !== null ? <Summary imp={imp} /> : null}
        {imp.row_count !== null ? <ErrorPreview imp={imp} /> : null}
        {status === 'validated' ? <ApproveStep imp={imp} me={me} /> : null}
        {status === 'approved' ? <PublishStep imp={imp} me={me} /> : null}
        {status === 'published' ? (
          <p role="status" className="text-sm font-medium text-verified-foreground" data-testid="published-note">
            {t('dm.published', { n: (imp.valid_row_count ?? 0) + (imp.warning_row_count ?? 0) })}{' '}
            <Link to={{ ...to('/workspace'), search: `?mode=${imp.data_mode}` }} className="underline">
              {t('dm.viewData')}
            </Link>
          </p>
        ) : null}
        {open && hasPermission(me, 'import.reject') ? <RejectControl imp={imp} /> : null}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ page

function Workspace({ me }: { me: Me }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selected = params.get('import');
  const select = (id: string | null) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set('import', id);
      else next.delete('import');
      return next;
    });
  const synthetic = useSources('synthetic');
  const verified = useSources('verified_source');
  const imports = useImports();
  const [registering, setRegistering] = useState(false);
  const sources = [...(synthetic.data ?? []), ...(verified.data ?? [])];

  if (selected) return <ImportDetail id={selected} me={me} onBack={() => select(null)} />;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>{t('dm.sourcesHeading')}</CardTitle>
            {hasPermission(me, 'source.register') ? (
              <Button variant="outline" size="sm" onClick={() => setRegistering((v) => !v)} aria-expanded={registering}>
                {t('dm.registerSource')}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {registering ? <RegisterSourceForm onDone={() => setRegistering(false)} /> : null}
          {sources.length === 0 ? <p className="text-sm text-muted-foreground">{t('dm.noSources')}</p> : (
            <ul className="flex flex-col gap-2 text-sm">
              {sources.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2">
                  <DataModeBadge mode={s.data_mode} />
                  <span className="font-medium">{s.dataset_title}</span>
                  {s.publisher ? <span className="text-muted-foreground">· {s.publisher}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {hasPermission(me, 'import.create') ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><FileUp aria-hidden="true" className="size-4" />{t('dm.uploadHeading')}</CardTitle>
          </CardHeader>
          <CardContent><UploadForm sources={sources} onUploaded={select} /></CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>{t('dm.importsHeading')}</CardTitle></CardHeader>
        <CardContent>
          {imports.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
          {imports.isError ? <StatePanel kind="error" detail={imports.error.message} /> : null}
          {imports.data?.length === 0 ? <p className="text-sm text-muted-foreground">{t('dm.noImports')}</p> : null}
          {imports.data && imports.data.length > 0 ? (
            <div className="relative overflow-x-auto">
              <table className="w-full text-sm" data-testid="imports-table">
                <thead>
                  <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                    <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.fileLabel')}</th>
                    <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.source')}</th>
                    <th scope="col" className="py-2 pe-3 text-start font-medium">{t('dm.status')}</th>
                    <th scope="col" className="py-2 text-end font-medium">{t('dm.rows')}</th>
                  </tr>
                </thead>
                <tbody>
                  {imports.data.map((imp) => (
                    <tr key={imp.id} className="border-b border-border last:border-0">
                      <td className="py-2 pe-3">
                        <button type="button" className="text-start text-primary underline underline-offset-2"
                          onClick={() => select(imp.id)} dir="ltr">
                          {imp.original_filename} · {imp.version.label}
                        </button>
                      </td>
                      <td className="py-2 pe-3">{imp.source_title}</td>
                      <td className="py-2 pe-3"><StatusBadge status={imp.version.status} /></td>
                      <td className="py-2 text-end tabular-nums" dir="ltr">{imp.row_count ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

/** Authorized area. The server enforces every permission; this page only reflects them. */
export function DataManagementPage() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const me = useMe();

  let body: ReactNode;
  if (adapterKind !== 'http') {
    body = (
      <StatePanel kind="restricted">
        <p className="text-sm text-muted-foreground">{t('dm.requiresApi')}</p>
      </StatePanel>
    );
  } else if (me.isPending) {
    body = <StatePanel kind="loading" skeleton="lines" />;
  } else if (me.isError) {
    body = <StatePanel kind="error" detail={me.error.message} onRetry={() => void me.refetch()} />;
  } else if (!me.data.authenticated) {
    body = (
      <StatePanel kind="restricted">
        <p className="text-sm text-muted-foreground">{t('dm.signInPrompt')}</p>
        <Link to={to('/sign-in')} className={cn(buttonVariants({ size: 'sm' }), 'mt-3 w-fit')}>{t('auth.signIn')}</Link>
      </StatePanel>
    );
  } else if (!hasPermission(me.data, 'import.read') && !hasPermission(me.data, 'research.review')
    && !hasPermission(me.data, 'user.manage')) {
    body = (
      <StatePanel kind="restricted">
        <p className="text-sm text-muted-foreground">{t('dm.noPermission')}</p>
      </StatePanel>
    );
  } else {
    body = (
      <>
        {hasPermission(me.data, 'import.read') || hasPermission(me.data, 'user.manage') ? (
          <div className="mb-8"><SourceFeedsAdmin canManage={hasPermission(me.data, 'user.manage')} /></div>
        ) : null}
        {hasPermission(me.data, 'import.read') ? <Workspace me={me.data} /> : null}
        {hasPermission(me.data, 'research.review') ? <ResearchQueue /> : null}
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('pages.dataManagement.title')} intro={t('pages.dataManagement.intro')}
        eyebrow={t('nav.authorizedOnly')} />
      {body}
    </>
  );
}
