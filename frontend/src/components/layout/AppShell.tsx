import { Menu, Search } from 'lucide-react';
import { MotionConfig, motion } from 'motion/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
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
import { NAV_ITEMS, SidebarNav } from './SidebarNav';
import { StatusBanners } from './StatusBanners';
import { ThemeSelector } from './ThemeSelector';
import { BrandMark } from '@/components/brand/BrandMark';
import { Dialog } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <Link to={to('/')} onClick={onNavigate} className="flex min-w-0 items-center gap-2.5 rounded-md">
      <BrandMark className="size-8" />
      <span className="min-w-0">
        <span className="block text-sm leading-tight font-semibold">{t('app.shortName')}</span>
        <span className="block text-[0.6875rem] leading-snug text-sidebar-muted">{t('app.fullName')}</span>
      </span>
    </Link>
  );
}

/** The current page's name for the top bar: its navigation label, or the nearest fitting one. */
function usePageTitle(pathname: string): string {
  const { t } = useTranslation();
  if (pathname === '/') return t('nav.home');
  if (pathname === '/talk') return t('nav.aiAssistant');
  if (pathname === '/energy') return t('nav.electricity');
  if (['/sign-in', '/register', '/forgot-password', '/reset-password', '/magic-link', '/verify-email', '/link-email'].includes(pathname)) {
    return t('nav.accountShort');
  }
  const match = [...NAV_ITEMS].sort((a, b) => b.path.length - a.path.length)
    .find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));
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
  const { pathname, hash } = useLocation();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  // The introduction opens the home page once per browser session: a direct link (a study, the
  // workspace, sign-in, the account) opens straight away. Replayable from the footer and Settings.
  const [entranceOpen, setEntranceOpen] = useState(() => pathname === '/' && introDue());
  const replayEntrance = useCallback(() => setEntranceOpen(true), []);
  // Arriving at the home page later in the session (after a direct link) also opens it, once
  // (adjusting state while rendering, as React recommends instead of an effect).
  const [introPath, setIntroPath] = useState(pathname);
  if (introPath !== pathname) {
    setIntroPath(pathname);
    if (pathname === '/' && introDue()) setEntranceOpen(true);
  }
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
    <div className="min-h-dvh bg-background text-foreground lg:grid lg:grid-cols-[var(--sidebar-width)_minmax(0,1fr)] print:block">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card font-medium text-foreground shadow-card focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:px-4 focus:py-2"
      >
        {t('app.skipToContent')}
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden border-e border-sidebar-border bg-sidebar text-sidebar-foreground lg:block print:hidden">
        <div className="sticky top-0 flex h-dvh flex-col">
          <div className="flex h-14 shrink-0 items-center border-b border-sidebar-border px-4">
            <Brand />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-4">
            <SidebarNav />
          </div>
          <div className="flex shrink-0 flex-col gap-3 border-t border-sidebar-border px-3 py-3">
            <DataModeSelector />
            <p className="text-[0.6875rem] leading-relaxed text-sidebar-muted">{t('app.identityNote')}</p>
          </div>
        </div>
      </aside>

      <div className={cn('flex min-w-0 flex-col', isChat ? 'h-dvh' : 'min-h-dvh')}>
        {/* Top bar: page title, search, language, theme and account */}
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md print:hidden" data-testid="top-bar">
          <div className="flex h-14 items-center gap-1.5 px-3 sm:gap-2 sm:px-4 lg:px-6">
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
            <p className="flex min-w-0 flex-1 items-center gap-1.5 text-sm" data-testid="page-title">
              <span className="hidden text-muted-foreground sm:inline">{t('app.shortName')}</span>
              <span aria-hidden="true" className="hidden text-muted-foreground/60 sm:inline">/</span>
              <span className="truncate font-medium">{title}</span>
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

        <Dialog open={menuOpen} onClose={() => setMenuOpen(false)} title={t('nav.menuTitle')} placement="start">
          <div className="flex flex-col gap-5" data-testid="mobile-menu">
            <Brand onNavigate={() => setMenuOpen(false)} />
            <div className="flex flex-col gap-3">
              <ThemeSelector />
              <DataModeSelector />
            </div>
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
            <p className="text-xs leading-relaxed text-sidebar-muted">{t('app.identityNote')}</p>
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
            : cn('flex-1 pb-24', !isHome && 'px-4 pt-6 sm:px-6 lg:px-8'))}
        >
          {/* Keyed by route: a short entrance on page change, never an exit animation, so
              back/forward and the focus move above stay immediate. Under reduced motion
              MotionConfig drops the movement and keeps only the brief fade. */}
          <motion.div
            key={pathname}
            initial={{ opacity: 0.01, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className={cn(!isHome && 'mx-auto w-full max-w-[96rem]', isChat && 'flex min-h-0 flex-1 flex-col')}
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
          <div className="mx-auto flex max-w-[96rem] flex-col gap-3 px-4 pt-5 pb-24 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:pe-28 sm:pb-5 lg:px-8 lg:pe-28">
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
      {pathname === '/talk' ? null : <AssistantOrb />}
      <Entrance open={entranceOpen} onClose={(action) => {
        setEntranceOpen(false);
        // Explore and Skip enter the dashboard (the Overview); Escape only closes.
        if (action !== 'dismiss' && pathname !== '/overview') void navigate(to('/overview'));
      }} />
    </div>
    </EntranceReplayContext.Provider>
    </PersonaProvider>
    </AssistantUiProvider>
    </MotionConfig>
  );
}
