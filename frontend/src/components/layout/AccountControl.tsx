import { Bell, LogIn, LogOut, UserRound } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useLogout, useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useAlerts } from '@/api/library';
import { Button, buttonVariants } from '@/components/ui/button';
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

/** Sign-in link or the signed-in user with a sign-out button (API mode only). */
export function AccountControl() {
  const { t } = useTranslation();
  const me = useMe();
  const logout = useLogout();
  const to = usePreservedSearch();

  if (adapterKind !== 'http') return null;
  if (!me.data?.authenticated) {
    return (
      <Link to={to('/sign-in')} className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="sign-in-link">
        <LogIn aria-hidden="true" />
        {t('auth.signIn')}
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      {me.data.password_change_required ? null : <AlertBell />}
      <Link to={to('/account')} className="flex items-center gap-1.5 text-muted-foreground underline-offset-4 hover:underline" data-testid="signed-in-as">
        <UserRound aria-hidden="true" className="size-4" />
        {t('auth.signedInAs', { name: me.data.display_name ?? me.data.email ?? '' })}
      </Link>
      <Button variant="ghost" size="sm" onClick={() => logout.mutate()}>
        <LogOut aria-hidden="true" className="rtl:-scale-x-100" />
        {t('auth.signOut')}
      </Button>
    </div>
  );
}
