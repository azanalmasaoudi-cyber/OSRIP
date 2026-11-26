import { CalendarClock, ExternalLink, Telescope } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { OUTLOOK_CLASSES, useOutlook, type OutlookClass, type OutlookItem } from '@/api/outlook';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { formatDecimal, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/** One look per evidence class, always with its words (never colour alone). */
const CLASS_VARIANT: Record<OutlookClass, 'verified' | 'sand' | 'pending' | 'accent' | 'outline' | 'missing'> = {
  observed: 'verified',
  estimate: 'sand',
  forecast: 'pending',
  policy_target: 'accent',
  planned: 'outline',
  under_consideration: 'missing',
};

export function OutlookClassBadge({ item }: { item: Pick<OutlookItem, 'evidence_class' | 'class_label'> }) {
  const language = useAppLanguage();
  return (
    <Badge variant={CLASS_VARIANT[item.evidence_class]} data-class={item.evidence_class}>
      {item.class_label[language]}
    </Badge>
  );
}

/** An item's value with its unit (percent without a space), or null for a dated event. */
export function outlookValue(item: OutlookItem, language: AppLanguage): string | null {
  if (item.value === null) return null;
  const n = formatDecimal(item.value, language, 2) ?? item.value;
  return item.unit.code === 'percent' ? `${n}${item.unit[language]}` : `${n} ${item.unit[language]}`;
}

/** Outlook items as a list: metric, year, value or date, scope, class, status and (on request) source. */
export function OutlookList({ items, compact = false }: { items: readonly OutlookItem[]; compact?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <ul className="flex flex-col divide-y divide-border" data-testid="outlook-items">
      {items.map((item) => (
        <li key={item.id} className="flex flex-col gap-1.5 py-3" data-testid="outlook-item" data-class={item.evidence_class}
          data-metric={item.metric.code} data-year={item.year} data-achieved={item.achieved}>
          <div className="flex flex-wrap items-center gap-2">
            <OutlookClassBadge item={item} />
            <span className="text-sm font-semibold tabular-nums" dir="ltr">{item.year}</span>
            <span className="text-xs text-muted-foreground" dir="auto">{item.scope[language]}</span>
          </div>
          <p className="text-base">
            <span className="font-medium">{language === 'ar' ? item.metric.ar : item.metric.en}</span>
            {outlookValue(item, language) ? <>: <bdi dir="ltr" className="tabular-nums">{outlookValue(item, language)}</bdi></> : (
              <span className="inline-flex items-center gap-1 text-sm text-muted-foreground"> <CalendarClock aria-hidden="true" className="size-3.5" />{t('outlook.dateOnly')}</span>
            )}
          </p>
          {item.status_note ? <p className="text-sm text-muted-foreground" dir="auto">{item.status_note[language]}</p> : null}
          {compact ? null : (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">{t('outlook.source')}</summary>
              <p className="mt-1">
                <a href={item.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                  {item.source.title}<ExternalLink aria-hidden="true" className="size-3" />
                </a>
                {' · '}{item.source.publisher} · {item.source.locator} · {t('outlook.retrieved', { date: item.source.retrieved_on })}
              </p>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * The official outlook for electricity or water (2026-2032 statements): forecasts, targets, plans
 * and options, each labelled with its evidence class and grouped by it, never mixed with the
 * observed series above. Loaded only when the panel is opened (the caller mounts it on request).
 */
export function SectorOutlook({ section }: { section: 'electricity' | 'water' }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const outlook = useOutlook(section);
  return (
    <section aria-labelledby={`${section}-outlook-h`} className="flex flex-col gap-4 rounded-lg border border-dashed border-border-strong/60 bg-card p-4 shadow-card sm:p-5"
      data-testid="sector-outlook">
      <div className="flex flex-col gap-1">
        <h3 id={`${section}-outlook-h`} className="flex items-center gap-2 text-lg font-semibold">
          <Telescope aria-hidden="true" className="size-5 text-primary" />{t('outlook.heading')}
        </h3>
        <p className="text-sm text-muted-foreground">{outlook.data ? outlook.data.note[language] : t('outlook.lead')}</p>
      </div>
      {outlook.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
      {outlook.isError ? <StatePanel kind="error" error={outlook.error} onRetry={() => void outlook.refetch()} /> : null}
      {outlook.data && !outlook.data.items.length ? (
        <p role="status" className="text-base" data-testid="outlook-empty">{t('outlook.empty')}</p>
      ) : null}
      {outlook.data?.items.length ? (
        <>
          <ul className="flex flex-wrap gap-2 text-xs" aria-label={t('outlook.legend')} data-testid="outlook-legend">
            {outlook.data.classes.map((c) => (
              <li key={c.code}><Badge variant={CLASS_VARIANT[c.code]}>{c.label[language]}</Badge></li>
            ))}
          </ul>
          {OUTLOOK_CLASSES.map((cls) => {
            const items = outlook.data.items.filter((i) => i.evidence_class === cls);
            if (!items.length) return null;
            return (
              <div key={cls} className={cn('flex flex-col', cls === 'observed' || cls === 'estimate' ? '' : 'rounded-md bg-muted/40 px-3')}
                data-testid="outlook-group" data-class={cls}>
                <OutlookList items={items} />
              </div>
            );
          })}
        </>
      ) : null}
    </section>
  );
}
