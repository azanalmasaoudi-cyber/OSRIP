import { ArrowRight, Droplets, LayoutGrid, Ship, Wheat, Zap, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useDashboardSeries } from './useDashboardSeries';
import { mixedFrequencies } from '@/components/common/MixedFrequency';
import { DOMAINS, SECTION_PATHS } from '@/domain/sections';
import type { DomainCode, SectionCode } from '@/domain/types';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export const DOMAIN_TITLE = {
  energy_essential_services: 'pages.energy.title',
  food_security: 'pages.food.title',
  trade: 'pages.trade.title',
} as const satisfies Record<DomainCode, string>;

export const SECTION_TITLE = {
  electricity: 'nav.electricity',
  water: 'nav.water',
  food_security: 'nav.foodSecurity',
  trade: 'nav.trade',
} as const satisfies Record<SectionCode, string>;

export const SECTION_ICON: Record<SectionCode, LucideIcon> = { electricity: Zap, water: Droplets, food_security: Wheat, trade: Ship };
const DOMAIN_ICON: Record<DomainCode, LucideIcon> = { energy_essential_services: Zap, food_security: Wheat, trade: Ship };

/**
 * The three domains with their sections and series counts. Choosing one narrows the whole
 * dashboard; when a domain is chosen only its card is shown, with a way back to all three.
 */
export function DomainOverview({ domain, onPick, frequency }: {
  domain: DomainCode | 'all';
  onPick: (code: DomainCode | 'all') => void;
  frequency?: string;
}) {
  const { t } = useTranslation();
  const visible = DOMAINS.filter((d) => domain === 'all' || d.code === domain);
  return (
    <section aria-labelledby="ws-domains" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ws-domains" className="text-lg font-semibold">{t('dashboard.domains.heading')}</h2>
        {domain !== 'all' ? (
          <button type="button" onClick={() => onPick('all')} data-testid="domain-pick-all"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-sm font-medium text-primary hover:bg-muted">
            <LayoutGrid aria-hidden="true" className="size-4" />{t('dashboard.domains.all')}
          </button>
        ) : null}
      </div>
      <ul className={cn('grid gap-3', domain === 'all' && 'md:grid-cols-3')}>
        {visible.map((d) => {
          const Icon = DOMAIN_ICON[d.code];
          const focused = domain === d.code;
          return (
            <li key={d.code}>
              <article data-testid={`domain-card-${d.code}`} data-focused={focused ? 'true' : undefined}
                className={cn('group relative flex h-full flex-col gap-4 overflow-hidden rounded-lg border bg-card p-5 shadow-card transition-[border-color,box-shadow] duration-200',
                  focused ? 'border-primary/40' : 'border-border hover:border-primary/30 hover:shadow-raised')}>
                <div aria-hidden="true" className={cn('absolute inset-x-0 top-0 h-0.5 transition-colors', focused ? 'bg-primary' : 'bg-copper/50 group-hover:bg-copper')} />
                <div className="flex items-center gap-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Icon aria-hidden="true" className="size-5" />
                  </span>
                  <h3 className="text-pretty font-semibold leading-snug">{t(DOMAIN_TITLE[d.code])}</h3>
                </div>
                <ul className={cn('flex flex-col gap-2 text-sm', focused && 'sm:flex-row sm:gap-3')}>
                  {d.sections.map((s) => <SectionCount key={s} section={s} frequency={frequency} />)}
                </ul>
                {!focused ? (
                  <button type="button" onClick={() => onPick(d.code)} data-testid={`domain-pick-${d.code}`}
                    className="mt-auto inline-flex w-fit items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
                    {t('workspace.domainFocus')}<span className="sr-only">: {t(DOMAIN_TITLE[d.code])}</span>
                    <ArrowRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" />
                  </button>
                ) : null}
              </article>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function SectionCount({ section, frequency }: { section: SectionCode; frequency?: string }) {
  const { t } = useTranslation();
  const data = useDashboardSeries(section, frequency);
  const to = usePreservedSearch();
  const Icon = SECTION_ICON[section];
  const label = data.state === 'loading' ? t('workspace.seriesShort', { n: '…' })
    : data.state === 'error' ? (mixedFrequencies(data.error) ? t('workspace.mixedShort') : '—')
      : t('workspace.seriesShort', { n: data.response.status !== 'ok' ? 0 : data.response.series.length });
  return (
    <li className="flex flex-1 items-center justify-between gap-3 rounded-md bg-muted/70 px-3 py-2">
      <Link to={to(SECTION_PATHS[section])} className="inline-flex min-w-0 items-center gap-2 font-medium underline-offset-4 hover:underline">
        <Icon aria-hidden="true" className="size-4 shrink-0 text-copper-foreground" />
        <span className="truncate">{t(SECTION_TITLE[section])}</span>
      </Link>
      <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted-foreground">{label}</span>
    </li>
  );
}
