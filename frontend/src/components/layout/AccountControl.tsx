import { Bell, ChevronDown, LogIn, LogOut, Settings } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useLogout, useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useAlerts } from '@/api/library';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Watchlist alerts: the unread count, linking to the alerts list. */
function AlertBell() {
  const { t } = useTranslation();
  const alerts = useAlerts(true);
  const to = usePreservedSearch();
  const target = to('/library');
  const unread = alerts.data?.unread ?? 0;
  return (
    <Link to={{ pathname: target.pathname, search: `${target.search ? `${target.search}&` : '?'}tab=watch` }}
      className="relative inline-flex size-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
      aria-label={`${t('library.alertsTitle')}: ${t('library.unread', { count: unread })}`} data-testid="alert-bell" data-unread={unread}>
      <Bell aria-hidden="true" className="size-4" />
      {unread > 0 ? (
        <span aria-hidden="true" className="absolute -end-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-[0.65rem] font-semibold leading-4 text-primary-foreground">
          {unread > 99 ? '99+' : unread}
        </span>
      ) : null}
    </Link>
  );
}

/**
 * The account menu (API mode only): a sign-in link, or the signed-in person's name opening a
 * small panel with Account and settings and Sign out. Escape or a click elsewhere closes it and
 * focus returns to the button.
 */
export function AccountControl() {
  const { t } = useTranslation();
  const me = useMe();
  const logout = useLogout();
  const to = usePreservedSearch();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  if (adapterKind !== 'http') return null;
  if (!me.data?.authenticated) {
    return (
      <Link to={to('/sign-in')} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'max-sm:px-2')} data-testid="sign-in-link">
        <LogIn aria-hidden="true" className="rtl:-scale-x-100" />
        {/* Phones: the icon alone (the top bar is full); the name stays for assistive technology. */}
        <span className="max-sm:sr-only">{t('auth.signIn')}</span>
      </Link>
    );
  }
  const name = me.data.display_name ?? me.data.email ?? me.data.username ?? '';
  return (
    <div ref={root} className="relative flex items-center gap-1 text-sm">
      {me.data.password_change_required ? null : <AlertBell />}
      <button ref={button} type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)}
        className="flex min-h-9 items-center gap-2 rounded-md px-1.5 hover:bg-muted" data-testid="signed-in-as">
        <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {name.trim().charAt(0).toUpperCase() || '?'}
        </span>
        <span className="hidden max-w-36 truncate sm:inline">{name}</span>
        <span className="sr-only">{t('shell.accountMenu')}: {t('auth.signedInAs', { name })}</span>
        <ChevronDown aria-hidden="true" className={cn('size-3.5 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      <div id={panelId} hidden={!open}
        className="absolute end-0 top-full z-50 mt-1 w-60 rounded-lg border border-border bg-card p-1 shadow-raised">
        <p className="truncate px-2.5 py-2 text-xs text-muted-foreground">{t('auth.signedInAs', { name })}</p>
        <Link to={to('/account')} onClick={() => setOpen(false)}
          className="flex items-center gap-2 rounded-md px-2.5 py-2 hover:bg-muted" data-testid="account-menu-settings">
          <Settings aria-hidden="true" className="size-4 text-muted-foreground" />{t('nav.account')}
        </Link>
        <button type="button" onClick={() => { setOpen(false); logout.mutate(); }}
          className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-start hover:bg-muted" data-testid="sign-out">
          <LogOut aria-hidden="true" className="size-4 text-muted-foreground rtl:-scale-x-100" />{t('auth.signOut')}
        </button>
      </div>
    </div>
  );
}
