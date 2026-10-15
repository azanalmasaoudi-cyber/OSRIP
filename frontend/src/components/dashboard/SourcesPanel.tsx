import { BookOpen, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PreviewBadge } from './PreviewLabel';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import type { Series } from '@/domain/types';
import { sourceTitle } from '@/lib/provenance';

/** Every source behind the values on screen, always visible (not only behind a dialog). */
export function SourcesPanel({ series, preview }: { series: readonly Series[]; preview: boolean }) {
  const { t } = useTranslation();
  const sources = [...new Map(series.map((s) => [`${sourceTitle(s)}|${s.source.versionLabel}`, s])).values()];
  return (
    <section aria-labelledby="ws-sources" className="flex flex-col gap-3" data-testid="workspace-sources">
      <h2 id="ws-sources" className="flex items-center gap-2 text-lg font-semibold">
        <BookOpen aria-hidden="true" className="size-5 text-primary" />{t('dashboard.sources.heading')}
      </h2>
      <p className="max-w-3xl text-sm text-muted-foreground">{t('dashboard.sources.intro')}</p>
      {sources.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border-strong/50 p-4 text-sm text-muted-foreground">{t('dashboard.sources.empty')}</p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {sources.map((s) => {
            const count = series.filter((x) => sourceTitle(x) === sourceTitle(s) && x.source.versionLabel === s.source.versionLabel).length;
            return (
              <li key={`${sourceTitle(s)}|${s.source.versionLabel}`} data-testid="dashboard-source"
                className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 shadow-card">
                <div className="flex flex-wrap items-center gap-1">
                  <DataModeBadge mode={s.dataMode} />
                  {preview ? <PreviewBadge /> : null}
                </div>
                <p className="text-pretty font-medium leading-snug">{sourceTitle(s)}</p>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
                  <dt className="text-muted-foreground">{t('dashboard.sources.publisher')}</dt>
                  <dd>{s.source.publisher ?? t('dashboard.sources.noPublisher')}</dd>
                  <dt className="text-muted-foreground">{t('dashboard.sources.version')}</dt>
                  <dd dir="ltr" className="text-start font-mono">{s.source.versionLabel}</dd>
                  {s.source.accessDate ? (
                    <>
                      <dt className="text-muted-foreground">{t('dashboard.sources.accessed')}</dt>
                      <dd dir="ltr" className="text-start tabular-nums">{s.source.accessDate}</dd>
                    </>
                  ) : null}
                  <dt className="text-muted-foreground">{t('dashboard.sources.series')}</dt>
                  <dd className="tabular-nums">{count}</dd>
                </dl>
                {s.source.url ? (
                  <a href={s.source.url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex w-fit items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
                    {t('dashboard.sources.link')}<ExternalLink aria-hidden="true" className="size-3.5" />
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
