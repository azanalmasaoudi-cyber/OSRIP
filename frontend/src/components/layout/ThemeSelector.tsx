import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { useRef, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Segmented } from '@/components/ui/segmented';
import { THEME_PREFERENCES, useThemePreference, type ThemePreference } from '@/lib/theme';
import { cn } from '@/lib/utils';

const ICON: Record<ThemePreference, LucideIcon> = { light: Sun, dark: Moon, system: Monitor };

/**
 * Light, Dark or System. `compact` (the top bar): three icon buttons in a radio group, each
 * with its name as the accessible label and tooltip; otherwise the labelled segmented control
 * (Settings). Arrow keys move the choice, mirrored in right-to-left layouts.
 */
export function ThemeSelector({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t } = useTranslation();
  const [preference, setPreference] = useThemePreference();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  if (!compact) {
    return (
      <Segmented label={t('theme.label')} value={preference} onChange={setPreference} className={className} testId="theme-options"
        options={THEME_PREFERENCES.map((p) => ({ value: p, label: t(`theme.${p}`) }))} />
    );
  }

  const index = THEME_PREFERENCES.indexOf(preference);
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    let next = index;
    if (event.key === (rtl ? 'ArrowLeft' : 'ArrowRight') || event.key === 'ArrowDown') next = (index + 1) % THEME_PREFERENCES.length;
    else if (event.key === (rtl ? 'ArrowRight' : 'ArrowLeft') || event.key === 'ArrowUp') next = (index - 1 + THEME_PREFERENCES.length) % THEME_PREFERENCES.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = THEME_PREFERENCES.length - 1;
    else return;
    event.preventDefault();
    const choice = THEME_PREFERENCES[next];
    if (choice) setPreference(choice);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={t('theme.label')} data-testid="theme-selector"
      className={cn('inline-flex items-center gap-0.5 rounded-md border border-border bg-card p-0.5', className)}>
      {THEME_PREFERENCES.map((p, i) => {
        const Icon = ICON[p];
        const checked = p === preference;
        return (
          <button key={p} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={checked}
            aria-label={t(`theme.${p}`)} title={t(`theme.${p}`)} tabIndex={checked ? 0 : -1} data-value={p}
            onClick={() => setPreference(p)} onKeyDown={onKeyDown}
            className={cn('inline-flex size-7 items-center justify-center rounded-[5px] transition-colors pointer-coarse:size-10',
              checked ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>
            <Icon aria-hidden="true" className="size-4" />
          </button>
        );
      })}
    </div>
  );
}
