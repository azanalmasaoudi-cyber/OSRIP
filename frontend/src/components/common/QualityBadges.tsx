import { CalendarClock, CircleDashed, FileText, Hourglass, ShieldCheck, FlaskConical } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Timeline } from '@/api/series';
import { Badge } from '@/components/ui/badge';
import type { DataMode } from '@/domain/types';
import { formatDate } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/** Revision statuses that the publisher (or a reviewer) has not yet confirmed as final. */
const NOT_FINAL = new Set(['provisional', 'preliminary', 'estimate']);

export interface Quality {
  mode: DataMode;
  /** Values shown (missing periods excluded). */
  withValue: number;
  /** Values whose figure is provisional, preliminary or an estimate. */
  pending: number;
  /** Periods in the range with no published value. */
  missing: number;
  /** The latest publication or retrieval date among the rows' sources (YYYY-MM-DD), if any. */
  lastUpdated: string | null;
  /** Publishers, in order of first appearance. */
  publishers: string[];
}

/** The quality of exactly the rows on screen (the same rows as the table, chart and CSV). */
export function qualityOf(timeline: Timeline, mode: DataMode): Quality {
  const rows = timeline.rows;
  const valued = rows.filter((r) => r.value !== null);
  const pending = valued.filter((r) => NOT_FINAL.has(r.revision_status ?? '') || r.nature === 'provisional' || r.nature === 'estimate').length;
  const dates = rows.flatMap((r) => [r.dataset_version?.published_at, r.source?.access_date])
    .concat(timeline.sources.map((s) => s.access_date))
    .filter((d): d is string => typeof d === 'string' && /^\d{4}-\d{2}-\d{2}/.test(d))
    .map((d) => d.slice(0, 10))
    .sort();
  const publishers = [...new Set(timeline.sources.map((s) => s.publisher).filter((p): p is string => Boolean(p)))];
  return {
    mode,
    withValue: timeline.summary?.with_value ?? valued.length,
    pending,
    missing: timeline.summary?.missing ?? rows.filter((r) => r.value === null).length,
    lastUpdated: dates.length ? dates[dates.length - 1]! : null,
    publishers,
  };
}

/**
 * The data-quality line above a result: Verified (or Synthetic), Pending review, Missing data,
 * Last updated and Source. Every badge is text with an icon, never colour alone, and none is
 * shown that the rows cannot support: "Verified" only for published values in verified-source
 * mode, never for synthetic demonstration data.
 */
export function QualityBadges({ quality, className }: { quality: Quality; className?: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { mode, withValue, pending, missing, lastUpdated, publishers } = quality;
  const first = publishers[0];
  const source = first && publishers.length > 1 ? t('quality.sourceMore', { first, count: publishers.length - 1 }) : first;
  return (
    <ul className={cn('flex flex-wrap items-center gap-1.5', className)} data-testid="quality-badges" aria-label={t('quality.label')}>
      {mode === 'synthetic' ? (
        <li><Badge variant="synthetic" data-quality="synthetic" title={t('quality.syntheticTitle')}>
          <FlaskConical aria-hidden="true" />{t('quality.synthetic')}
        </Badge></li>
      ) : withValue > 0 ? (
        <li><Badge variant="verified" data-quality="verified" title={t('quality.verifiedTitle')}>
          <ShieldCheck aria-hidden="true" />{t('quality.verified')}
        </Badge></li>
      ) : null}
      {pending > 0 ? (
        <li><Badge variant="pending" data-quality="pending" title={t('quality.pendingTitle')}>
          <Hourglass aria-hidden="true" />{t('quality.pending', { count: pending })}
        </Badge></li>
      ) : null}
      {missing > 0 ? (
        <li><Badge variant="missing" data-quality="missing" title={t('quality.missingTitle')}>
          <CircleDashed aria-hidden="true" />{t('quality.missing', { count: missing })}
        </Badge></li>
      ) : null}
      {lastUpdated ? (
        <li><Badge variant="muted" data-quality="updated">
          <CalendarClock aria-hidden="true" />{t('quality.updated', { date: formatDate(lastUpdated, language) })}
        </Badge></li>
      ) : null}
      {source ? (
        <li className="min-w-0"><Badge variant="outline" data-quality="source" className="max-w-full" title={publishers.join(' · ')}>
          <FileText aria-hidden="true" /><span className="truncate"><bdi>{t('quality.source', { source })}</bdi></span>
        </Badge></li>
      ) : null}
    </ul>
  );
}

/** The five badges with what each means, for the Overview and the Sources page. */
export function QualityLegend({ className }: { className?: string }) {
  const { t } = useTranslation();
  const items = [
    { variant: 'verified', icon: ShieldCheck, label: t('quality.verified'), body: t('quality.legend.verified') },
    { variant: 'pending', icon: Hourglass, label: t('quality.pendingShort'), body: t('quality.legend.pending') },
    { variant: 'missing', icon: CircleDashed, label: t('quality.missingShort'), body: t('quality.legend.missing') },
    { variant: 'muted', icon: CalendarClock, label: t('quality.updatedShort'), body: t('quality.legend.updated') },
    { variant: 'outline', icon: FileText, label: t('quality.sourceShort'), body: t('quality.legend.source') },
  ] as const;
  return (
    <dl className={cn('grid gap-3 sm:grid-cols-2 xl:grid-cols-5', className)} data-testid="quality-legend">
      {items.map(({ variant, icon: Icon, label, body }) => (
        <div key={variant} className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-4">
          <dt><Badge variant={variant}><Icon aria-hidden="true" />{label}</Badge></dt>
          <dd className="text-sm text-muted-foreground">{body}</dd>
        </div>
      ))}
    </dl>
  );
}
