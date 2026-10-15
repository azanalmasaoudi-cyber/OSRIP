import { ChevronDown } from 'lucide-react';
import { useId, type SelectHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange'> {
  label: string;
  options: readonly SelectOption[];
  onValueChange: (value: string) => void;
  labelClassName?: string;
}

/** Labelled native select: full keyboard and screen-reader support for free. */
export function SelectField({ label, options, onValueChange, className, labelClassName, ...props }: SelectFieldProps) {
  const id = useId();
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <label htmlFor={id} className={cn('text-xs font-medium text-muted-foreground', labelClassName)}>
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          onChange={(event) => onValueChange(event.target.value)}
          className="h-10 w-full min-w-0 appearance-none truncate rounded-md border border-border-strong bg-card ps-3 pe-9 text-sm text-foreground hover:border-foreground/60"
          {...props}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
      </div>
    </div>
  );
}
