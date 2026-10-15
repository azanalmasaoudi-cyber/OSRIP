import { Menu } from 'lucide-react';
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
import { Entrance, entranceSeen } from './Entrance';
import { EntranceReplayContext } from './entranceControl';
import { LanguageSwitcher } from './LanguageSwitcher';
import { SidebarNav } from './SidebarNav';
import { StatusBanners } from './StatusBanners';
import { BrandMark, CrenellationDivider, LatticeBackdrop } from '@/components/brand/BrandMark';
import { Dialog } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <Link to={to('/')} onClick={onNavigate} className="flex min-w-0 items-center gap-3 rounded-md">
      <BrandMark />
      <span className="min-w-0">
        <span className="block text-lg leading-tight font-semibold">{t('app.shortName')}</span>
        <span className="block text-xs leading-snug text-nav-muted">{t('app.fullName')}</span>
      </span>
    </Link>
  );
}

/** Shown while the signed-in account still has a temporary password (enforced by the server). */
function PasswordChangeBanner() {
  const { t } = useTranslation();
  const me = useMe();
  const to = usePreservedSearch();
  const { pathname } = useLocation();
  if (!me.data?.password_change_required || pathname === '/account') return null;
  return (
    <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-copper/40 bg-copper-subtle px-4 py-2 text-sm text-copper-foreground sm:px-6 lg:px-10"
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
  const [entranceOpen, setEntranceOpen] = useState(() => !entranceSeen());
  const replayEntrance = useCallback(() => setEntranceOpen(true), []);
  const mainRef = useRef<HTMLElement>(null);
  const handledLocation = useRef<string | null>(null);
  const isHome = pathname === '/';

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
      <aside className="on-nav relative hidden bg-nav text-nav-foreground lg:block print:hidden">
        <div className="sticky top-0 flex h-dvh flex-col overflow-y-auto">
          <LatticeBackdrop className="bg-nav-foreground/[0.06]" />
          <div className="relative px-5 pt-6 pb-5">
            <Brand />
          </div>
          <CrenellationDivider className="relative bg-nav-ring/50" />
          <div className="relative flex-1 px-3 py-6">
            <SidebarNav />
          </div>
          <p className="relative px-5 pb-5 text-xs leading-relaxed text-nav-muted">{t('app.identityNote')}</p>
        </div>
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-col">
        {/* Mobile top bar */}
        <header className="on-nav sticky top-0 z-30 flex items-center gap-2 bg-nav px-3 py-2 text-nav-foreground lg:hidden print:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={menuOpen}
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-nav-active"
            data-testid="open-menu"
          >
            <Menu aria-hidden="true" className="size-6" />
            <span className="sr-only">{t('nav.openMenu')}</span>
          </button>
          <Link to={to('/')} className="flex min-w-0 flex-1 items-center gap-2 rounded-md">
            <BrandMark className="size-8" />
            <span className="truncate font-semibold">{t('app.shortName')}</span>
          </Link>
          <LanguageSwitcher tone="nav" />
        </header>

        <Dialog open={menuOpen} onClose={() => setMenuOpen(false)} title={t('nav.menuTitle')} placement="start">
          <div className="flex flex-col gap-6" data-testid="mobile-menu">
            <Brand onNavigate={() => setMenuOpen(false)} />
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
            <p className="text-xs leading-relaxed text-nav-muted">{t('app.identityNote')}</p>
          </div>
        </Dialog>

        <div className="print:hidden"><StatusBanners /><PasswordChangeBanner /></div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6 lg:px-10 print:hidden">
          <DataModeSelector />
          <div className="flex flex-wrap items-center gap-3">
            <AccountControl />
            <LanguageSwitcher className="hidden lg:inline-flex" />
          </div>
        </div>

        <main
          id="main"
          ref={mainRef}
          tabIndex={-1}
          // Bottom padding keeps the floating assistant orb clear of the last content.
          className={cn('flex-1 pb-24 outline-none', !isHome && 'px-4 pt-8 sm:px-6 lg:px-10 lg:pt-10')}
        >
          {/* Keyed by route: a short entrance on page change, never an exit animation, so
              back/forward and the focus move above stay immediate. Under reduced motion
              MotionConfig drops the movement and keeps only the brief fade. */}
          <motion.div
            key={pathname}
            initial={{ opacity: 0.01, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className={cn(!isHome && 'mx-auto w-full max-w-6xl')}
            data-testid="route-transition"
          >
            <ErrorBoundary resetKey={pathname} fallback={(reset) => (
              <StatePanel kind="error" detail={t('states.pageFailed')} onRetry={reset} />
            )}>
              <Outlet />
            </ErrorBoundary>
          </motion.div>
        </main>

        <footer className="mt-12 bg-card print:hidden">
          <CrenellationDivider className="bg-sand/40" />
          <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 pt-6 pb-24 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:pe-28 sm:pb-6 lg:px-10 lg:pe-28">
            <p className="max-w-2xl">
              {t('footer.disclaimer')} {t('app.identityNote')}
            </p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              <li>
                <Link to={{ ...to('/sources'), hash: '#image-credits' }} className="underline underline-offset-2 hover:no-underline">
                  {t('footer.credits')}
                </Link>
              </li>
              <li>
                <Link to={to('/design-reference')} className="underline underline-offset-2 hover:no-underline">
                  {t('footer.designReference')}
                </Link>
              </li>
              <li>
                <button type="button" onClick={replayEntrance} className="underline underline-offset-2 hover:no-underline"
                  data-testid="replay-entrance">
                  {t('entrance.replay')}
                </button>
              </li>
            </ul>
          </div>
        </footer>
      </div>
      {pathname === '/talk' ? null : <AssistantOrb />}
      <Entrance open={entranceOpen} onClose={(explore) => {
        setEntranceOpen(false);
        // Explore from the home page opens the overview; a direct link stays where it pointed.
        if (explore && pathname === '/') void navigate(to('/overview'));
      }} />
    </div>
    </EntranceReplayContext.Provider>
    </PersonaProvider>
    </AssistantUiProvider>
    </MotionConfig>
  );
}
