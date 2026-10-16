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
export function LanguageSwitcher({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const current = useAppLanguage();

  return (
    <div role="group" aria-label={t('language.label')}
      className={cn('inline-flex items-center gap-0.5 rounded-md border border-border bg-card p-0.5', className)}>
      <Languages aria-hidden="true" className="mx-1 size-4 text-muted-foreground max-sm:hidden" />
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
              'min-h-7 rounded-[5px] px-2 text-xs transition-colors sm:px-2.5',
              active ? 'bg-muted font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(LANGUAGE_KEY[lng])}
          </button>
        );
      })}
    </div>
  );
}
