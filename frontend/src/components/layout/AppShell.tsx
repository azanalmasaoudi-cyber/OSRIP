import { LogIn, Menu, PanelLeftClose, PanelLeftOpen, Search } from 'lucide-react';
import { MotionConfig, motion } from 'motion/react';
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { useRoleLabel } from '@/components/admin/AccessControl';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { StatePanel } from '@/components/common/StatePanel';
import { AssistantUiProvider } from '@/components/assistant/AssistantContext';
import { AssistantOrb } from '@/components/assistant/AssistantOrb';
import { PersonaProvider } from '@/components/assistant/persona';
import { AccountControl } from './AccountControl';
import { DataModeSelector } from './DataModeSelector';
import { Entrance, introDue } from './Entrance';
import { EntranceReplayContext } from './entranceControl';
import { GlobalSearch } from './GlobalSearch';
import { LanguageSwitcher } from './LanguageSwitcher';
import { NAV_ITEMS, SidebarNav, isCurrentItem } from './SidebarNav';
import { StatusBanners } from './StatusBanners';
import { ThemeSelector } from './ThemeSelector';
import { BrandMark } from '@/components/brand/BrandMark';
import { Dialog } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

function Brand({ onNavigate, compact = false }: { onNavigate?: () => void; compact?: boolean }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <Link to={to('/')} onClick={onNavigate} className="flex min-w-0 items-center gap-3 rounded-lg" aria-label={compact ? t('app.shortName') : undefined}>
      <BrandMark className="size-9 shrink-0" />
      {compact ? null : (
        <span className="min-w-0">
          <span className="block text-base leading-tight font-semibold ltr:tracking-wide">{t('app.shortName')}</span>
          <span className="block text-xs leading-snug text-sidebar-muted">{t('app.fullName')}</span>
        </span>
      )}
    </Link>
  );
}

const COLLAPSED_KEY = 'osrip.nav.collapsed';

/** The desktop sidebar's width: full, or icons only (remembered in this browser). */
function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSED_KEY) === '1';
    } catch {
      return false;
    }
  });
  const toggle = () => setCollapsed((now) => {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, now ? '0' : '1');
    } catch {
      // Storage blocked: the choice lasts for this page only.
    }
    return !now;
  });
  return [collapsed, toggle];
}

/** The signed-in person at the foot of the sidebar (name and first role), or Sign in. */
function ProfileCard({ compact }: { compact: boolean }) {
  const { t } = useTranslation();
  const me = useMe();
  const to = usePreservedSearch();
  const roleLabel = useRoleLabel();
  if (!me.data?.authenticated) {
    return (
      <Link to={to('/sign-in')} className={cn('flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-sidebar-foreground hover:bg-sidebar-active/70', compact && 'justify-center px-0')}
        aria-label={compact ? t('auth.submit') : undefined} data-testid="sidebar-sign-in">
        <LogIn aria-hidden="true" className="size-4 shrink-0" />{compact ? null : t('auth.submit')}
      </Link>
    );
  }
  const name = me.data.display_name || me.data.username || '';
  const role = me.data.roles[0];
  return (
    <Link to={to('/account')} className={cn('flex min-h-12 items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-sidebar-active/70', compact && 'justify-center px-0')}
      aria-label={compact ? name : undefined} data-testid="sidebar-profile">
      <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-sm font-semibold text-primary-foreground">
        {name.slice(0, 1).toUpperCase() || '?'}
      </span>
      {compact ? null : (
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-sidebar-foreground">{name}</span>
          <span className="block truncate text-xs text-sidebar-muted">{role ? roleLabel(role) : t('nav.accountShort')}</span>
        </span>
      )}
    </Link>
  );
}

/** The current page's name for the top bar: its navigation label, or the nearest fitting one. */
function usePageTitle(pathname: string): string {
  const { t } = useTranslation();
  const { hash, search } = useLocation();
  if (pathname === '/') return t('nav.dashboard');
  if (pathname === '/energy') return t('nav.electricity');
  if (['/sign-in', '/register', '/forgot-password', '/reset-password', '/magic-link', '/verify-email', '/link-email'].includes(pathname)) {
    return t('nav.accountShort');
  }
  // The item for this page and its open section or tab, the most specific path first.
  const match = [...NAV_ITEMS].sort((a, b) => b.path.length - a.path.length)
    .find((item) => item.path !== '/' && isCurrentItem(item, pathname, hash, search));
  return match ? t(match.key) : t('app.shortName');
}

