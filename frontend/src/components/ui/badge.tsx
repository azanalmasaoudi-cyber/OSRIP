import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3.5',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        outline: 'border-border-strong text-foreground',
        synthetic: 'border-synthetic-border bg-synthetic text-synthetic-foreground',
        verified: 'border-verified-border bg-verified text-verified-foreground',
        muted: 'border-transparent bg-muted text-muted-foreground',
        sand: 'border-sand/50 bg-sand-subtle text-sand-foreground',
        accent: 'border-accent/40 bg-card text-accent',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
