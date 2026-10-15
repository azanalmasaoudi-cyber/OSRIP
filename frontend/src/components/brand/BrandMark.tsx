import { cn } from '@/lib/utils';

/**
 * OSRIP mark: an eight-point star of two overlapping squares, a generic
 * geometric motif. Deliberately not a seal, crest or emblem, so it cannot be
 * mistaken for official government branding.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={cn('size-9 shrink-0', className)}>
      <rect width="32" height="32" rx="7" className="fill-nav-active" />
      <g fill="none" strokeWidth="2" strokeLinejoin="round" className="stroke-nav-ring">
        <path d="M10 10h12v12H10z" />
        <path d="M16 7.5 24.5 16 16 24.5 7.5 16z" />
      </g>
      <circle cx="16" cy="16" r="2" className="fill-nav-ring" />
    </svg>
  );
}

/** Horizontal strip of stepped merlons, used as a section divider. */
export function CrenellationDivider({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('pattern-crenellation h-3.5 w-full bg-sand/70', className)} />;
}

/** Faint eight-point-star lattice; place inside a `relative` parent. */
export function LatticeBackdrop({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('pattern-lattice pointer-events-none absolute inset-0', className)} />;
}
