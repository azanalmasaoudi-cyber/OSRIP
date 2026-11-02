import { Outlet, Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { LanguageSwitcher } from './LanguageSwitcher';
import { ThemeSelector } from './ThemeSelector';
import { BrandMark } from '@/components/brand/BrandMark';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * The full-screen sign-in layout: a slow, soft light over the page (still under reduced motion),
 * the brand linking home, and the language and theme controls. The form sits in a glass card
 * at the centre (pages/SignInPage.tsx).
 */
export function AuthLayout() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <div className="auth-stage relative isolate flex min-h-dvh flex-col overflow-clip bg-background text-foreground">
      <div aria-hidden="true" className="auth-light auth-light-1" />
      <div aria-hidden="true" className="auth-light auth-light-2" />
      <a href="#main" className="sr-only z-50 rounded-md bg-card font-medium text-foreground shadow-card focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:px-4 focus:py-2">
        {t('app.skipToContent')}
      </a>
      <header className="flex items-center justify-between gap-3 px-4 py-4 sm:px-8" data-testid="auth-top-bar">
        <Link to={to('/')} className="flex min-w-0 items-center gap-3 rounded-lg">
          <BrandMark className="size-9 shrink-0" />
          <span className="min-w-0">
            <span className="block text-base leading-tight font-semibold ltr:tracking-wide">{t('app.shortName')}</span>
            <span className="block truncate text-xs text-muted-foreground max-sm:hidden">{t('app.fullName')}</span>
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeSelector compact />
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex flex-1 items-center justify-center px-4 pt-4 pb-16 outline-none sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
