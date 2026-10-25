import { Check, Copy, Download, ExternalLink, X } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useResearchCandidates, useReviewCandidate, type CandidateStatus, type ResearchCandidate } from '@/api/assistant';
import { apiBaseUrl } from '@/api/config';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

const STATUSES = ['pending', 'conflict', 'approved', 'accepted', 'rejected', 'duplicate'] as const;

function CheckRow({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <li className="flex items-start gap-1.5">
      {ok === null ? <span aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-center">–</span>
        : ok ? <Check aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-primary" />
          : <X aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-destructive" />}
      <span>{label}</span>
    </li>
  );
}

function Candidate({ item }: { item: ResearchCandidate }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const review = useReviewCandidate();
  const [note, setNote] = useState('');
  const noteId = useId();
  const checks = item.checks as {
    official_source?: boolean; in_scope?: boolean; has_publication_date?: boolean; comparable_period?: boolean;
    unit_matches_text?: boolean; same_figure_queued?: number;
    published_matches?: { relation: string; value: string | null }[];
  };
  const matches = checks.published_matches ?? [];
  const date = (d: string | null) => (d ? formatPeriod(d.slice(0, 10), d.slice(0, 10), language) : '—');
  const decide = (decision: Exclude<CandidateStatus, 'pending'>) => review.mutate({ id: item.id, decision, note });
  return (
    <li className="surface-card flex flex-col gap-3 p-4 text-sm" data-testid="research-candidate" data-status={item.status}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold" dir="auto">{item.indicator}</p>
          <p className="text-muted-foreground" dir="auto">{item.geography} · {item.period_label}</p>
        </div>
        <p className="text-lg font-semibold tabular-nums" dir="ltr">{item.value_text} <span className="text-sm font-normal">{item.unit}</span></p>
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">{t('research.publisher')}</dt>
        <dd className="flex flex-wrap items-center gap-1.5">
          <bdi>{item.publisher}</bdi>
          <Badge variant={item.source_class === 'secondary' ? 'sand' : 'verified'}>{t(`web.sourceClass.${item.source_class}`)}</Badge>
        </dd>
        <dt className="text-muted-foreground">{t('research.published')}</dt><dd>{date(item.publication_date)}</dd>
        <dt className="text-muted-foreground">{t('research.retrieved')}</dt><dd>{date(item.retrieved_at)}</dd>
        <dt className="text-muted-foreground">{t('research.period')}</dt>
        <dd dir="ltr">{item.period_start ?? '?'} – {item.period_end ?? '?'}</dd>
      </dl>
      <a href={item.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-xs text-primary underline underline-offset-2">
        <bdi>{item.source_title}</bdi><ExternalLink aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
      </a>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">{t('web.excerpt')}</summary>
        <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap" dir="auto">{item.excerpt}</p>
      </details>
      {item.validation_reasons.length ? (
        <p className="text-xs" data-testid="research-reasons">
          <span className="font-semibold">{t('research.reasons')}: </span>
          <span dir="ltr" className="font-mono">{item.validation_reasons.join(' · ')}</span>
        </p>
      ) : null}
      {item.status === 'approved' && item.observation_id ? (
        <p className="text-xs text-muted-foreground" data-testid="research-saved-record">
          {t(item.decided_by === 'reviewer' ? 'research.savedByReviewer' : 'research.savedByValidation')}
          {' · '}{t('research.record')}: <span dir="ltr" className="font-mono">{item.observation_id}</span>
        </p>
      ) : null}
      {item.status === 'pending' || item.status === 'conflict' ? (
        <>
          <div>
            <p className="mb-1 text-xs font-semibold">{t('research.checks')}</p>
            <ul className="grid gap-1 text-xs sm:grid-cols-2">
              <CheckRow ok={Boolean(checks.official_source)} label={t('research.check.official')} />
              <CheckRow ok={Boolean(checks.in_scope)} label={t('research.check.inScope')} />
              <CheckRow ok={Boolean(checks.has_publication_date)} label={t('research.check.pubDate')} />
              <CheckRow ok={Boolean(checks.comparable_period)} label={t('research.check.comparable')} />
              <CheckRow ok={checks.unit_matches_text ?? null} label={t('research.check.unit')} />
              {matches.some((m) => m.relation === 'duplicate') ? <CheckRow ok={false} label={t('research.check.duplicate')} /> : null}
              {matches.some((m) => m.relation !== 'duplicate') ? <CheckRow ok={false} label={t('research.check.revision')} /> : null}
              {checks.same_figure_queued ? <CheckRow ok={null} label={`${t('research.check.queued')}: ${checks.same_figure_queued}`} /> : null}
            </ul>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={noteId} className="text-xs font-medium">{t('research.note')}</label>
            <textarea id={noteId} rows={2} value={note} onChange={(e) => setNote(e.target.value)} dir="auto"
              className="rounded-md border border-border-strong bg-card px-3 py-2 text-sm" />
          </div>
          {review.error ? <p role="alert" className="text-xs text-destructive">{review.error.message}</p> : null}
          <div className="flex flex-wrap gap-2">
            {item.can_save ? (
              <Button size="sm" onClick={() => decide('approved')} disabled={review.isPending || !note.trim()} data-testid="research-approve-save">
                <Check aria-hidden="true" />{t(item.status === 'conflict' ? 'research.approveRevision' : 'research.approveSave')}
              </Button>
            ) : null}
            <Button size="sm" variant={item.can_save ? 'outline' : 'default'} onClick={() => decide('accepted')} disabled={review.isPending || !note.trim()} data-testid="research-accept">
              <Check aria-hidden="true" />{t('research.accept')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => decide('duplicate')} disabled={review.isPending}>
              <Copy aria-hidden="true" />{t('research.markDuplicate')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => decide('rejected')} disabled={review.isPending}>
              <X aria-hidden="true" />{t('research.reject')}
            </Button>
          </div>
        </>
      ) : item.review_note ? <p className="text-xs text-muted-foreground" dir="auto">{item.review_note}</p> : null}
    </li>
  );
}

/** Data managers review figures found on the web. Nothing here publishes data. */
export function ResearchQueue() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<CandidateStatus>('pending');
  const items = useResearchCandidates(status, true);
  return (
    <section aria-labelledby="research-heading" className="mt-10 flex flex-col gap-4" data-testid="research-queue">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-2xl">
          <h2 id="research-heading" className="text-xl font-semibold">{t('research.title')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('research.intro')}</p>
        </div>
        <a href={`${apiBaseUrl}/research/candidates/accepted.csv`} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
          <Download aria-hidden="true" />{t('research.downloadAccepted')}
        </a>
      </div>
      <Segmented label={t('research.tab')} value={status} onChange={setStatus} testId="research-status"
        options={STATUSES.map((s) => ({ value: s, label: t(`research.status.${s}`) }))} />
      {items.isPending ? <StatePanel kind="loading" skeleton="lines" /> : items.isError ? (
        <StatePanel kind="error" detail={items.error.message} onRetry={() => void items.refetch()} />
      ) : items.data.length === 0 ? <p className="text-sm text-muted-foreground">{t('research.empty')}</p> : (
        <ul className="grid gap-4 lg:grid-cols-2">{items.data.map((c) => <Candidate key={c.id} item={c} />)}</ul>
      )}
    </section>
  );
}
