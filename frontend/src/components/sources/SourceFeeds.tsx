import { CalendarClock, CloudDownload, FileUp, RefreshCw, ShieldAlert } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import {
  useCheckFeed,
  useFeedReleases,
  useFeedRuns,
  useSourceFeeds,
  useUpdateFeed,
  useUploadWorkbook,
  type SourceFeed,
} from '@/api/sourceSync';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Official statistics feeds. Three moments are always shown apart, because a successful check
 * does not mean anything new was published: the last successful check (OSRIP's), the latest
 * release (the publisher's date) and the latest observation period (what the figures cover).
 */

const INTERVALS = [24, 48, 72, 168] as const;

function FeedFacts({ feed }: { feed: SourceFeed }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const release = feed.latest_release;
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-3" data-testid="feed-facts">
      <div className="rounded-md border border-border p-3" data-testid="feed-last-success">
        <dt className="text-xs font-medium text-muted-foreground">{t('feeds.lastSuccess')}</dt>
        <dd className="font-medium">{feed.last_success_at ? formatDateTime(feed.last_success_at, language) : t('feeds.never')}</dd>
        {feed.last_checked_at && feed.last_status ? (
          <dd className="text-xs text-muted-foreground">{t('feeds.lastResult', { status: t(`feeds.status.${feed.last_status}`, { defaultValue: feed.last_status }) })}</dd>
        ) : null}
      </div>
      <div className="rounded-md border border-border p-3" data-testid="feed-latest-release">
        <dt className="text-xs font-medium text-muted-foreground">{t('feeds.latestRelease')}</dt>
        <dd className="font-medium">
          {release ? ((language === 'ar' ? release.title_ar : null) ?? release.title_en) : t('feeds.noRelease')}
        </dd>
        {release?.published_at ? <dd className="text-xs text-muted-foreground">{t('feeds.publishedOn', { date: formatDate(release.published_at, language) })}</dd> : null}
      </div>
      <div className="rounded-md border border-border p-3" data-testid="feed-latest-observation">
        <dt className="text-xs font-medium text-muted-foreground">{t('feeds.latestObservation')}</dt>
        <dd className="font-medium">{feed.latest_observation ? formatDate(feed.latest_observation.period_end, language) : t('feeds.noObservation')}</dd>
        {feed.latest_observation ? <dd className="text-xs text-muted-foreground">{t('feeds.periodEnd')}</dd> : null}
      </div>
    </dl>
  );
}

function AccessBadge({ feed }: { feed: SourceFeed }) {
  const { t } = useTranslation();
  return feed.access === 'public_listing'
    ? <Badge variant="verified">{t('feeds.access.public_listing')}</Badge>
    : <Badge variant="sand"><ShieldAlert aria-hidden="true" className="me-1 size-3.5" />{t('feeds.access.requires_access')}</Badge>;
}

/** The public summary (Sources page). */
export function PublicFeedStatus() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const feeds = useSourceFeeds();
  if (feeds.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (feeds.isError) return <StatePanel kind="error" detail={feeds.error.message} onRetry={() => void feeds.refetch()} />;
  return (
    <ul className="flex flex-col gap-4" data-testid="public-feeds">
      {feeds.data.map((feed) => (
        <li key={feed.code} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4" data-testid="public-feed" data-feed={feed.code}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{feed.title[language]}</h3>
            <span className="flex flex-wrap items-center gap-2">
              <AccessBadge feed={feed} />
              {feed.access === 'public_listing' ? (
                <Badge variant={feed.enabled ? 'outline' : 'muted'}>{feed.enabled ? t('feeds.scheduled', { hours: feed.check_interval_hours }) : t('feeds.notScheduled')}</Badge>
              ) : null}
            </span>
          </div>
          {feed.access === 'public_listing' ? <FeedFacts feed={feed} /> : null}
          {feed.notes ? <p className="text-xs text-muted-foreground">{feed.notes[language]}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function FeedAdmin({ feed, canManage }: { feed: SourceFeed; canManage: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const update = useUpdateFeed(feed.code);
  const check = useCheckFeed(feed.code);
  const upload = useUploadWorkbook(feed.code);
  const runs = useFeedRuns(feed.code, feed.access === 'public_listing');
  const releases = useFeedReleases(feed.code, feed.access === 'public_listing');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [fileUrl, setFileUrl] = useState('');
  const [publishedOn, setPublishedOn] = useState('');
  const result = check.data ?? upload.data;
  const submitUpload = (e: FormEvent) => {
    e.preventDefault();
    if (file) upload.mutate({ file, title, fileUrl, publishedOn });
  };
  const publicListing = feed.access === 'public_listing';
  // While a change is being saved, the controls show the value asked for.
  const [asked, setAsked] = useState<{ enabled?: boolean; auto_publish?: boolean; check_interval_hours?: number } | null>(null);
  const save = (change: { enabled?: boolean; auto_publish?: boolean; check_interval_hours?: number }) => {
    setAsked(change);
    update.mutate(change, { onSettled: () => setAsked(null) });
  };
  const enabled = asked?.enabled ?? feed.enabled;
  const autoPublish = asked?.auto_publish ?? Boolean(feed.auto_publish);
  const interval = asked?.check_interval_hours ?? feed.check_interval_hours;

  return (
    <section aria-labelledby={`feed-${feed.code}`} className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 sm:p-5" data-testid="feed-admin" data-feed={feed.code}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id={`feed-${feed.code}`} className="text-base font-semibold">{feed.title[language]}</h3>
          <p className="text-xs text-muted-foreground">{feed.publisher}</p>
        </div>
        <AccessBadge feed={feed} />
      </div>
      {publicListing ? <FeedFacts feed={feed} /> : null}
      {feed.notes ? <p className="text-sm text-muted-foreground">{feed.notes[language]}</p> : null}
      {feed.last_error ? <p role="status" className="text-sm text-destructive" data-testid="feed-last-error">{feed.last_error}</p> : null}

      {canManage && publicListing ? (
        <div className="flex flex-col gap-3 rounded-md border border-border p-3" data-testid="feed-schedule">
          <h4 className="flex items-center gap-2 text-sm font-semibold"><CalendarClock aria-hidden="true" className="size-4" />{t('feeds.schedule')}</h4>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={enabled} disabled={update.isPending}
              onChange={(e) => save({ enabled: e.target.checked })} data-testid="feed-enabled" />
            {t('feeds.enabled')}
          </label>
          <SelectField label={t('feeds.interval')} className="max-w-xs" value={String(interval)}
            onValueChange={(v) => save({ check_interval_hours: Number(v) })}
            options={[...new Set([interval, ...INTERVALS])].sort((a, b) => a - b)
              .map((h) => ({ value: String(h), label: t('feeds.everyHours', { hours: h }) }))} data-testid="feed-interval" />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={autoPublish} disabled={update.isPending}
              onChange={(e) => save({ auto_publish: e.target.checked })} data-testid="feed-auto-publish" />
            <span>{t('feeds.autoPublish')}<span className="block text-xs text-muted-foreground">{t('feeds.autoPublishNote')}</span></span>
          </label>
          {feed.enabled && feed.next_check_at ? (
            <p className="text-xs text-muted-foreground">{t('feeds.nextCheck', { time: formatDateTime(feed.next_check_at, language) })}</p>
          ) : null}
          <p className="text-xs text-muted-foreground">{t('feeds.workerNote')}</p>
          {update.error ? <p role="alert" className="text-sm text-destructive">{update.error.message}</p> : null}
        </div>
      ) : null}

      {canManage ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => check.mutate()} disabled={check.isPending} data-testid="feed-check-now">
            <RefreshCw aria-hidden="true" className={check.isPending ? 'animate-spin motion-reduce:animate-none' : undefined} />
            {check.isPending ? t('feeds.checking') : t('feeds.checkNow')}
          </Button>
          {check.error ? <span role="alert" className="text-sm text-destructive">{check.error.message}</span> : null}
        </div>
      ) : null}
      {result ? (
        <p role="status" className="rounded-md border border-border bg-muted/40 p-2 text-sm" data-testid="feed-result" data-status={result.status}>
          <span className="font-medium">{t(`feeds.status.${result.status}`, { defaultValue: result.status })}</span>
          {result.message ? <> — {result.message}</> : null}
        </p>
      ) : null}

      {canManage && publicListing ? (
        <details className="rounded-md border border-border p-3">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold"><FileUp aria-hidden="true" className="size-4" />{t('feeds.uploadHeading')}</summary>
          <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={submitUpload} data-testid="feed-upload">
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('feeds.uploadNote')}</p>
            <label className="flex flex-col gap-1 text-xs font-medium sm:col-span-2">{t('feeds.uploadFile')}
              <input type="file" accept=".xlsx" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">{t('feeds.uploadTitle')}
              <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Monthly Statistical Bulletin :October 2026"
                className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">{t('feeds.uploadUrl')}
              <input required type="url" value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} pattern="https://api\.ncsi\.gov\.om/uploads/.*"
                placeholder="https://api.ncsi.gov.om/uploads/xls/…" className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">{t('feeds.uploadDate')}
              <input type="date" value={publishedOn} onChange={(e) => setPublishedOn(e.target.value)}
                className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
            </label>
            <div className="flex items-end">
              <Button type="submit" size="sm" disabled={upload.isPending || !file}>
                <CloudDownload aria-hidden="true" />{t('feeds.uploadSubmit')}
              </Button>
            </div>
            {upload.error ? <p role="alert" className="text-sm text-destructive sm:col-span-2">{upload.error.message}</p> : null}
          </form>
        </details>
      ) : null}

      {publicListing ? (
        <details className="rounded-md border border-border p-3" data-testid="feed-releases">
          <summary className="cursor-pointer text-sm font-semibold">{t('feeds.releasesHeading')}</summary>
          {releases.data?.length ? (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[36rem] text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th scope="col" className="py-1 pe-3 text-start font-medium">{t('feeds.release')}</th>
                    <th scope="col" className="py-1 pe-3 text-start font-medium">{t('feeds.published')}</th>
                    <th scope="col" className="py-1 pe-3 text-start font-medium">{t('feeds.result')}</th>
                    <th scope="col" className="py-1 text-end font-medium">{t('feeds.counts')}</th>
                  </tr>
                </thead>
                <tbody>
                  {releases.data.map((r) => (
                    <tr key={r.id} className="border-t border-border align-top" data-testid="feed-release" data-status={r.status}>
                      <td className="py-1.5 pe-3">
                        {r.title_en}
                        {r.import_id ? (
                          <Link to={{ ...to('/data-management'), search: `?import=${r.import_id}` }} className="ms-2 text-xs text-primary underline">
                            {t('feeds.openImport')}
                          </Link>
                        ) : null}
                        {r.message ? <p className="text-xs text-muted-foreground">{r.message}</p> : null}
                      </td>
                      <td className="py-1.5 pe-3 whitespace-nowrap">{r.published_at ? formatDate(r.published_at, language) : '—'}</td>
                      <td className="py-1.5 pe-3">{t(`feeds.releaseStatus.${r.status}`, { defaultValue: r.status })}</td>
                      <td className="py-1.5 text-end tabular-nums" dir="ltr">{r.rows_new} / {r.rows_revised} / {r.rows_unchanged}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-xs text-muted-foreground">{t('feeds.countsNote')}</p>
            </div>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t('feeds.noReleases')}</p>}
        </details>
      ) : null}

      {publicListing ? (
        <details className="rounded-md border border-border p-3" data-testid="feed-log">
          <summary className="cursor-pointer text-sm font-semibold">{t('feeds.logHeading')}</summary>
          {runs.data?.length ? (
            <ul className="mt-3 flex flex-col gap-1.5 text-sm">
              {runs.data.map((r) => (
                <li key={r.id} className="flex flex-wrap gap-x-3" data-testid="feed-run" data-status={r.status}>
                  <span className="tabular-nums text-muted-foreground">{r.started_at ? formatDateTime(r.started_at, language) : ''}</span>
                  <span>{t(`feeds.trigger.${r.trigger}`, { defaultValue: r.trigger })}</span>
                  <span className="font-medium">{t(`feeds.status.${r.status}`, { defaultValue: r.status })}</span>
                  <span className="text-muted-foreground">{t('feeds.attempts', { n: r.attempts })}{r.http_status ? ` · HTTP ${r.http_status}` : ''}</span>
                  {r.message ? <span className="basis-full text-xs text-muted-foreground">{r.message}</span> : null}
                </li>
              ))}
            </ul>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t('feeds.noRuns')}</p>}
        </details>
      ) : null}
    </section>
  );
}

/** Data Management: every feed, with the schedule and actions for administrators. */
export function SourceFeedsAdmin({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const feeds = useSourceFeeds(true);
  return (
    <section aria-labelledby="feeds-heading" className="flex flex-col gap-3" data-testid="source-feeds-admin">
      <div>
        <h2 id="feeds-heading" className="text-lg font-semibold">{t('feeds.heading')}</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">{t('feeds.intro')}</p>
      </div>
      {feeds.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
      {feeds.isError ? <StatePanel kind="error" detail={feeds.error.message} onRetry={() => void feeds.refetch()} /> : null}
      {feeds.data?.map((feed) => <FeedAdmin key={feed.code} feed={feed} canManage={canManage} />)}
    </section>
  );
}
