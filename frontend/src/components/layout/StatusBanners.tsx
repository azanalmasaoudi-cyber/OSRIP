import { FlaskConical, Info, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { dataAdapter } from '@/api';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

/** Persistent statements of what the user is looking at, in one slim strip: the data mode
 * (with what it means) and, in the offline prototype only, that no backend is connected. The
 * API address is technical detail and is listed under Settings › Services instead. */
export function StatusBanners() {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const ModeIcon = mode === 'synthetic' ? FlaskConical : ShieldCheck;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2 text-xs sm:px-6 lg:px-8">
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
      {dataAdapter.kind === 'mock' ? (
        <p data-testid="prototype-notice" className="inline-flex min-w-0 items-start gap-1.5 text-muted-foreground">
          <Info aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          {t('prototype.mockAdapter')}
        </p>
      ) : null}
    </div>
  );
}
