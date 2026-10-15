import {
  Activity,
  BookOpen,
  Bot,
  DatabaseZap,
  Droplets,
  FileText,
  FlaskConical,
  House,
  LayoutDashboard,
  LibraryBig,
  LineChart,
  Lock,
  Map,
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

interface NavItem {
  path: string;
  key:
    | 'nav.home'
    | 'nav.overview'
    | 'nav.energy'
    | 'nav.electricity'
    | 'nav.water'
    | 'nav.foodSecurity'
    | 'nav.trade'
    | 'nav.map'
    | 'nav.scenarios'
    | 'nav.reports'
    | 'nav.assistant'
    | 'nav.library'
    | 'nav.studies'
    | 'nav.account'
    | 'nav.sourcesShort'
    | 'nav.dataManagement'
    | 'nav.users'
    | 'nav.health';
  icon: LucideIcon;
  end?: boolean;
  restricted?: boolean;
  children?: readonly NavItem[];
}

interface NavGroup {
  label: 'nav.groupDomains' | 'nav.groupAnalyse' | 'nav.groupTools' | 'nav.groupYou' | 'nav.groupAdmin' | null;
  items: readonly NavItem[];
}

/** Overview, the resource domains, then Map, Studies, Scenarios and Sources; Al Mulhim, reports
 * and the research library; the account and administration. Page titles keep their full names. */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: null,
    items: [
      { path: '/', key: 'nav.home', icon: House, end: true },
      { path: '/overview', key: 'nav.overview', icon: LayoutDashboard },
    ],
  },
  {
    label: 'nav.groupDomains',
    items: [
      {
        path: '/energy',
        key: 'nav.energy',
        icon: DatabaseZap,
        children: [
          { path: '/energy/electricity', key: 'nav.electricity', icon: Zap },
          { path: '/energy/water', key: 'nav.water', icon: Droplets },
        ],
      },
      { path: '/food-security', key: 'nav.foodSecurity', icon: Wheat },
      { path: '/trade', key: 'nav.trade', icon: Ship },
    ],
  },
  {
    label: 'nav.groupAnalyse',
    items: [
      { path: '/geography', key: 'nav.map', icon: Map },
      { path: '/studies', key: 'nav.studies', icon: FlaskConical },
      { path: '/forecasts', key: 'nav.scenarios', icon: LineChart },
      { path: '/sources', key: 'nav.sourcesShort', icon: BookOpen },
    ],
  },
  {
    label: 'nav.groupTools',
    items: [
      { path: '/assistant', key: 'nav.assistant', icon: Bot },
      { path: '/reports', key: 'nav.reports', icon: FileText },
      { path: '/library', key: 'nav.library', icon: LibraryBig },
    ],
  },
  {
    label: 'nav.groupYou',
    items: [{ path: '/account', key: 'nav.account', icon: UserRound }],
  },
  {
    label: 'nav.groupAdmin',
    items: [
      { path: '/data-management', key: 'nav.dataManagement', icon: Lock, restricted: true },
      { path: '/admin/users', key: 'nav.users', icon: Users, restricted: true },
      { path: '/admin/health', key: 'nav.health', icon: Activity, restricted: true },
    ],
  },
];

const linkBase =
  'flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-nav-active/70';

/** Navigation list for the navy sidebar and the mobile drawer. */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();

  return (
    <nav aria-label={t('nav.mainLabel')} className="flex flex-col gap-6">
      {NAV_GROUPS.map((group, gi) => (
        <div key={group.label ?? gi} className="flex flex-col gap-1">
          {group.label ? (
            <p className="px-3 pb-1 text-xs font-semibold text-nav-muted ltr:tracking-wide ltr:uppercase">{t(group.label)}</p>
          ) : null}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.key}>
                  <NavLink
                    to={to(item.path)}
                    end={item.end}
                    onClick={onNavigate}
                    // A section parent is "the current section", not "the current page".
                    aria-current={item.children ? 'true' : 'page'}
                    className={({ isActive }) =>
                      cn(
                        linkBase,
                        isActive
                          ? 'group bg-nav-active font-semibold text-nav-foreground shadow-[inset_3px_0_0_var(--nav-accent)] rtl:shadow-[inset_-3px_0_0_var(--nav-accent)]'
                          : 'text-nav-foreground/90',
                      )
                    }
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0 text-nav-muted group-aria-[current]:text-nav-accent" />
                    <span className="min-w-0 flex-1">{t(item.key)}</span>
                    {item.restricted ? <span className="sr-only">({t('nav.authorizedOnly')})</span> : null}
                  </NavLink>
                  {item.restricted ? (
                    <p className="ps-10 text-xs text-nav-muted" aria-hidden="true">
                      {t('nav.authorizedOnly')}
                    </p>
                  ) : null}
                  {item.children ? (
                    <ul className="ms-5 mt-0.5 flex flex-col gap-0.5 border-s border-nav-muted/30 ps-2">
                      {item.children.map((child) => {
                        const ChildIcon = child.icon;
                        return (
                          <li key={child.key}>
                            <NavLink
                              to={to(child.path)}
                              onClick={onNavigate}
                              className={({ isActive }) =>
                                cn(
                                  linkBase,
                                  'min-h-9 py-1.5',
                                  isActive ? 'bg-nav-active/80 font-semibold text-nav-foreground' : 'text-nav-foreground/85',
                                )
                              }
                            >
                              <ChildIcon aria-hidden="true" className="size-4 shrink-0 text-nav-muted" />
                              {t(child.key)}
                            </NavLink>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
