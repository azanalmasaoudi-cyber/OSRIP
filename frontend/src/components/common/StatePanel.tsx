import {
  CircleAlert, Construction, DatabaseZap, FileQuestion, FilterX, Lock, LogIn, ServerOff, ShieldX, Unplug, type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { problemOf, type ProblemKind } from '@/api/problems';
import { Button, buttonVariants } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export type StateKind = 'loading' | 'error' | 'no_verified_data' | 'empty' | 'not_implemented' | 'restricted' | 'sign_in_required';

interface StatePanelProps {
  kind: StateKind;
  /** On `error`: what was thrown. It decides the title and explanation (server not connected,
   * not responding, database unavailable, sign-in needed, no permission, other). */
  error?: unknown;
  detail?: string;
  onRetry?: () => void;
  /** Shown on `empty`: clears the page filters. */
  onReset?: () => void;
  /** Loading placeholder shape. */
  skeleton?: 'cards' | 'lines';
  children?: ReactNode;
  className?: string;
}

interface Content { icon: LucideIcon; title: string; body: string }

/** The fixed states; `error` is refined by the failure's kind (PROBLEM_ICON, problems.* keys). */
const CONTENT = {
  error: { icon: CircleAlert, title: 'states.errorTitle', body: 'states.error' },
  no_verified_data: { icon: DatabaseZap, title: 'states.noVerifiedDataTitle', body: 'states.noVerifiedData' },
  empty: { icon: FilterX, title: 'states.emptyTitle', body: 'states.empty' },
  not_implemented: { icon: Construction, title: 'states.notImplementedTitle', body: 'states.notImplemented' },
  restricted: { icon: Lock, title: 'states.restrictedTitle', body: 'states.restricted' },
  sign_in_required: { icon: LogIn, title: 'problems.sign_in_required.title', body: 'problems.sign_in_required.body' },
} as const satisfies Record<Exclude<StateKind, 'loading'>, Content>;

const PROBLEM_ICON: Record<ProblemKind, LucideIcon> = {
  not_connected: Unplug,
  server_unavailable: ServerOff,
  database_unavailable: DatabaseZap,
  sign_in_required: LogIn,
  forbidden: ShieldX,
  invalid_response: FileQuestion,
  request_failed: CircleAlert,
};

/** Problems that are not a fault to retry or report: a sign-in or a permission. */
const NOT_A_FAULT: ReadonlySet<ProblemKind> = new Set(['sign_in_required', 'forbidden']);

/**
 * Every state gets an icon, a title and an explanation rather than a blank
 * panel (booklet 3.14). Colour is never the only signal. A failed request says which kind of
 * failure it is, in the reader's language, with Retry where asking again can help.
 */
export function StatePanel({ kind, error, detail, onRetry, onReset, skeleton = 'cards', children, className }: StatePanelProps) {
  const { t } = useTranslation();
  const to = usePreservedSearch();

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

  const problem = kind === 'error' && error !== undefined ? problemOf(error) : null;
  const base = CONTENT[kind];
  const Icon = problem ? PROBLEM_ICON[problem.kind] : base.icon;
  const title = problem ? (`problems.${problem.kind}.title` as const) : base.title;
  const body = problem ? (`problems.${problem.kind}.body` as const) : base.body;
  const isProblem = kind === 'error' && !(problem && NOT_A_FAULT.has(problem.kind));
  // The API's own words only for an unexplained refusal; otherwise the code and HTTP status.
  const technical = detail ?? (problem
    ? [problem.kind === 'request_failed' ? problem.message : null, problem.code, problem.status ? `HTTP ${problem.status}` : null]
        .filter(Boolean).join(' · ')
    : undefined);
  const signIn = kind === 'sign_in_required' || problem?.kind === 'sign_in_required';
  const retry = onRetry && !(problem && (problem.kind === 'sign_in_required' || problem.kind === 'forbidden')) ? onRetry : undefined;

  return (
    <div
      role={isProblem ? 'alert' : 'status'}
      aria-live="polite"
      data-state={kind}
      data-problem={problem?.kind}
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
        <p className={cn('font-semibold', isProblem && 'text-destructive')} data-testid="state-title">{t(title)}</p>
        <p className="max-w-prose text-sm text-muted-foreground" data-testid="state-body">{t(body)}</p>
        {technical ? (
          <p className="mt-1 text-xs text-muted-foreground" data-testid="state-detail">
            <span className="font-medium">{t('states.technicalDetail')}:</span>{' '}
            <span dir="auto">{technical}</span>
          </p>
        ) : null}
        {children}
        {retry || signIn || (onReset && kind === 'empty') ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {retry ? (
              <Button variant="outline" size="sm" onClick={retry} data-testid="state-retry">
                {t('states.retry')}
              </Button>
            ) : null}
            {signIn && !children ? (
              <Link to={to('/sign-in')} className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="state-sign-in">
                {t('auth.signIn')}
              </Link>
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
