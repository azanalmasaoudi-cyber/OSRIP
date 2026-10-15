import { useRef, type KeyboardEvent } from 'react';

import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * ARIA tabs with roving focus: Tab reaches the selected tab, the arrow keys move between tabs
 * (mirrored in Arabic), Home and End jump to the first and last. Panels are rendered by the
 * caller with ``tabPanelProps``.
 */
export function Tabs<T extends string>({ tabs, value, onChange, idBase, label, className }: {
  tabs: readonly { id: T; label: string; badge?: string | null }[];
  value: T;
  onChange: (id: T) => void;
  idBase: string;
  label: string;
  className?: string;
}) {
  const rtl = useAppLanguage() === 'ar';
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (event: KeyboardEvent, index: number) => {
    const forward = rtl ? 'ArrowLeft' : 'ArrowRight';
    const back = rtl ? 'ArrowRight' : 'ArrowLeft';
    let next = index;
    if (event.key === forward) next = (index + 1) % tabs.length;
    else if (event.key === back) next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    const tab = tabs[next];
    if (!tab) return;
    onChange(tab.id);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={cn('flex gap-1 rounded-lg border border-border bg-muted/50 p-1', className)} data-testid={`${idBase}-tabs`}>
      {tabs.map((tab, i) => {
        const selected = tab.id === value;
        return (
          <button key={tab.id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`${idBase}-tab-${tab.id}`}
            aria-selected={selected} aria-controls={`${idBase}-panel-${tab.id}`} tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)} onKeyDown={(e) => move(e, i)} data-tab={tab.id}
            className={cn('inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-md px-3 text-sm font-medium transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-ring',
              selected ? 'bg-card text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground')}>
            {tab.label}
            {tab.badge ? <span className="rounded-full bg-copper-subtle px-1.5 text-xs text-copper-foreground">{tab.badge}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function tabPanelProps(idBase: string, id: string, selected: boolean) {
  return {
    role: 'tabpanel' as const,
    id: `${idBase}-panel-${id}`,
    'aria-labelledby': `${idBase}-tab-${id}`,
    hidden: !selected,
    tabIndex: 0,
  };
}
