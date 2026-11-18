import { FlaskConical, FolderOpen, LineChart, SlidersHorizontal, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** The Al Mulhim conversation with a request written for the person (never sent by itself). */
export function useAskMulhim() {
  const to = usePreservedSearch();
  return (question: string) => to(`/assistant?${new URLSearchParams({ q: question }).toString()}`);
}

const ASKS: { key: 'study' | 'forecast' | 'scenario'; icon: LucideIcon }[] = [
  { key: 'study', icon: FlaskConical },
  { key: 'forecast', icon: LineChart },
  { key: 'scenario', icon: SlidersHorizontal },
];

/**
 * Studies, forecasts and hypothetical scenarios are run by Al Mulhim from a sentence (there is no
 * separate page for them in the navigation). Here, for the indicator and area being analysed,
 * each button opens the conversation with that request already written in the person's
 * language; they read it, change it if they like, and send it.
 */
export function AskMulhim({ indicator, area, className }: { indicator: string; area: string; className?: string }) {
  const { t } = useTranslation();
  const ask = useAskMulhim();
  const to = usePreservedSearch();
  return (
    <section aria-labelledby="ask-mulhim-h" className={cn('flex flex-col gap-3 rounded-lg border border-border border-t-4 border-t-copper bg-card p-4 shadow-card sm:p-5', className)}
      data-testid="sector-ask-mulhim">
      <h2 id="ask-mulhim-h" className="text-base font-semibold">{t('sector.ask.heading')}</h2>
      <p className="text-sm text-muted-foreground">{t('sector.ask.lead')}</p>
      <div className="flex flex-wrap gap-2">
        {ASKS.map(({ key, icon: Icon }) => (
          <Link key={key} to={ask(t(`sector.ask.${key}`, { indicator, area }))}
            className={buttonVariants({ variant: key === 'study' ? 'default' : 'outline', size: 'sm' })} data-testid={`sector-ask-${key}`}>
            <Icon aria-hidden="true" />{t(`sector.ask.${key}Button`)}
          </Link>
        ))}
      </div>
      <Link to={to('/studies')} className="inline-flex w-fit items-center gap-1.5 text-sm text-primary underline underline-offset-4" data-testid="sector-saved-studies">
        <FolderOpen aria-hidden="true" className="size-4" />{t('sector.ask.savedStudies')}
      </Link>
    </section>
  );
}
