import { Outlet } from 'react-router';
import { useTranslation } from 'react-i18next';

import { WelcomeFooter, WelcomeStage, WelcomeTopBar } from './WelcomeChrome';

/**
 * The full-screen sign-in layout, in the owner's welcome design (welcome.css): the soft glows and
 * grid, the brand linking home, the language and theme chips, and the footer. The showcase and
 * the form are the page itself (pages/SignInPage.tsx).
 */
export function AuthLayout() {
  const { t } = useTranslation();
  return (
    <WelcomeStage className="flex flex-col" data-testid="auth-stage">
      <a href="#main" className="sr-only z-50 rounded-md bg-card font-medium text-foreground shadow-card focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:px-4 focus:py-2">
        {t('app.skipToContent')}
      </a>
      <WelcomeTopBar />
      <main id="main" tabIndex={-1} className="ow-frame w-full flex-1 outline-none">
        <Outlet />
      </main>
      <WelcomeFooter />
    </WelcomeStage>
  );
}
