import { Languages } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LANGUAGE_KEY } from '@/i18n/keys';
import { SUPPORTED_LANGUAGES } from '@/i18n/languages';
import { cn } from '@/lib/utils';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Changes labels and direction only; the URL (data mode, page filters) is left
 * untouched, so every selection and value is preserved (T08).
 */
export function LanguageSwitcher({ tone = 'light', className }: { tone?: 'light' | 'nav'; className?: string }) {
  const { t, i18n } = useTranslation();
  const current = useAppLanguage();

  return (
    <div
      role="group"
      aria-label={t('language.label')}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border p-0.5',
        tone === 'nav' ? 'on-nav border-nav-muted/40' : 'border-border-strong/60 bg-card',
        className,
      )}
    >
      <Languages aria-hidden="true" className={cn('mx-1.5 size-4', tone === 'nav' ? 'text-nav-muted' : 'text-muted-foreground')} />
      {SUPPORTED_LANGUAGES.map((lng) => {
        const active = current === lng;
        return (
          <button
            key={lng}
            type="button"
            lang={lng}
            aria-pressed={active}
            onClick={() => void i18n.changeLanguage(lng)}
            className={cn(
              'min-h-8 rounded px-3 text-sm transition-colors',
              active && tone === 'light' && 'bg-primary font-medium text-primary-foreground',
              active && tone === 'nav' && 'bg-nav-foreground font-medium text-nav',
              !active && tone === 'light' && 'text-foreground hover:bg-muted',
              !active && tone === 'nav' && 'text-nav-foreground hover:bg-nav-active',
            )}
          >
            {t(LANGUAGE_KEY[lng])}
          </button>
        );
      })}
    </div>
  );
}
