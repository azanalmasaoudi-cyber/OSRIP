import { CalendarClock, Check, ExternalLink, X } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useOutlookReview, useReviewOutlookItem, type OutlookItem, type OutlookReviewStatus } from '@/api/outlook';
import { StatePanel } from '@/components/common/StatePanel';
import { OutlookClassBadge, outlookValue } from '@/components/sector/SectorOutlook';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

const STATUSES = ['pending', 'approved', 'rejected'] as const satisfies readonly OutlookReviewStatus[];
const SECTIONS = ['electricity', 'water'] as const;

function ReviewItem({ item }: { item: OutlookItem }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const review = useReviewOutlookItem();
  const [note, setNote] = useState('');
  const noteId = useId();
  const shown = outlookValue(item, language);
  const decide = (decision: 'approved' | 'rejected') => review.mutate({ id: item.id, decision, note: note.trim() });
  return (
    <li className="surface-card flex flex-col gap-3 p-4 text-sm" data-testid="outlook-review-item"
      data-metric={item.metric.code} data-year={item.year} data-status={item.review_status}>
      <div className="flex flex-wrap items-center gap-2">
        <OutlookClassBadge item={item} />
        <span className="font-semibold tabular-nums" dir="ltr">{item.year}</span>
        <span className="text-xs text-muted-foreground" dir="auto">{item.scope[language]}</span>
      </div>
      <p className="text-base">
        <span className="font-medium">{language === 'ar' ? item.metric.ar : item.metric.en}</span>
        {shown ? <>: <bdi dir="ltr" className="tabular-nums">{shown}</bdi></> : (
          <span className="inline-flex items-center gap-1 text-sm text-muted-foreground"> <CalendarClock aria-hidden="true" className="size-3.5" />{t('outlook.dateOnly')}</span>
        )}
      </p>
      {item.status_note ? <p className="text-muted-foreground" dir="auto">{item.status_note[language]}</p> : null}
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">{t('outlook.source')}</dt>
        <dd>
          <a href={item.source.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-primary underline underline-offset-2">
            <bdi>{item.source.title}</bdi><ExternalLink aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
          </a>
          {' · '}<bdi>{item.source.publisher}</bdi>
        </dd>
        <dt className="text-muted-foreground">{t('outlook.review.page')}</dt>
        <dd dir="ltr" className="text-start">{item.source.locator}</dd>
        <dt className="text-muted-foreground">{t('outlook.review.retrievedOn')}</dt>
        <dd>{formatDate(item.source.retrieved_on, language)}</dd>
        {item.source.sha256 ? (
          <>
            <dt className="text-muted-foreground">{t('outlook.review.hash')}</dt>
            <dd dir="ltr" className="break-all text-start font-mono" title={item.source.sha256}>{item.source.sha256.slice(0, 16)}…</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">{t('outlook.review.batch')}</dt>
        <dd dir="ltr" className="text-start">{item.batch}</dd>
      </dl>
      {item.review_status === 'pending' ? (
        <>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={noteId} className="text-xs font-medium">{t('outlook.review.note')}</label>
            <textarea id={noteId} rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} dir="auto"
              data-testid="outlook-review-note" className="rounded-md border border-border-strong bg-card px-3 py-2 text-sm" />
          </div>
          {review.error ? <p role="alert" className="text-xs text-destructive">{review.error.message}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => decide('approved')} disabled={review.isPending} data-testid="outlook-approve">
              <Check aria-hidden="true" />{t('outlook.review.approve')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => decide('rejected')} disabled={review.isPending || !note.trim()}
              data-testid="outlook-reject">
              <X aria-hidden="true" />{t('outlook.review.reject')}
            </Button>
          </div>
        </>
      ) : (
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="outlook-review-decision">
          <Badge variant={item.review_status === 'approved' ? 'verified' : 'accent'}>{t(`outlook.review.statuses.${item.review_status}`)}</Badge>
          {item.reviewed_at ? <span>{formatDateTime(item.reviewed_at, language)}</span> : null}
          {item.review_note ? <span dir="auto">· {item.review_note}</span> : null}
        </p>
      )}
    </li>
  );
}

/**
 * The official outlook's review queue in Data Management: each staged forecast, target, plan or
 * option with its kind of evidence and source page, approved or rejected one at a time. Only
 * approved items reach the sectors and Al Mulhim; the server checks the permission and records
 * every decision.
 */
export function OutlookReview() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<OutlookReviewStatus>('pending');
  const query = useOutlookReview();
  const items = query.data?.items ?? [];
  const count = (s: OutlookReviewStatus) => items.filter((i) => i.review_status === s).length;
  const shown = items.filter((i) => i.review_status === status);
  return (
    <section aria-labelledby="outlook-review-heading" className="mt-10 flex flex-col gap-4" data-testid="outlook-review">
      <div className="max-w-2xl">
        <h2 id="outlook-review-heading" className="text-xl font-semibold">{t('outlook.review.title')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('outlook.review.intro')}</p>
      </div>
      <Segmented label={t('outlook.review.status')} value={status} onChange={setStatus} testId="outlook-review-status"
        options={STATUSES.map((s) => ({ value: s, label: t(`outlook.review.statuses.${s}`), note: query.data ? `(${count(s)})` : undefined }))} />
      {query.isPending ? <StatePanel kind="loading" skeleton="lines" /> : query.isError ? (
        <StatePanel kind="error" error={query.error} onRetry={() => void query.refetch()} />
      ) : shown.length === 0 ? <p className="text-sm text-muted-foreground" role="status">{t('outlook.review.empty')}</p> : (
        SECTIONS.filter((section) => shown.some((i) => i.section === section)).map((section) => (
          <div key={section} className="flex flex-col gap-2" data-testid="outlook-review-section" data-section={section}>
            <h3 className="text-base font-semibold">{t(`outlook.review.sections.${section}`)}</h3>
            <ul className="grid gap-4 lg:grid-cols-2">
              {shown.filter((i) => i.section === section).map((i) => <ReviewItem key={i.id} item={i} />)}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
