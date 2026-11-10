import {
  Activity,
  BookOpen,
  Bot,
  ChevronDown,
  ClipboardList,
  DatabaseZap,
  Download,
  Droplets,
  FileText,
  FlaskConical,
  FolderOpen,
  Gauge,
  Info,
  Languages,
  Layers,
  LayoutDashboard,
  LibraryBig,
  LineChart,
  Map,
  MapPinned,
  Palette,
  ScrollText,
  Settings,
  Sheet,
  ShieldCheck,
  Ship,
  SlidersHorizontal,
  UserRound,
  Users,
  UsersRound,
  Wheat,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { useState, type FocusEvent, type MouseEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';

import { hasPermission, useMe } from '@/api/auth';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export type NavKey =
  | 'nav.dashboard'
  | 'nav.overview'
  | 'nav.electricity'
  | 'nav.water'
  | 'nav.foodSecurity'
  | 'nav.trade'
  | 'nav.workspace'
  | 'nav.datasets'
  | 'nav.scenarios'
  | 'nav.forecast'
  | 'nav.aiAssistant'
  | 'nav.studies'
  | 'nav.library'
  | 'nav.sourcesShort'
  | 'nav.map'
  | 'nav.geoCompare'
  | 'nav.reports'
  | 'nav.savedReports'
  | 'nav.exportCenter'
  | 'nav.profile'
  | 'nav.settings'
  | 'nav.appearance'
  | 'nav.language'
  | 'nav.dataManagement'
  | 'nav.users'
  | 'nav.groupsPermissions'
  | 'nav.health'
  | 'nav.audit';

type ModuleKey =
  | 'nav.moduleDashboard'
  | 'nav.moduleAxes'
  | 'nav.moduleResearch'
  | 'nav.moduleGeo'
  | 'nav.moduleReports'
  | 'nav.groupAccount'
  | 'nav.groupAdmin';

export interface NavItem {
  path: string;
  /** A section of the page (`#id`); items of one page are told apart by it. */
  hash?: string;
  /** A query that opens a tab of the page (`tab=groups`). */
  query?: string;
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
  /** The account and administration: set apart at the end of the list. */
  section?: 'admin' | 'you';
}

/** The modules: Dashboard; the Axes; Research and Analytics; Geographic Intelligence; Reports;
 * then the account and, only for those who may use it, administration. Every module opens and
 * closes (remembered in this browser) and starts open. */
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
    id: 'research', label: 'nav.moduleResearch', icon: FlaskConical, items: [
      { path: '/assistant', key: 'nav.aiAssistant', icon: Bot },
      { path: '/workspace', key: 'nav.workspace', icon: LayoutDashboard },
      { path: '/datasets', key: 'nav.datasets', icon: Sheet },
      { path: '/forecasts', key: 'nav.forecast', icon: LineChart },
      { path: '/studies', key: 'nav.studies', icon: ClipboardList },
      { path: '/library', key: 'nav.library', icon: LibraryBig },
      { path: '/sources', key: 'nav.sourcesShort', icon: BookOpen },
    ],
  },
  {
    id: 'geo', label: 'nav.moduleGeo', icon: Map, items: [
      { path: '/geography', key: 'nav.map', icon: MapPinned },
    ],
  },
  {
    id: 'reports', label: 'nav.moduleReports', icon: FileText, items: [
      { path: '/reports', key: 'nav.reports', icon: FileText },
    ],
  },
  {
    id: 'you', label: 'nav.groupAccount', icon: UserRound, section: 'you', items: [
      { path: '/account', key: 'nav.profile', icon: UserRound },
      { path: '/settings', key: 'nav.settings', icon: Settings },
    ],
  },
  {
    id: 'admin', label: 'nav.groupAdmin', icon: ShieldCheck, section: 'admin', items: [
      { path: '/data-management', key: 'nav.dataManagement', icon: DatabaseZap, requires: ['import.read', 'research.review', 'user.manage'] },
      { path: '/admin/users', key: 'nav.users', icon: Users, requires: ['user.manage'] },
      { path: '/admin/users', query: 'tab=groups', key: 'nav.groupsPermissions', icon: UsersRound, requires: ['user.manage'] },
      { path: '/admin/health', key: 'nav.health', icon: Activity, requires: ['audit.read'] },
      { path: '/admin/audit', key: 'nav.audit', icon: ScrollText, requires: ['audit.read'] },
    ],
  },
];

