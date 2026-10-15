import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/** Placeholder block. The pulse is disabled under prefers-reduced-motion. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn('rounded-md bg-muted motion-safe:animate-pulse', className)} {...props} />;
}
