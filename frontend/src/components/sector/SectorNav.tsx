import { Droplets, Ship, Wheat, Zap } from 'lucide-react';
import { NavLink } from 'react-router';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTORS = [
  { path: '/energy/electricity', key: 'nav.electricity', icon: Zap },
  { path: '/energy/water', key: 'nav.water', icon: Droplets },
  { path: '/food-security', key: 'nav.foodSecurity', icon: Wheat },
  { path: '/trade', key: 'nav.trade', icon: Ship },
] as const;

/** The four sectors as one row of links, the same on every sector page (it scrolls
 * sideways on a narrow screen instead of wrapping). Each sector keeps its own selection. */
export function SectorNav() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <nav aria-label={t('sectorFlow.navLabel')} className="-mt-2 mb-6 overflow-x-auto overflow-y-hidden border-b border-border" data-testid="sector-nav">
      <ul className="flex min-w-max gap-1">
        {SECTORS.map((s) => {
          const Icon = s.icon;
          return (
            <li key={s.path}>
              <NavLink to={to(s.path)} className={({ isActive }) => cn(
                'tab-underline inline-flex min-h-11 items-center gap-2 rounded-t-md px-4 text-sm transition-colors hover:bg-muted/60',
                isActive ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}>
                <Icon aria-hidden="true" className="size-4" />{t(s.key)}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
