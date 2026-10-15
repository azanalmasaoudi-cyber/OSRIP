import { ChevronDown } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { DATA_MODES } from '@/domain/types';
import { DATA_MODE_KEY } from '@/i18n/keys';
import { useDataMode } from '@/state/useDataMode';

/** Explicit, deliberate choice of data mode (booklet 3.4). */
export function DataModeSelector() {
  const { t } = useTranslation();
  const [mode, setMode] = useDataMode();
  const id = useId();

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
      <label htmlFor={id} className="font-medium text-muted-foreground">
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
          className="h-10 max-w-full appearance-none rounded-md border border-border-strong bg-card ps-3 pe-9 text-sm hover:border-foreground/60"
          data-testid="data-mode-select"
        >
          {DATA_MODES.map((m) => (
            <option key={m} value={m}>
              {t(DATA_MODE_KEY[m])}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      </div>
    </div>
  );
}