/** Every sidebar destination, for the page title in the top bar and for search. */
export const NAV_ITEMS: readonly NavItem[] = NAV_MODULES.flatMap((m) => m.items);

/** Sections of pages the sidebar already lists (one sidebar entry per page). They are not in the
 * sidebar, but search still finds them by name and opens the page at the section. */
export const SECTION_ITEMS: readonly NavItem[] = [
  { path: '/forecasts', hash: '#scenarios', key: 'nav.scenarios', icon: SlidersHorizontal },
  { path: '/geography', hash: '#compare-heading', key: 'nav.geoCompare', icon: Layers },
  { path: '/reports', hash: '#saved-reports', key: 'nav.savedReports', icon: FolderOpen },
  { path: '/reports', hash: '#export-center', key: 'nav.exportCenter', icon: Download },
  { path: '/settings', hash: '#appearance', key: 'nav.appearance', icon: Palette },
  { path: '/settings', hash: '#language', key: 'nav.language', icon: Languages },
];

const OPEN_KEY = 'osrip.nav.open';

function readOpen(): Record<string, boolean> {
  try {
    return JSON.parse(window.localStorage.getItem(OPEN_KEY) ?? '{}') as Record<string, boolean>;
  } catch {
    return {};
  }
}

function onPath(path: string, pathname: string): boolean {
  return path === '/' ? pathname === '/' : pathname === path || pathname.startsWith(`${path}/`);
}

/** The current item: the right page, then the open section (#hash) or tab (?tab=) when an item
 * names one; otherwise the page's plain item. */
export function isCurrentItem(item: NavItem, pathname: string, hash: string, search: string): boolean {
  if (!onPath(item.path, pathname)) return false;
  const tab = new URLSearchParams(search).get('tab');
  const tabQuery = tab === null ? null : `tab=${tab}`;
  if (item.query) return item.query === tabQuery;
  if (item.hash) return hash === item.hash;
  const siblings = NAV_ITEMS.filter((other) => other !== item && other.path === item.path);
  return !siblings.some((other) => (other.hash !== undefined && other.hash === hash) || (other.query !== undefined && other.query === tabQuery));
}

/** Where an item leads: its page with the data mode kept, plus its section or tab. */
export function useItemTarget() {
  const to = usePreservedSearch();
  return (item: NavItem) => {
    const target = to(item.path);
    const search = new URLSearchParams(target.search);
    if (item.query) for (const [k, v] of new URLSearchParams(item.query)) search.set(k, v);
    const query = search.toString();
    return { ...target, search: query ? `?${query}` : '', hash: item.hash ?? '' };
  };
}

