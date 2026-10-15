import { FlaskConical, Info, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { apiBaseUrl, dataAdapter } from '@/api';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

/** Persistent statements of what the user is looking at: data mode and backend status. */
export function StatusBanners() {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const ModeIcon = mode === 'synthetic' ? FlaskConical : ShieldCheck;

  return (
    <div className="flex flex-col">
      <p
        data-testid="prototype-notice"
        className="flex items-center justify-center gap-2 border-b border-border bg-muted px-4 py-1.5 text-center text-xs text-muted-foreground"
      >
        <Info aria-hidden="true" className="size-3.5 shrink-0" />
        {dataAdapter.kind === 'mock' ? t('prototype.mockAdapter') : t('prototype.httpAdapter', { baseUrl: apiBaseUrl })}
      </p>
      <p
        role="status"
        data-testid="data-mode-banner"
        data-mode={mode}
        className={cn(
          'flex items-center justify-center gap-2 border-b px-4 py-2 text-center text-sm font-medium',
          mode === 'synthetic'
            ? 'border-synthetic-border bg-synthetic text-synthetic-foreground'
            : 'border-verified-border bg-verified text-verified-foreground',
        )}
      >
        <ModeIcon aria-hidden="true" className="size-4 shrink-0" />
        {mode === 'synthetic' ? t('dataMode.syntheticBanner') : t('dataMode.verifiedBanner')}
      </p>
    </div>
  );
}
