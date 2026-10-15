import { CircleAlert, Construction, DatabaseZap, FilterX, Lock, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export type StateKind = 'loading' | 'error' | 'no_verified_data' | 'empty' | 'not_implemented' | 'restricted';

interface StatePanelProps {
  kind: StateKind;
  detail?: string;
  onRetry?: () => void;
  /** Shown on `empty`: clears the page filters. */
  onReset?: () => void;
  /** Loading placeholder shape. */
  skeleton?: 'cards' | 'lines';
  children?: ReactNode;
  className?: string;
}

const CONTENT = {
  error: { icon: CircleAlert, title: 'states.errorTitle', body: 'states.error' },
  no_verified_data: { icon: DatabaseZap, title: 'states.noVerifiedDataTitle', body: 'states.noVerifiedData' },
  empty: { icon: FilterX, title: 'states.emptyTitle', body: 'states.empty' },
  not_implemented: { icon: Construction, title: 'states.notImplementedTitle', body: 'states.notImplemented' },
  restricted: { icon: Lock, title: 'states.restrictedTitle', body: 'states.restricted' },
} as const satisfies Record<Exclude<StateKind, 'loading'>, { icon: LucideIcon; title: string; body: string }>;

/**
 * Every state gets an icon, a title and an explanation rather than a blank
 * panel (booklet 3.14). Colour is never the only signal.
 */
export function StatePanel({ kind, detail, onRetry, onReset, skeleton = 'cards', children, className }: StatePanelProps) {
  const { t } = useTranslation();

  if (kind === 'loading') {
    return (
      <div role="status" aria-live="polite" aria-busy="true" data-state="loading" className={className}>
        <span className="sr-only">{t('states.loading')}</span>
        {skeleton === 'cards' ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {[0, 1].map((i) => (
              <div key={i} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-6">
                <Skeleton className="h-5 w-2/5" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="mt-2 h-32 w-full" />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        )}
      </div>
    );
  }

  const { icon: Icon, title, body } = CONTENT[kind];
  const isProblem = kind === 'error';

  return (
    <div
      role={isProblem ? 'alert' : 'status'}
      aria-live="polite"
      data-state={kind}
      className={cn(
        'flex flex-col items-start gap-3 rounded-lg border p-6 sm:flex-row sm:gap-4',
        isProblem ? 'border-destructive/40 bg-card' : 'border-dashed border-border-strong/50 bg-card/60',
        className,
      )}
    >
      <span
        className={cn(
          'flex size-10 shrink-0 items-center justify-center rounded-full',
          isProblem ? 'bg-destructive/10 text-destructive' : 'bg-sand-subtle text-sand-foreground',
        )}
      >
        <Icon aria-hidden="true" className="size-5" />
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className={cn('font-semibold', isProblem && 'text-destructive')}>{t(title)}</p>
        <p className="max-w-prose text-sm text-muted-foreground">{t(body)}</p>
        {detail ? (
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="font-medium">{t('states.technicalDetail')}:</span>{' '}
            <span dir="auto">{detail}</span>
          </p>
        ) : null}
        {children}
        {onRetry || (onReset && kind === 'empty') ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {onRetry ? (
              <Button variant="outline" size="sm" onClick={onRetry}>
                {t('states.retry')}
              </Button>
            ) : null}
            {onReset && kind === 'empty' ? (
              <Button variant="outline" size="sm" onClick={onReset}>
                {t('states.clearFilters')}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
