import { Droplets, Zap } from 'lucide-react';
import { Navigate, NavLink, Outlet, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/common/PageHeader';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const VIEWS = [
  { path: '/energy/electricity', key: 'nav.electricity', icon: Zap },
  { path: '/energy/water', key: 'nav.water', icon: Droplets },
] as const;

/**
 * Electricity and Water are separate views inside the Energy and Essential
 * Services domain (booklet 3.14). They are links (each view has its own URL),
 * not ARIA tabs.
 */
export function EnergyLayout() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const { pathname } = useLocation();

  return (
    <>
      <PageHeader title={t('pages.energy.title')} intro={t('pages.energy.intro')} setsDocumentTitle={false}
        illustration={pathname.startsWith('/energy/water') ? 'water' : 'electricity'} />
      <nav aria-label={t('nav.energySectionsLabel')} className="mb-8 border-b border-border">
        <ul className="flex gap-1">
          {VIEWS.map((view) => {
            const Icon = view.icon;
            return (
              <li key={view.path}>
                <NavLink
                  to={to(view.path)}
                  className={({ isActive }) =>
                    cn(
                      'tab-underline inline-flex min-h-11 items-center gap-2 rounded-t-md px-4 text-sm transition-colors hover:bg-muted/60',
                      isActive ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground',
                    )
                  }
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {t(view.key)}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <Outlet />
    </>
  );
}

/** /energy -> /energy/electricity, keeping the query string (data mode). */
export function EnergyIndexRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/energy/electricity', search }} replace />;
}
