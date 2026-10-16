import { ArrowUpRight, Bot, Search } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { NAV_ITEMS, type NavItem } from './SidebarNav';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

type Option = { kind: 'page'; item: NavItem } | { kind: 'ask' };

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

/**
 * Search in the top bar: pages by their name in either language, and "Ask the assistant" with
 * the typed text as a draft (the assistant page prefills it from ?q= and sends nothing). A
 * combobox with a listbox: arrows choose, Enter opens, Escape clears. `shortcut` makes Ctrl+K
 * (⌘K on a Mac) focus this instance.
 */
export function GlobalSearch({ shortcut = false, focusOnOpen = false, inline = false, onDone, className }: {
  shortcut?: boolean;
  /** Focus the field when it appears (the phone search dialog opens for typing). */
  focusOnOpen?: boolean;
  /** Results below the field in the flow (inside a dialog) rather than as a floating list. */
  inline?: boolean;
  /** Called after a choice (closes the phone search dialog). */
  onDone?: () => void;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [shortcut]);

  const text = query.trim();
  const needle = text.toLowerCase();
  const en = i18n.getFixedT('en');
  const ar = i18n.getFixedT('ar');
  const pages = needle
    ? NAV_ITEMS.filter((item) => [t(item.key), en(item.key), ar(item.key)].some((label) => label.toLowerCase().includes(needle)))
    : [];
  const options: Option[] = needle ? [...pages.map((item) => ({ kind: 'page' as const, item })), { kind: 'ask' as const }] : [];
  const expanded = open && options.length > 0;
  const current = Math.min(active, Math.max(options.length - 1, 0));
  const optionId = (i: number) => `${listId}-${i}`;

  const choose = (option: Option) => {
    if (option.kind === 'page') {
      void navigate(to(option.item.path));
    } else {
      const target = to('/assistant');
      const params = new URLSearchParams(target.search);
      params.set('q', text.slice(0, 1000));
      void navigate({ pathname: target.pathname, search: `?${params.toString()}` });
    }
    setQuery('');
    setOpen(false);
    onDone?.();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' && options.length) {
      event.preventDefault();
      setOpen(true);
      setActive((current + 1) % options.length);
    } else if (event.key === 'ArrowUp' && options.length) {
      event.preventDefault();
      setOpen(true);
      setActive((current - 1 + options.length) % options.length);
    } else if (event.key === 'Enter' && expanded) {
      event.preventDefault();
      const option = options[current];
      if (option) choose(option);
    } else if (event.key === 'Escape') {
      if (query) event.stopPropagation(); // clear first; a second Escape reaches any dialog
      setQuery('');
      setOpen(false);
    }
  };

  return (
    <div className={cn('relative', className)} data-testid="global-search">
      <label className="sr-only" htmlFor={`${listId}-input`}>{t('search.label')}</label>
      <Search aria-hidden="true" className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={input}
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded ? optionId(current) : undefined}
        // eslint-disable-next-line jsx-a11y/no-autofocus -- the phone search dialog opens for typing
        autoFocus={focusOnOpen}
        autoComplete="off"
        value={query}
        placeholder={t('search.placeholder')}
        onChange={(event) => { setQuery(event.target.value); setActive(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        className="h-9 w-full rounded-md border border-border bg-card ps-8 pe-14 text-sm placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
        data-testid="global-search-input"
      />
      {shortcut ? (
        <kbd aria-hidden="true" className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 font-sans text-[0.6875rem] text-muted-foreground" dir="ltr">
          {isMac ? '⌘K' : 'Ctrl K'}
        </kbd>
      ) : null}
      <ul id={listId} role="listbox" aria-label={t('search.label')} hidden={!expanded}
        className={cn('max-h-80 overflow-y-auto rounded-lg border border-border bg-card p-1',
          inline ? 'mt-2' : 'absolute inset-x-0 top-full z-50 mt-1 shadow-raised')}
        data-testid="global-search-results">
        {options.map((option, i) => (
          // Options are chosen with the keyboard through the combobox (aria-activedescendant).
          // eslint-disable-next-line jsx-a11y/click-events-have-key-events
          <li key={option.kind === 'page' ? option.item.path : 'ask'} id={optionId(i)} role="option" aria-selected={i === current}
            onMouseDown={(event) => event.preventDefault()} onClick={() => choose(option)} onMouseEnter={() => setActive(i)}
            className={cn('flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm', i === current && 'bg-muted')}
            data-testid={option.kind === 'page' ? 'search-result-page' : 'search-result-ask'}>
            {option.kind === 'page' ? (
              <>
                <option.item.icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{t(option.item.key)}</span>
                <ArrowUpRight aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground rtl:-scale-x-100" />
              </>
            ) : (
              <>
                <Bot aria-hidden="true" className="size-4 shrink-0 text-primary" />
                <span className="min-w-0 flex-1 truncate" dir="auto">{t('search.ask', { query: text })}</span>
              </>
            )}
          </li>
        ))}
      </ul>
      {open && needle && !pages.length ? (
        <p className="sr-only" role="status">{t('search.none', { query: text })}</p>
      ) : null}
    </div>
  );
}
