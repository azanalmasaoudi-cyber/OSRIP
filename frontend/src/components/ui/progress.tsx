import { cn } from '@/lib/utils';

/**
 * Progress for work of unknown length (forecast backtests, uploads, validation).
 * Announced once by screen readers; the moving bar stops under reduced motion.
 */
export function ProgressBar({ label, value, className }: { label: string; value?: number; className?: string }) {
  const determinate = typeof value === 'number';
  return (
    <div className={cn('flex flex-col gap-1.5', className)} data-testid="progress">
      <p className="text-xs text-muted-foreground" aria-live="polite">{label}</p>
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={determinate ? Math.round(value) : undefined} aria-busy={!determinate}
        className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn('absolute inset-y-0 start-0 rounded-full bg-primary', determinate ? 'transition-[width] duration-300' : 'progress-indeterminate w-1/3')}
          style={determinate ? { width: `${Math.min(100, Math.max(0, value))}%` } : undefined} />
      </div>
    </div>
  );
}
