import { ArrowRight, CircleCheck, CircleDashed } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { DevelopmentConditions, ForecastOverview } from '@/api/forecasting';
import { Badge } from '@/components/ui/badge';
import type { SectionCode } from '@/domain/types';
import { formatPeriod, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

export const DOMAINS = ['electricity', 'water', 'food_security', 'trade'] as const satisfies readonly SectionCode[];
export type Domain = (typeof DOMAINS)[number];

export const DOMAIN_KEY = {
  electricity: 'nav.electricity',
  water: 'nav.water',
  food_security: 'nav.foodSecurity',
  trade: 'nav.trade',
} as const satisfies Record<Domain, string>;

const DOMAIN_PATH: Record<Domain, string> = {
  electricity: '/energy/electricity',
  water: '/energy/water',
  food_security: '/food-security',
  trade: '/trade',
};

/** The domain of an indicator code, from its prefix (ELEC_, WATER_, AGRI_/FISH_/FOOD_/SELF_, TRADE_). */
export function domainOf(indicator: string): Domain {
  if (indicator.startsWith('ELEC_')) return 'electricity';
  if (indicator.startsWith('WATER_')) return 'water';
  if (indicator.startsWith('TRADE_')) return 'trade';
  return 'food_security';
}

function pick(text: { en: string; ar: string } | null | undefined, language: AppLanguage): string {
  return text ? (language === 'ar' ? text.ar : text.en) : '';
}

/** A. Historical observations: what published history each target has, with a link to it. */
export function HistoryPanel({ data, domains }: { data: ForecastOverview; domains: readonly Domain[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  return (
    <div className="flex flex-col gap-4" data-testid="history-panel">
      {domains.map((domain) => {
        const series = data.targets.filter((x) => x.group === domain).flatMap((x) => x.series);
        return (
          <div key={domain} className="rounded-lg border border-border bg-card p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">{t(DOMAIN_KEY[domain])}</h3>
              <Link to={to(DOMAIN_PATH[domain])} className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline">
                {t('forecasts.openObservations')}<ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
              </Link>
            </div>
            {series.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('forecasts.noHistory')}</p>
            ) : (
              <ul className="flex flex-col gap-1 text-sm">
                {series.map((s) => (
                  <li key={s.series_id} className="flex flex-wrap justify-between gap-x-4">
                    <span>{language === 'ar' ? s.indicator.name_ar : s.indicator.name_en} · {language === 'ar' ? s.area.name_ar : s.area.name_en}</span>
                    <span className="text-muted-foreground">
                      {s.first_period && s.last_period ? `${formatPeriod(s.first_period, s.first_period, language)} – ${formatPeriod(s.last_period, s.last_period, language)} · ` : ''}
                      {t('forecasts.observationsCount', { n: s.usable_observations })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      <p className="text-xs text-muted-foreground">{t('forecasts.historyNote')}</p>
    </div>
  );
}

/** Candidate development conditions: measured only with a published compatible series. */
export function ConditionsPanel({ data, domains }: { data: DevelopmentConditions; domains: readonly Domain[] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <div className="flex flex-col gap-4" data-testid="conditions-panel">
      <p className="max-w-3xl text-sm text-muted-foreground">{pick(data.explanation, language)}</p>
      {domains.map((domain) => (
        <div key={domain} className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 font-semibold">{t(DOMAIN_KEY[domain])}</h3>
          <ul className="grid gap-3 md:grid-cols-2">
            {(data.domains[domain] ?? []).map((c) => (
              <li key={c.code} className="flex flex-col gap-1 rounded-md border border-border p-3 text-sm" data-testid="condition"
                data-code={c.code} data-status={c.status}>
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {c.status === 'measured'
                    ? <CircleCheck aria-hidden="true" className="size-4 text-primary" />
                    : <CircleDashed aria-hidden="true" className="size-4 text-muted-foreground" />}
                  {pick(c.name, language)}
                  <Badge variant={c.status === 'measured' ? 'verified' : 'muted'}>
                    {c.status === 'measured' ? t('forecasts.measured') : t('forecasts.assumption')}
                  </Badge>
                </p>
                {c.measured_by.length ? (
                  <p className="text-xs text-muted-foreground">
                    {t('forecasts.measuredBy')}: {c.measured_by.map((m) => `${m.indicator} (${t('forecasts.observationsCount', { n: m.observations })})`).join(', ')}
                  </p>
                ) : null}
                <p className="text-xs"><span className="font-medium">{t('forecasts.evidenceNeeded')}:</span> {pick(c.evidence_needed, language)}</p>
                {c.note ? <p className="text-xs text-muted-foreground">{pick(c.note, language)}</p> : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export interface Explanation {
  change: string;
  factors: string;
  uncertainty: string;
  evidence: string[];
  followUp: string;
}

/** What may change, contributing factors, uncertainty, evidence needed and a follow-up. */
export function ExplanationBlock({ explanation, testId }: { explanation: Explanation; testId: string }) {
  const { t } = useTranslation();
  return (
    <dl className="grid gap-x-4 gap-y-2 rounded-md border border-sand/50 bg-sand-subtle/40 p-4 text-sm sm:grid-cols-[minmax(9rem,auto)_1fr]" data-testid={testId}>
      <dt className="font-medium">{t('explain.change')}</dt><dd>{explanation.change}</dd>
      <dt className="font-medium">{t('explain.factors')}</dt><dd>{explanation.factors}</dd>
      <dt className="font-medium">{t('explain.uncertainty')}</dt><dd>{explanation.uncertainty}</dd>
      <dt className="font-medium">{t('explain.evidence')}</dt>
      <dd>{explanation.evidence.length ? <ul className="list-disc ps-5">{explanation.evidence.map((e) => <li key={e}>{e}</li>)}</ul> : '—'}</dd>
      <dt className="font-medium">{t('explain.followUp')}</dt><dd>{explanation.followUp}</dd>
    </dl>
  );
}

/** Evidence still needed in a domain: the unmeasured conditions (at most four). */
export function evidenceNeeded(data: DevelopmentConditions | undefined, domain: Domain, language: AppLanguage): string[] {
  return (data?.domains[domain] ?? [])
    .filter((c) => c.status === 'scenario_assumption')
    .slice(0, 4)
    .map((c) => `${pick(c.name, language)}: ${pick(c.evidence_needed, language)}`);
}
