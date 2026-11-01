import {
  Activity,
  BookOpen,
  Bot,
  ChevronDown,
  DatabaseZap,
  Droplets,
  FileText,
  FlaskConical,
  Gauge,
  Info,
  Layers,
  LayoutDashboard,
  LibraryBig,
  LineChart,
  Map,
  Settings,
  Sheet,
  ShieldCheck,
  Ship,
  UserRound,
  Users,
  Wheat,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { NavLink, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';

import { hasPermission, useMe } from '@/api/auth';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export type NavKey =
  | 'nav.dashboard'
  | 'nav.overview'
  | 'nav.workspace'
  | 'nav.datasets'
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

type ModuleKey =
  | 'nav.moduleDashboard'
  | 'nav.moduleAxes'
  | 'nav.moduleAnalysis'
  | 'nav.moduleMap'
  | 'nav.moduleReports'
  | 'nav.moduleAssistant'
  | 'nav.groupAdmin'
  | 'nav.groupYou';

export interface NavItem {
  path: string;
  key: NavKey;
  icon: LucideIcon;
  /** Shown only to people holding one of these permissions (the server checks again). */
  requires?: readonly string[];
}

interface NavModule {
  id: string;
  label: ModuleKey;
  icon: LucideIcon;
  items: readonly NavItem[];
  /** Administration and the account: set apart at the end of the list. */
  section?: 'admin' | 'you';
}

/** The modules, in this order: Dashboard; Economic and Development Axes; Scenarios, Data and
 * Analysis; the Oman map; Reports; the AI Research Assistant; then administration (only what
 * the person may use) and the account. A module with one destination is a direct link; one with
 * several opens and closes, and opens by itself when it holds the current page. */
export const NAV_MODULES: readonly NavModule[] = [
  {
    id: 'dashboard', label: 'nav.moduleDashboard', icon: Gauge, items: [
      { path: '/', key: 'nav.dashboard', icon: LayoutDashboard },
      { path: '/overview', key: 'nav.overview', icon: Info },
    ],
  },
  {
    id: 'axes', label: 'nav.moduleAxes', icon: Layers, items: [
      { path: '/energy/electricity', key: 'nav.electricity', icon: Zap },
      { path: '/energy/water', key: 'nav.water', icon: Droplets },
      { path: '/food-security', key: 'nav.foodSecurity', icon: Wheat },
      { path: '/trade', key: 'nav.trade', icon: Ship },
    ],
  },
  {
    id: 'analysis', label: 'nav.moduleAnalysis', icon: LineChart, items: [
      { path: '/forecasts', key: 'nav.scenarios', icon: LineChart },
      { path: '/workspace', key: 'nav.workspace', icon: LayoutDashboard },
      { path: '/datasets', key: 'nav.datasets', icon: Sheet },
      { path: '/studies', key: 'nav.studies', icon: FlaskConical },
      { path: '/sources', key: 'nav.sourcesShort', icon: BookOpen },
      { path: '/library', key: 'nav.library', icon: LibraryBig },
    ],
  },
  { id: 'map', label: 'nav.moduleMap', icon: Map, items: [{ path: '/geography', key: 'nav.map', icon: Map }] },
  { id: 'reports', label: 'nav.moduleReports', icon: FileText, items: [{ path: '/reports', key: 'nav.reports', icon: FileText }] },
  { id: 'assistant', label: 'nav.moduleAssistant', icon: Bot, items: [{ path: '/assistant', key: 'nav.aiAssistant', icon: Bot }] },
  {
    id: 'admin', label: 'nav.groupAdmin', icon: ShieldCheck, section: 'admin', items: [
      { path: '/data-management', key: 'nav.dataManagement', icon: DatabaseZap, requires: ['import.read', 'research.review', 'user.manage'] },
      { path: '/admin/users', key: 'nav.users', icon: Users, requires: ['user.manage'] },
      { path: '/admin/health', key: 'nav.health', icon: Activity, requires: ['audit.read'] },
    ],
  },
  {
    id: 'you', label: 'nav.groupYou', icon: UserRound, section: 'you', items: [
      { path: '/account', key: 'nav.accountShort', icon: UserRound },
      { path: '/settings', key: 'nav.settings', icon: Settings },
    ],
  },
];

/** Every destination, for the page title in the top bar and for search. */
export const NAV_ITEMS: readonly NavItem[] = NAV_MODULES.flatMap((m) => m.items);

const OPEN_KEY = 'osrip.nav.open';

function readOpen(): Record<string, boolean> {
  try {
    return JSON.parse(window.localStorage.getItem(OPEN_KEY) ?? '{}') as Record<string, boolean>;
  } catch {
    return {};
  }
}

function isCurrent(path: string, pathname: string): boolean {
  return path === '/' ? pathname === '/' : pathname === path || pathname.startsWith(`${path}/`);
}

/** Navigation list for the sidebar and the mobile drawer. */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const { pathname } = useLocation();
  const me = useMe();
  const [open, setOpen] = useState<Record<string, boolean>>(readOpen);
  const allowed = (item: NavItem) => !item.requires || item.requires.some((p) => hasPermission(me.data, p));
  const showsAdmin = NAV_MODULES.some((m) => m.section === 'admin' && m.items.some(allowed));

  const toggle = (id: string, now: boolean) => {
    const next = { ...open, [id]: !now };
    setOpen(next);
    try {
      window.localStorage.setItem(OPEN_KEY, JSON.stringify(next));
    } catch {
      // Storage blocked: the choice lasts for this page only.
    }
  };

  const link = (item: NavItem, nested: boolean, label: NavKey | ModuleKey = item.key) => {
    const Icon = item.icon;
    return (
      <NavLink
        to={to(item.path)}
        end={item.path === '/'}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            // The active item: a lighter fill and a soft-gold bar on its inline start.
            'group relative flex min-h-10 items-center gap-3 rounded-md px-3 py-1.5 text-sm transition-colors',
            nested && 'ps-9',
            isActive
              ? 'bg-sidebar-active font-semibold text-sidebar-foreground before:absolute before:inset-y-2 before:start-0 before:w-[3px] before:rounded-full before:bg-sidebar-accent'
              : 'text-sidebar-muted hover:bg-sidebar-active/70 hover:text-sidebar-foreground',
          )
        }
      >
        <Icon aria-hidden="true" className="size-4 shrink-0 group-aria-[current=page]:text-sidebar-accent" />
        <span className="min-w-0 flex-1 truncate">{t(label)}</span>
      </NavLink>
    );
  };

  return (
    <nav aria-label={t('nav.mainLabel')} className="flex flex-col gap-1" data-testid="main-nav">
      {NAV_MODULES.map((module) => {
        const items = module.items.filter(allowed);
        if (items.length === 0) return null; // administration only for those who may use it
        const separated = module.section === 'admin' || (module.section === 'you' && !showsAdmin);
        const only = items.length === 1 ? items[0] : undefined;
        if (only) {
          return (
            <div key={module.id} className={cn(separated && 'mt-3 border-t border-sidebar-border pt-3')} data-module={module.id}>
              {link({ ...only, icon: module.icon }, false, module.label)}
            </div>
          );
        }
        const holdsCurrent = items.some((item) => isCurrent(item.path, pathname));
        const expanded = open[module.id] ?? holdsCurrent;
        const ModuleIcon = module.icon;
        const listId = `nav-module-${module.id}`;
        return (
          <div key={module.id} className={cn('flex flex-col gap-0.5', separated && 'mt-3 border-t border-sidebar-border pt-3')} data-module={module.id}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={listId}
              onClick={() => toggle(module.id, expanded)}
              className={cn(
                'flex min-h-10 items-center gap-3 rounded-md px-3 py-1.5 text-start text-sm font-medium transition-colors hover:bg-sidebar-active/70',
                holdsCurrent ? 'text-sidebar-foreground' : 'text-sidebar-muted hover:text-sidebar-foreground',
              )}
              data-testid={`nav-module-${module.id}`}
            >
              <ModuleIcon aria-hidden="true" className={cn('size-4 shrink-0', holdsCurrent && 'text-sidebar-accent')} />
              <span className="min-w-0 flex-1">{t(module.label)}</span>
              <ChevronDown aria-hidden="true" className={cn('size-4 shrink-0 transition-transform', expanded && 'rotate-180')} />
            </button>
            {expanded ? (
              <ul id={listId} className="flex flex-col gap-0.5">
                {items.map((item) => <li key={item.key}>{link(item, true)}</li>)}
              </ul>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
