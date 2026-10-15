import { useRef, type KeyboardEvent } from 'react';

import { cn } from '@/lib/utils';

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  /** Shown after the label, e.g. "(unavailable)". The option stays selectable. */
  note?: string;
}

/**
 * Single-choice control with a sliding indicator. A radio group: arrow keys move the
 * choice (mirrored in right-to-left layouts), and the indicator's slide is removed
 * under prefers-reduced-motion by the global rule in index.css.
 */
export function Segmented<T extends string>({ label, value, options, onChange, className, testId }: {
  label: string;
  value: T;
  options: readonly SegmentOption<T>[];
  onChange: (value: T) => void;
  className?: string;
  testId?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  const width = 100 / options.length;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    const forward = rtl ? 'ArrowLeft' : 'ArrowRight';
    const back = rtl ? 'ArrowRight' : 'ArrowLeft';
    let next = index;
    if (event.key === forward || event.key === 'ArrowDown') next = (index + 1) % options.length;
    else if (event.key === back || event.key === 'ArrowUp') next = (index - 1 + options.length) % options.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = options.length - 1;
    else return;
    const target = options[next];
    if (!target) return;
    event.preventDefault();
    onChange(target.value);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={label} data-testid={testId}
      className={cn('relative isolate flex rounded-lg bg-muted p-1', className)}>
      <span aria-hidden="true"
        className="segment-indicator absolute inset-y-1 -z-10 rounded-md bg-card shadow-card"
        style={{ width: `calc(${width}% - 0.5rem * ${1 / options.length})`, insetInlineStart: `calc(0.25rem + ${index * width}% - ${(index * 0.5) / options.length}rem)` }} />
      {options.map((o, i) => (
        <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio"
          aria-checked={o.value === value} tabIndex={o.value === value ? 0 : -1} onClick={() => onChange(o.value)} onKeyDown={onKeyDown}
          data-value={o.value}
          className={cn('min-h-10 flex-1 rounded-md px-3 py-1.5 text-sm transition-colors',
            o.value === value ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground')}>
          {o.label}{o.note ? <span className="ms-1 text-xs font-normal text-muted-foreground">{o.note}</span> : null}
        </button>
      ))}
    </div>
  );
}
