import {
  Activity,
  BookOpen,
  Bot,
  DatabaseZap,
  Droplets,
  FileText,
  FlaskConical,
  LayoutDashboard,
  LibraryBig,
  LineChart,
  Lock,
  Map,
  Settings,
  Ship,
  UserRound,
  Users,
  Wheat,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { NavLink } from 'react-router';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export type NavKey =
  | 'nav.overview'
  | 'nav.electricity'
  | 'nav.water'
  | 'nav.foodSecurity'
  | 'nav.trade'
  | 'nav.map'
  | 'nav.studies'
  | 'nav.scenarios'
  | 'nav.sourcesShort'
  | 'nav.aiAssistant'
  | 'nav.reports'
  | 'nav.library'
  | 'nav.accountShort'
  | 'nav.settings'
  | 'nav.dataManagement'
  | 'nav.users'
  | 'nav.health';

export interface NavItem {
  path: string;
  key: NavKey;
  icon: LucideIcon;
  restricted?: boolean;
}

interface NavGroup {
  label: 'nav.groupMain' | 'nav.groupMoreTools' | 'nav.groupYou' | 'nav.groupAdmin' | null;
  items: readonly NavItem[];
}

/** The main destinations, in this order: Overview, the four sectors, Studies, Sources and
 * Settings. Then the other tools (the AI Assistant, the map, scenarios, reports, the library),
 * the account and administration (authorized users). Page titles keep their full names. */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: null,
    items: [
      { path: '/overview', key: 'nav.overview', icon: LayoutDashboard },
      { path: '/energy/electricity', key: 'nav.electricity', icon: Zap },
      { path: '/energy/water', key: 'nav.water', icon: Droplets },
      { path: '/food-security', key: 'nav.foodSecurity', icon: Wheat },
      { path: '/trade', key: 'nav.trade', icon: Ship },
      { path: '/studies', key: 'nav.studies', icon: FlaskConical },
      { path: '/sources', key: 'nav.sourcesShort', icon: BookOpen },
      { path: '/settings', key: 'nav.settings', icon: Settings },
    ],
  },
  {
    label: 'nav.groupMoreTools',
    items: [
      { path: '/assistant', key: 'nav.aiAssistant', icon: Bot },
      { path: '/geography', key: 'nav.map', icon: Map },
      { path: '/forecasts', key: 'nav.scenarios', icon: LineChart },
      { path: '/reports', key: 'nav.reports', icon: FileText },
      { path: '/library', key: 'nav.library', icon: LibraryBig },
    ],
  },
  { label: 'nav.groupYou', items: [{ path: '/account', key: 'nav.accountShort', icon: UserRound }] },
  {
    label: 'nav.groupAdmin',
    items: [
      { path: '/data-management', key: 'nav.dataManagement', icon: DatabaseZap, restricted: true },
      { path: '/admin/users', key: 'nav.users', icon: Users, restricted: true },
      { path: '/admin/health', key: 'nav.health', icon: Activity, restricted: true },
    ],
  },
];

/** Every destination, for the page title in the top bar and for search. */
export const NAV_ITEMS: readonly NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

/** Navigation list for the sidebar and the mobile drawer. */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();

  return (
    <nav aria-label={t('nav.mainLabel')} className="flex flex-col gap-5">
      {NAV_GROUPS.map((group, gi) => (
        <div key={group.label ?? gi} className="flex flex-col gap-0.5">
          {group.label ? (
            <p className="px-2.5 pb-1 text-[0.6875rem] font-medium text-sidebar-muted ltr:tracking-wider ltr:uppercase">{t(group.label)}</p>
          ) : null}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.key}>
                  <NavLink
                    to={to(item.path)}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'group flex min-h-9 items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors',
                        isActive
                          ? 'bg-sidebar-active font-medium text-sidebar-foreground'
                          : 'text-sidebar-muted hover:bg-sidebar-active/70 hover:text-sidebar-foreground',
                      )
                    }
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0 group-aria-[current=page]:text-sidebar-accent" />
                    <span className="min-w-0 flex-1 truncate">{t(item.key)}</span>
                    {item.restricted ? (
                      <>
                        <Lock aria-hidden="true" className="size-3 shrink-0 opacity-60" />
                        <span className="sr-only">({t('nav.authorizedOnly')})</span>
                      </>
                    ) : null}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
