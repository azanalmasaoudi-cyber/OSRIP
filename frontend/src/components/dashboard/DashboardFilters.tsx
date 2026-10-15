import { CalendarRange, ChevronDown, Layers, MapPin, RotateCcw, ShieldCheck, SlidersHorizontal, type LucideIcon } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/** One labelled group of filters (a fieldset, so screen readers announce the group name). */
export function FilterGroup({ legend, icon: Icon, children, className }: { legend: string; icon: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <fieldset className={cn('flex min-w-0 flex-col gap-3 rounded-md border border-border bg-background/60 p-3', className)}>
      <legend className="sr-only">{legend}</legend>
      <p aria-hidden="true" className="flex items-center gap-1.5 text-xs font-semibold text-copper-foreground ltr:uppercase ltr:tracking-wider">
        <Icon className="size-3.5" />{legend}
      </p>
      {children}
    </fieldset>
  );
}

export const FILTER_ICONS = { scope: Layers, period: CalendarRange, geography: MapPin, mode: ShieldCheck } as const;

/**
 * Filters above the content they control. Values live in the URL, so a language switch
 * keeps them. On phones the panel collapses behind a disclosure button.
 */
export function DashboardFilters({ children, onReset, canReset, activeCount }: {
  children: ReactNode;
  onReset: () => void;
  canReset: boolean;
  activeCount: number;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <section aria-label={t('filters.heading')} data-testid="filter-bar" className="rounded-lg border border-border bg-card p-4 shadow-card sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)}
          className="-m-2 flex min-h-11 flex-1 items-center gap-2 rounded-md p-2 text-sm font-semibold md:hidden" data-testid="filters-toggle">
          <SlidersHorizontal aria-hidden="true" className="size-4 text-primary" />
          {t('filters.heading')}
          {activeCount > 0 ? <Badge variant="sand">{activeCount}</Badge> : null}
          <ChevronDown aria-hidden="true" className={cn('ms-auto size-4 transition-transform', open && 'rotate-180')} />
        </button>
        <h2 className="hidden items-center gap-2 text-sm font-semibold md:flex">
          <SlidersHorizontal aria-hidden="true" className="size-4 text-primary" />
          {t('filters.heading')}
          {activeCount > 0 ? <Badge variant="sand">{activeCount}</Badge> : null}
        </h2>
        <Button variant="ghost" size="sm" onClick={onReset} disabled={!canReset} className="hidden md:inline-flex">
          <RotateCcw aria-hidden="true" />{t('filters.reset')}
        </Button>
      </div>
      <div id={panelId} className={cn('mt-4 md:block', open ? 'block' : 'hidden')}>
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-[1.4fr_1.4fr_0.8fr_1fr]">{children}</div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">{t('filters.keptOnLanguageSwitch')}</p>
          <Button variant="outline" size="sm" onClick={onReset} disabled={!canReset} className="md:hidden">
            <RotateCcw aria-hidden="true" />{t('filters.reset')}
          </Button>
        </div>
      </div>
    </section>
  );
}
