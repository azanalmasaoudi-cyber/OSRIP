import { Layers } from 'lucide-react';
import { Link, type To } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ApiRequestError } from '@/api/client';
import { Button, buttonVariants } from '@/components/ui/button';
import { PERIOD_KINDS } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';

/** Period kinds a reader can choose: a year-to-date total is never shown beside a full year. */
export const FREQUENCIES = PERIOD_KINDS;
export type Frequency = (typeof FREQUENCIES)[number];

/**
 * The API refuses a read that would show annual, year-to-date, quarterly, monthly or
 * statement values of one indicator side by side (booklet 3.12). Returns the period
 * kinds involved, or null when the error is something else.
 */
export function mixedFrequencies(error: unknown): Frequency[] | null {
  if (!(error instanceof ApiRequestError) || error.code !== 'incompatible_series') return null;
  const details = (error.details ?? {}) as Record<string, { frequency?: string; period_kind?: string }[]>;
  const found = new Set<string>();
  for (const combos of Object.values(details)) {
    for (const c of combos) {
      const kind = c.period_kind ?? c.frequency;
      if (kind) found.add(kind);
    }
  }
  return FREQUENCIES.filter((f) => found.has(f));
}

/** Explains the refusal and lets the reader choose one period kind (a filter or a link). */
export function MixedFrequencyNotice({ frequencies, onChoose, hrefFor }: {
  frequencies: Frequency[];
  onChoose?: (frequency: Frequency) => void;
  hrefFor?: (frequency: Frequency) => To;
}) {
  const { t } = useTranslation();
  return (
    <div role="status" data-state="mixed_frequency"
      className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-border-strong/50 bg-card/60 p-6 sm:flex-row sm:gap-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sand-subtle text-sand-foreground">
        <Layers aria-hidden="true" className="size-5" />
      </span>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="font-semibold">{t('states.mixedFrequencyTitle')}</p>
        <p className="max-w-prose text-sm text-muted-foreground">{t('states.mixedFrequency')}</p>
        <div className="flex flex-wrap gap-2">
          {frequencies.map((f) =>
            hrefFor ? (
              <Link key={f} to={hrefFor(f)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
                {t('states.showFrequency', { frequency: t(FREQUENCY_KEY[f]) })}
              </Link>
            ) : (
              <Button key={f} variant="outline" size="sm" onClick={() => onChoose?.(f)} data-testid={`choose-frequency-${f}`}>
                {t('states.showFrequency', { frequency: t(FREQUENCY_KEY[f]) })}
              </Button>
            ),
          )}
        </div>
      </div>
    </div>
  );
}
