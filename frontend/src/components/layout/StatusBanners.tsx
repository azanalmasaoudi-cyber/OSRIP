import { FlaskConical, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

/** A persistent statement of what the user is looking at, in one slim strip: the data mode, with
 * what it means. Technical details (the API address, the offline prototype, the services) are
 * listed under Settings › Services instead. */
export function StatusBanners() {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const ModeIcon = mode === 'synthetic' ? FlaskConical : ShieldCheck;

  return (
    <div className="border-b border-border bg-card/60">
      <div className="mx-auto flex max-w-[var(--content-max)] flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2 text-xs sm:px-6 lg:px-8">
        <p
          role="status"
          data-testid="data-mode-banner"
          data-mode={mode}
          className={cn(
            'inline-flex min-w-0 items-start gap-1.5 rounded-md border px-2 py-1 font-medium',
            mode === 'synthetic'
              ? 'border-synthetic-border/70 bg-synthetic text-synthetic-foreground'
              : 'border-verified-border/70 bg-verified text-verified-foreground',
          )}
        >
          <ModeIcon aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          {mode === 'synthetic' ? t('dataMode.syntheticBanner') : t('dataMode.verifiedBanner')}
        </p>
      </div>
    </div>
  );
}