/** Shown while the signed-in account still has a temporary password (enforced by the server). */
function PasswordChangeBanner() {
  const { t } = useTranslation();
  const me = useMe();
  const to = usePreservedSearch();
  const { pathname } = useLocation();
  if (!me.data?.password_change_required || pathname === '/account') return null;
  return (
    <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-copper/40 bg-copper-subtle px-4 py-2 text-sm text-copper-foreground sm:px-6 lg:px-8"
      data-testid="password-change-banner">
      <span className="font-medium">{t('account.changeRequiredTitle')}</span>
      <Link to={to('/account')} className="underline underline-offset-2">{t('account.changePassword')}</Link>
    </p>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const { pathname, hash } = location;
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();
  // The welcome opens the home page once per browser session: a direct link (a study, the
  // workspace, sign-in, the account) opens straight away. Shown again from the footer, Settings
  // and the sign-in page's "Back to introduction" (which navigates here with { welcome: true }).
  const welcomeAsked = (location.state as { welcome?: boolean } | null)?.welcome === true;
  const [entranceOpen, setEntranceOpen] = useState(() => pathname === '/' && (welcomeAsked || introDue()));
  const replayEntrance = useCallback(() => setEntranceOpen(true), []);
  // Arriving at the home page later in the session (after a direct link) also opens it, once
  // (adjusting state while rendering, as React recommends instead of an effect).
  const [introPath, setIntroPath] = useState(pathname);
  if (introPath !== pathname) {
    setIntroPath(pathname);
    if (pathname === '/' && (welcomeAsked || introDue())) setEntranceOpen(true);
  }
  // The request is used once: a reload of the home page does not show the welcome again.
  useEffect(() => {
    if (welcomeAsked) void navigate({ pathname, search: location.search, hash }, { replace: true, state: null });
  }, [welcomeAsked, navigate, pathname, location.search, hash]);
  const mainRef = useRef<HTMLElement>(null);
  const handledLocation = useRef<string | null>(null);
  const isHome = pathname === '/';
  // The AI Assistant is a conversation that fills the window: one screen tall, one scrolling area.
  const isChat = pathname === '/assistant';
  const title = usePageTitle(pathname);

  // After client-side navigation, move focus to the new page and scroll to the
  // top, as a full page load would; a #hash target gets scrolled to and focused
  // instead. Filter changes (query only) do not move focus.
  // Compares with the last handled location (not a first-render flag) so that
  // StrictMode's double-run of effects cannot steal focus on initial load.
  useEffect(() => {
    const key = `${pathname}${hash}`;
    if (handledLocation.current === key) return;
    const isInitialLoad = handledLocation.current === null;
    handledLocation.current = key;
    const target = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
    if (target) {
      target.scrollIntoView();
      target.focus({ preventScroll: true });
      return;
    }
    if (isInitialLoad) return;
    window.scrollTo({ top: 0, behavior: 'instant' });
    mainRef.current?.focus({ preventScroll: true });
  }, [pathname, hash]);

  return (
    <MotionConfig reducedMotion="user">
    <AssistantUiProvider>
    <PersonaProvider>
    <EntranceReplayContext.Provider value={replayEntrance}>
    <div className="min-h-dvh bg-background text-foreground lg:grid lg:grid-cols-[var(--sidebar-current)_minmax(0,1fr)] lg:transition-[grid-template-columns] lg:duration-200 print:block"
      style={{ '--sidebar-current': collapsed ? 'var(--sidebar-width-collapsed)' : 'var(--sidebar-width)' } as CSSProperties}>
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card font-medium text-foreground shadow-card focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:px-4 focus:py-2"
      >
        {t('app.skipToContent')}
      </a>

      {/* Desktop sidebar: follows the theme, with its own focus ring (.on-sidebar) */}
      <aside className="on-sidebar sidebar-glass hidden min-w-0 border-e border-sidebar-border text-sidebar-foreground lg:block print:hidden" data-testid="sidebar" data-collapsed={collapsed || undefined}>
        <div className="sticky top-0 flex h-dvh flex-col">
          <div className={cn('flex h-16 shrink-0 items-center gap-2 border-b border-sidebar-border', collapsed ? 'justify-center px-2' : 'px-4')}>
            <Brand compact={collapsed} />
          </div>
          <div className={cn('min-h-0 flex-1 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}>
            <SidebarNav collapsed={collapsed} />
          </div>
          <div className={cn('flex shrink-0 flex-col gap-2 border-t border-sidebar-border py-3', collapsed ? 'px-2' : 'px-3')}>
            {collapsed ? null : <DataModeSelector />}
            <ProfileCard compact={collapsed} />
            <button type="button" onClick={toggleCollapsed} aria-pressed={collapsed}
              className={cn('flex min-h-9 items-center gap-3 rounded-lg px-3 text-sm text-sidebar-muted hover:bg-sidebar-active/70 hover:text-sidebar-foreground', collapsed && 'justify-center px-0')}
              data-testid="sidebar-collapse">
              {collapsed ? <PanelLeftOpen aria-hidden="true" className="size-4 shrink-0 rtl:-scale-x-100" /> : <PanelLeftClose aria-hidden="true" className="size-4 shrink-0 rtl:-scale-x-100" />}
              <span className={cn(collapsed && 'sr-only')}>{collapsed ? t('nav.expand') : t('nav.collapse')}</span>
            </button>
          </div>
        </div>
      </aside>

      <div className={cn('flex min-w-0 flex-col', isChat ? 'h-dvh' : 'min-h-dvh')}>
        {/* Top bar: page title, search, language, theme and account */}
        <header className="topbar-glass sticky top-0 z-30 border-b print:hidden" data-testid="top-bar">
          <div className="mx-auto flex h-16 max-w-[var(--content-max)] items-center gap-1.5 px-3 sm:gap-2 sm:px-4 lg:px-8">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={menuOpen}
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
              data-testid="open-menu"
            >
              <Menu aria-hidden="true" className="size-5" />
              <span className="sr-only">{t('nav.openMenu')}</span>
            </button>
            <Link to={to('/')} className="shrink-0 rounded-md lg:hidden" aria-label={t('app.shortName')}>
              <BrandMark className="size-7" />
            </Link>
            <p className="flex min-w-0 flex-1 items-center gap-2 text-sm" data-testid="page-title">
              <span className="hidden text-muted-foreground sm:inline">{t('app.shortName')}</span>
              <span aria-hidden="true" className="hidden text-copper sm:inline">/</span>
              <span className="truncate text-base font-semibold">{title}</span>
            </p>
            <GlobalSearch shortcut className="hidden w-56 md:block xl:w-72" />
            <button type="button" onClick={() => setSearchOpen(true)} aria-haspopup="dialog"
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
              data-testid="open-search">
              <Search aria-hidden="true" className="size-4" />
              <span className="sr-only">{t('search.label')}</span>
            </button>
            <LanguageSwitcher />
            <ThemeSelector compact className="max-sm:hidden" />
            <AccountControl />
          </div>
        </header>

        <Dialog open={menuOpen} onClose={() => setMenuOpen(false)} title={t('nav.menuTitle')} placement="start" className="on-sidebar">
          <div className="flex flex-col gap-5" data-testid="mobile-menu">
            <Brand onNavigate={() => setMenuOpen(false)} />
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
            <div className="flex flex-col gap-3 border-t border-sidebar-border pt-4">
              <ThemeSelector />
              <DataModeSelector />
              <ProfileCard compact={false} />
            </div>
          </div>
        </Dialog>

        <Dialog open={searchOpen} onClose={() => setSearchOpen(false)} title={t('search.label')}>
          {searchOpen ? <GlobalSearch focusOnOpen inline onDone={() => setSearchOpen(false)} /> : null}
        </Dialog>

        <div className="print:hidden"><StatusBanners /><PasswordChangeBanner /></div>

        <main
          id="main"
          ref={mainRef}
          tabIndex={-1}
          // Bottom padding keeps the floating assistant orb clear of the last content.
          className={cn('outline-none', isChat ? 'flex min-h-0 flex-1 flex-col px-3 pt-3 sm:px-6'
            : cn('flex-1 pb-24', !isHome && 'px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8'))}
        >
          {/* Keyed by route: a short entrance on page change, never an exit animation, so
              back/forward and the focus move above stay immediate. Under reduced motion
              MotionConfig drops the movement and keeps only the brief fade. */}
          <motion.div
            key={pathname}
            initial={{ opacity: 0.01, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className={cn(!isHome && 'mx-auto w-full max-w-[var(--content-max)]', isChat && 'flex min-h-0 flex-1 flex-col')}
            data-testid="route-transition"
          >
            <ErrorBoundary resetKey={pathname} fallback={(reset) => (
              <StatePanel kind="error" detail={t('states.pageFailed')} onRetry={reset} />
            )}>
              <Outlet />
            </ErrorBoundary>
          </motion.div>
        </main>

        {/* On the conversation page, phones and tablets give the footer's room to the messages
            (the menu keeps the same note). */}
        <footer className={cn('border-t border-border print:hidden', isChat && 'max-lg:hidden')}>
          <div className="mx-auto flex max-w-[var(--content-max)] flex-col gap-3 px-4 pt-5 pb-24 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:pe-28 sm:pb-5 lg:px-8 lg:pe-28">
            <p className="max-w-3xl">
              {t('footer.disclaimer')} {t('app.identityNote')}
            </p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              <li>
                <Link to={{ ...to('/sources'), hash: '#image-credits' }} className="underline-offset-2 hover:text-foreground hover:underline">
                  {t('footer.credits')}
                </Link>
              </li>
              <li>
                <Link to={to('/design-reference')} className="underline-offset-2 hover:text-foreground hover:underline">
                  {t('footer.designReference')}
                </Link>
              </li>
              <li>
                <button type="button" onClick={replayEntrance} className="underline-offset-2 hover:text-foreground hover:underline"
                  data-testid="replay-entrance">
                  {t('entrance.replay')}
                </button>
              </li>
            </ul>
          </div>
        </footer>
      </div>
      <AssistantOrb />
      {/* The opening ends on the page it was opened on: never a redirect. */}
      <Entrance open={entranceOpen} onClose={() => setEntranceOpen(false)} />
    </div>
    </EntranceReplayContext.Provider>
    </PersonaProvider>
    </AssistantUiProvider>
    </MotionConfig>
  );
}
