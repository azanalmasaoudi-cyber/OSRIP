import { Moon, Sun } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { resolveTheme, useThemePreference } from '@/lib/theme';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

import './welcome.css';

/*
 * What the welcome and sign-in screens share (welcome.css): the background, the top bar with the
 * brand and the language and theme chips, and the footer. Language and theme are the
 * application's own settings, so a choice made here holds everywhere.
 */

export function WelcomeStage({ children, className, ...rest }: { children: ReactNode; className?: string } & Record<`data-${string}`, string>) {
  return (
    <div className={['ow', className].filter(Boolean).join(' ')} {...rest}>
      <div aria-hidden="true" className="ow-aurora" />
      <div aria-hidden="true" className="ow-grid" />
      {children}
    </div>
  );
}

/** The brand (home), then the language and theme chips. `onHome` runs before going home. */
export function WelcomeTopBar({ onHome }: { onHome?: () => void }) {
  const { t, i18n } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const [preference, setPreference] = useThemePreference();
  const dark = resolveTheme(preference) === 'dark';
  const other = language === 'ar' ? 'en' : 'ar';
  return (
    <header className="ow-topbar" data-testid="welcome-top-bar">
      <Link to={to('/')} onClick={onHome} className="ow-brand" aria-label={t('welcome.home')}>
        <span aria-hidden="true" className="ow-symbol">O</span>
        <span lang="en" dir="ltr">
          <span className="ow-brand-word">OSRIP</span>
          <span className="ow-brand-sub">OMAN RESOURCE INTELLIGENCE</span>
        </span>
      </Link>
      <div className="ow-tools">
        <button type="button" className="ow-chip" onClick={() => void i18n.changeLanguage(other)} lang={other}
          data-testid="welcome-language">
          {other === 'ar' ? 'العربية' : 'English'}
        </button>
        <button type="button" className="ow-chip" onClick={() => setPreference(dark ? 'light' : 'dark')}
          aria-label={dark ? t('welcome.toLightLabel') : t('welcome.toDarkLabel')} data-testid="welcome-theme" data-theme-now={dark ? 'dark' : 'light'}>
          {dark ? <Sun aria-hidden="true" className="size-4" /> : <Moon aria-hidden="true" className="size-4" />}
          {dark ? t('welcome.toLight') : t('welcome.toDark')}
        </button>
      </div>
    </header>
  );
}

export function WelcomeFooter() {
  const { t } = useTranslation();
  return (
    <footer className="ow-footer">
      <span lang="en" dir="ltr">OSRIP © 2026</span>
      <span>{t('footer.disclaimer')}</span>
    </footer>
  );
}
