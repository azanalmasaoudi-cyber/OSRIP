import { ArrowRight, BookOpen, ExternalLink, FlaskConical } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { useMyStudies } from '@/api/studies';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { seriesKey } from '@/domain/filters';
import type { Series } from '@/domain/types';
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
export function SourcesPanel({ series }: { series: readonly Series[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const unique = [...new Map(series.map((s) => [sourceTitle(s), s])).values()].slice(0, 4);
  return (
    <DashboardCard title={t('workspace.sources.heading')} labelledBy="ws-sources" testId="workspace-sources"
      icon={<BookOpen aria-hidden="true" className="size-4 text-primary" />}
      action={<Link to={to('/sources')} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
        {t('workspace.sources.all')}<ArrowRight aria-hidden="true" className="size-3.5 rtl:-scale-x-100" /></Link>}>
      <p className="text-xs text-muted-foreground">{t('workspace.sources.note')}</p>
      {unique.length ? (
        <ul className="flex flex-col divide-y divide-border">
          {unique.map((s) => (
            <li key={seriesKey(s)} className="flex flex-col gap-0.5 py-2 text-sm" data-testid="workspace-source">
              <span className="font-medium"><bdi>{sourceTitle(s)}</bdi></span>
              <span className="text-xs text-muted-foreground">
                {s.source.publisher ?? t('workspace.sources.publisherNone')}
                {s.source.versionLabel ? ` · ${s.source.versionLabel}` : ''}
                {s.source.accessDate ? ` · ${t('workspace.sources.retrieved', { date: formatDate(s.source.accessDate, language) })}` : ''}
              </span>
              {s.source.url ? (
                <a href={s.source.url} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-xs text-primary hover:underline">
                  <span className="truncate" dir="ltr">{new URL(s.source.url).hostname}</span><ExternalLink aria-hidden="true" className="size-3" />
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs text-muted-foreground">{t('workspace.sources.none')}</p>
      )}
    </DashboardCard>
  );
}