/** Navigation list for the sidebar (full or icon-only) and the mobile drawer. */
export function SidebarNav({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  const { t } = useTranslation();
  const target = useItemTarget();
  const { pathname, hash, search } = useLocation();
  const me = useMe();
  const [open, setOpen] = useState<Record<string, boolean>>(readOpen);
  const allowed = (item: NavItem) => !item.requires || item.requires.some((p) => hasPermission(me.data, p));
  // Icon-only mode: the hovered or focused item's name, beside it (fixed, so the scrolling
  // sidebar cannot clip it); on the inline-end side in both directions.
  const [tip, setTip] = useState<{ label: string; top: number; x: number; rtl: boolean } | null>(null);
  const showTip = (label: string) => (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    setTip({ label, top: rect.top + rect.height / 2, x: rtl ? window.innerWidth - rect.left + 8 : rect.right + 8, rtl });
  };

  const toggle = (id: string, now: boolean) => {
    const next = { ...open, [id]: !now };
    setOpen(next);
    try {
      window.localStorage.setItem(OPEN_KEY, JSON.stringify(next));
    } catch {
      // Storage blocked: the choice lasts for this page only.
    }
  };

  const link = (item: NavItem, nested: boolean) => {
    const Icon = item.icon;
    const current = isCurrentItem(item, pathname, hash, search);
    const label = t(item.key);
    return (
      <Link
        to={target(item)}
        onClick={onNavigate}
        aria-current={current ? 'page' : undefined}
        aria-label={collapsed ? label : undefined}
        onMouseEnter={collapsed ? showTip(label) : undefined}
        onFocus={collapsed ? showTip(label) : undefined}
        onMouseLeave={collapsed ? () => setTip(null) : undefined}
        onBlur={collapsed ? () => setTip(null) : undefined}
        className={cn(
          // The current item: a soft accent fill and a peach bar on its inline start.
          'nav-link group relative flex min-h-10 items-center gap-3 rounded-lg px-3 py-1.5 text-sm transition-colors duration-150',
          nested && !collapsed && 'ps-9',
          collapsed && 'justify-center px-0',
          current
            ? 'bg-primary-soft font-semibold text-sidebar-foreground before:absolute before:inset-y-2 before:start-0 before:w-[3px] before:rounded-full before:bg-sidebar-accent'
            : 'text-sidebar-muted hover:bg-sidebar-active/70 hover:text-sidebar-foreground',
        )}
      >
        <Icon aria-hidden="true" className={cn('size-4 shrink-0', current && 'text-sidebar-accent')} />
        {collapsed ? null : <span className="min-w-0 flex-1 truncate">{label}</span>}
      </Link>
    );
  };

  // Administration only for those who may use it; the first of the end sections gets a rule.
  const visible = NAV_MODULES.map((module) => ({ module, items: module.items.filter(allowed) })).filter((v) => v.items.length > 0);
  const firstSection = visible.findIndex((v) => v.module.section);
  return (
    <nav aria-label={t('nav.mainLabel')} className="flex flex-col gap-1" data-testid="main-nav" data-collapsed={collapsed || undefined}>
      {collapsed && tip ? (
        <span role="tooltip" className="pointer-events-none fixed z-50 -translate-y-1/2 rounded-md bg-foreground px-2.5 py-1 text-sm whitespace-nowrap text-background shadow-raised"
          style={tip.rtl ? { top: tip.top, right: tip.x } : { top: tip.top, left: tip.x }} data-testid="nav-tooltip">
          {tip.label}
        </span>
      ) : null}
      {visible.map(({ module, items }, index) => {
        const border = index === firstSection;
        const key = (item: NavItem) => `${item.path}${item.hash ?? ''}${item.query ?? ''}`;
        if (collapsed) {
          // Icon-only: every destination as an icon with its name as a tooltip; modules apart.
          return (
            <ul key={module.id} aria-label={t(module.label)} data-module={module.id}
              className={cn('flex flex-col gap-0.5', border ? 'mt-3 border-t border-sidebar-border pt-3' : 'border-t border-sidebar-border/60 pt-1 first:border-0 first:pt-0')}>
              {items.map((item) => <li key={key(item)}>{link(item, false)}</li>)}
            </ul>
          );
        }
        const holdsCurrent = items.some((item) => isCurrentItem(item, pathname, hash, search));
        const expanded = open[module.id] ?? true;
        const ModuleIcon = module.icon;
        const listId = `nav-module-${module.id}`;
        return (
          <div key={module.id} className={cn('flex flex-col gap-0.5', border && 'mt-3 border-t border-sidebar-border pt-3')} data-module={module.id}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={listId}
              onClick={() => toggle(module.id, expanded)}
              className={cn(
                'flex min-h-10 items-center gap-3 rounded-lg px-3 py-1.5 text-start text-sm font-semibold transition-colors hover:bg-sidebar-active/70',
                holdsCurrent ? 'text-sidebar-foreground' : 'text-sidebar-muted hover:text-sidebar-foreground',
              )}
              data-testid={`nav-module-${module.id}`}
            >
              <ModuleIcon aria-hidden="true" className={cn('size-4 shrink-0', holdsCurrent && 'text-sidebar-accent')} />
              <span className="min-w-0 flex-1">{t(module.label)}</span>
              <ChevronDown aria-hidden="true" className={cn('size-4 shrink-0 transition-transform duration-200', expanded && 'rotate-180')} />
            </button>
            {expanded ? (
              <ul id={listId} className="nav-expand flex flex-col gap-0.5">
                {items.map((item) => <li key={key(item)}>{link(item, true)}</li>)}
              </ul>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
