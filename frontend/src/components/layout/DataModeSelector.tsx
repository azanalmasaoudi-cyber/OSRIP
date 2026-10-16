import { ChevronDown } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { DATA_MODES } from '@/domain/types';
import { DATA_MODE_KEY } from '@/i18n/keys';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

/** Explicit, deliberate choice of data mode (booklet 3.4): the sidebar footer and the phone menu. */
export function DataModeSelector({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [mode, setMode] = useDataMode();
  const id = useId();

  return (
    <div className={cn('flex min-w-0 flex-col gap-1 text-sm', className)}>
      <label htmlFor={id} className="text-[0.6875rem] font-medium text-sidebar-muted ltr:tracking-wider ltr:uppercase">
        {t('dataMode.label')}
      </label>
      <div className="relative min-w-0">
        <select
          id={id}
          value={mode}
          onChange={(event) => {
            const next = DATA_MODES.find((m) => m === event.target.value);
            if (next) setMode(next);
          }}
          className="h-9 w-full appearance-none truncate rounded-md border border-border bg-card ps-2.5 pe-8 text-sm text-foreground hover:border-border-strong"
          data-testid="data-mode-select"
        >
          {DATA_MODES.map((m) => (
            <option key={m} value={m}>
              {t(DATA_MODE_KEY[m])}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute end-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      </div>
    </div>
  );
}
