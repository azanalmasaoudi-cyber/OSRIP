import { ArrowRight, BookOpen, ExternalLink, FlaskConical } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { useMyStudies } from '@/api/studies';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { seriesKey } from '@/domain/filters';
import type { Series } from '@/domain/types';
import { REVISION_STATUS_KEY } from '@/i18n/keys';
import { formatDate } from '@/lib/format';
import { sourceTitle } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** A dashboard card: title row (with an optional action) and body. */
export function DashboardCard({ title, icon, action, children, className, testId, labelledBy }: {
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
  labelledBy: string;
}) {
  return (
    <section aria-labelledby={labelledBy} className={cn('flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-4', className)}
      data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={labelledBy} className="flex items-center gap-2 text-sm font-semibold">{icon}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Studies of this browser session (the assistant's live studies) and, signed in, the latest
 * saved studies. Opening a session study shows it in the Study tab. */
export function RecentStudies({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated);
  const saved = useMyStudies(signedIn);
  const to = usePreservedSearch();
  const session = ui.studies.slice(0, 4);
  const stored = (saved.data ?? []).slice(0, 4);
  return (
    <DashboardCard title={t('workspace.recent.heading')} labelledBy="ws-recent" testId="recent-studies"
      icon={<FlaskConical aria-hidden="true" className="size-4 text-primary" />}
      action={<Link to={to('/studies')} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
        {t('workspace.recent.all')}<ArrowRight aria-hidden="true" className="size-3.5 rtl:-scale-x-100" /></Link>}>
      {session.length ? (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">{t('workspace.recent.session')}</p>
          <ul className="flex flex-col divide-y divide-border">
            {session.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                <span className="min-w-0 truncate text-sm" dir="auto" title={s.question}>{s.question || t('workspace.recent.untitled')}</span>
                <button type="button" onClick={() => onOpen(s.id)} aria-pressed={ui.activeStudy?.id === s.id}
                  className="shrink-0 rounded-md border border-border px-2 py-0.5 text-xs hover:bg-muted" data-testid="recent-study-open">
                  {t('workspace.recent.open')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {stored.length ? (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">{t('workspace.recent.saved')}</p>
          <ul className="flex flex-col divide-y divide-border">
            {stored.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                <Link to={to(`/studies/${s.id}`)} className="min-w-0 truncate text-sm hover:underline">{s.title[language]}</Link>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{formatDate(s.created_at, language)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {!session.length && !stored.length ? (
        <p className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs text-muted-foreground" data-testid="recent-studies-empty">
          {t('workspace.recent.none')} {signedIn ? null : t('workspace.recent.signIn')}
        </p>
      ) : null}
    </DashboardCard>
  );
}

/** Where the shown series come from: dataset, publisher (none for synthetic data), version and
 * retrieval date, one line per source. */
/** The latest observation with a value (else the latest one): what "latest" means here. */
function latestObservation(s: Series) {
  const valued = s.observations.filter((o) => o.value !== null);
  const pool = valued.length ? valued : s.observations;
  return pool.reduce<(typeof pool)[number] | undefined>((a, o) => (!a || o.periodEnd > a.periodEnd ? o : a), undefined);
}

/**
 * Data freshness and sources for the series shown: for each, the end of its latest period, its
 * unit, where it applies (the area, and the source's stated coverage), when the source was
 * published and retrieved, its review status, and the source's address. Most recent first; at
 * most six (the full list is on Sources).
 */
export function SourcesPanel({ series }: { series: readonly Series[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const latest = new Map(series.map((s) => [seriesKey(s), latestObservation(s)]));
  const unique = [...new Map(series.map((s) => [seriesKey(s), s])).values()]
    .sort((a, b) => (latest.get(seriesKey(b))?.periodEnd ?? '').localeCompare(latest.get(seriesKey(a))?.periodEnd ?? ''))
    .slice(0, 6);
  return (
    <DashboardCard title={t('workspace.sources.heading')} labelledBy="ws-sources" testId="workspace-sources"
      icon={<BookOpen aria-hidden="true" className="size-4 text-primary" />}
      action={<Link to={to('/sources')} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
        {t('workspace.sources.all')}<ArrowRight aria-hidden="true" className="size-3.5 rtl:-scale-x-100" /></Link>}>
      <p className="text-xs text-muted-foreground">{t('workspace.sources.note')}</p>
      {unique.length ? (
        <ul className="flex flex-col divide-y divide-border">
          {unique.map((s) => {
            const obs = latest.get(seriesKey(s));
            const revision = obs?.revisionStatus && obs.revisionStatus in REVISION_STATUS_KEY
              ? t(REVISION_STATUS_KEY[obs.revisionStatus]) : null;
            const scope = [s.area ? s.area.name[language] : t('filters.national'),
              s.area?.level === 'reporting_group' ? t('workspace.sources.group') : null].filter(Boolean).join(' · ');
            const dash = t('workspace.sources.notStated');
            return (
              <li key={seriesKey(s)} className="flex flex-col gap-1 py-2.5 text-sm" data-testid="workspace-source" data-indicator={s.indicatorCode}>
                <span className="font-medium">{s.name[language]}</span>
                <span className="text-xs"><bdi>{sourceTitle(s)}</bdi></span>
                <span className="text-xs text-muted-foreground">
                  {s.source.publisher ?? t('workspace.sources.publisherNone')}
                  {s.source.versionLabel ? ` · ${s.source.versionLabel}` : ''}
                </span>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs" data-testid="freshness">
                  <dt className="text-muted-foreground">{t('workspace.sources.periodEnd')}</dt>
                  <dd data-field="period_end">{obs ? formatDate(obs.periodEnd, language) : dash}{obs && !obs.periodComplete ? ` (${t('workspace.sources.partial')})` : ''}</dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.unit')}</dt>
                  <dd data-field="unit">{s.unit.label[language]}</dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.scope')}</dt>
                  <dd data-field="geographic_scope">{scope}{s.source.geographicCoverage ? <span className="block text-muted-foreground" dir="auto">{s.source.geographicCoverage}</span> : null}</dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.published')}</dt>
                  <dd data-field="publication_date">{s.source.publishedAt ? formatDate(s.source.publishedAt, language) : dash}</dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.retrievedLabel')}</dt>
                  <dd data-field="retrieved_at">{s.source.accessDate ? formatDate(s.source.accessDate, language) : dash}</dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.review')}</dt>
                  <dd data-field="review_status">
                    {s.dataMode === 'synthetic' ? t('workspace.sources.reviewSynthetic') : t('workspace.sources.reviewPublished')}
                    {revision ? ` · ${revision}` : ''}
                  </dd>
                  <dt className="text-muted-foreground">{t('workspace.sources.address')}</dt>
                  <dd data-field="source_url" className="min-w-0">
                    {s.source.url ? (
                      <a href={s.source.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 text-primary hover:underline">
                        <span className="truncate" dir="ltr">{new URL(s.source.url).hostname}</span><ExternalLink aria-hidden="true" className="size-3 shrink-0" />
                      </a>
                    ) : dash}
                  </dd>
                </dl>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs text-muted-foreground">{t('workspace.sources.none')}</p>
      )}
    </DashboardCard>
  );
}
