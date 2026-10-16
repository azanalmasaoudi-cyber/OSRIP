import { ChevronDown, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface FilterBarProps {
  children: ReactNode;
  onReset?: () => void;
  canReset?: boolean;
  /** Number of filters away from their default, shown on the collapsed mobile toggle. */
  activeCount?: number;
  className?: string;
}

/**
 * One row of filters above the content they control. Filter values live in the
 * URL (see useUrlFilter), so they are unchanged by a language switch.
 * On small screens the controls collapse behind a disclosure button.
 */
export function FilterBar({ children, onReset, canReset = false, activeCount = 0, className }: FilterBarProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <section aria-label={t('filters.heading')} data-testid="filter-bar" className={cn('mb-6 rounded-lg border border-border bg-card p-4', className)}>
      <div className="flex items-center justify-between gap-3 sm:mb-3">
        {/* Mobile: disclosure button. */}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="-m-2 flex min-h-11 flex-1 items-center gap-2 rounded-md p-2 text-sm font-semibold sm:hidden"
          data-testid="filters-toggle"
        >
          <SlidersHorizontal aria-hidden="true" className="size-4 text-primary" />
          {t('filters.heading')}
          {activeCount > 0 ? <Badge variant="sand">{activeCount}</Badge> : null}
          <ChevronDown aria-hidden="true" className={cn('ms-auto size-4 transition-transform', open && 'rotate-180')} />
        </button>
        {/* Larger screens: static heading. */}
        <h2 className="hidden items-center gap-2 text-sm font-semibold sm:flex">
          <SlidersHorizontal aria-hidden="true" className="size-4 text-primary" />
          {t('filters.heading')}
        </h2>
        {onReset ? (
          <Button variant="ghost" size="sm" onClick={onReset} disabled={!canReset} className="hidden sm:inline-flex">
            <RotateCcw aria-hidden="true" />
            {t('filters.reset')}
          </Button>
        ) : null}
      </div>
      <div id={panelId} className={cn('mt-3 sm:mt-0 sm:block', open ? 'block' : 'hidden')}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))]">{children}</div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">{t('filters.keptOnLanguageSwitch')}</p>
          {onReset ? (
            <Button variant="outline" size="sm" onClick={onReset} disabled={!canReset} className="sm:hidden">
              <RotateCcw aria-hidden="true" />
              {t('filters.reset')}
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
