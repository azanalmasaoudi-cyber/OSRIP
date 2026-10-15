import { ChevronDown, CircleHelp, FileSearch, History, Search, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAnalysis, useReviewCards, type SectionFilters } from '@/api/analysis';
import type { DataMode, SectionCode, Series } from '@/domain/types';
import { FREQUENCY_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod } from '@/lib/format';

/** First and last period with a published value (missing values are not coverage). */
function coverage(s: Series): { from: string; to: string } | null {
  const valued = s.observations.filter((o) => o.value !== null);
  if (!valued.length) return null;
  const from = valued.reduce((m, o) => (o.periodStart < m ? o.periodStart : m), valued[0]!.periodStart);
  const to = valued.reduce((m, o) => (o.periodEnd > m ? o.periodEnd : m), valued[0]!.periodEnd);
  return { from, to };
}
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const CHANGE_KINDS = new Set(['percentage_change', 'absolute_change']);
const OPEN_STATUSES = new Set(['open', 'under_review']);

function Question({ icon, title, children, testid }: { icon: ReactNode; title: string; children: ReactNode; testid: string }) {
  return (
    <details className="group rounded-lg border border-border bg-card" data-testid={testid}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        {icon}
        <span className="flex-1">{title}</span>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground transition-transform duration-150 group-open:rotate-180" />
      </summary>
      <div className="expand-content border-t border-border px-4 py-3 text-sm">{children}</div>
    </details>
  );
}

/**
 * The questions every analytical page answers: what the indicator measures and over
 * which period, what changed, what evidence (source) supports it, its limits, and what to
 * investigate next. Built only from what the page already loaded: indicator definitions,
 * the section calculations, the sources and dataset versions, and the open review
 * cards. Nothing is generated.
 */
export function SectionInsights({ section, mode, filters, series }: {
  section: SectionCode; mode: DataMode; filters: SectionFilters; series: readonly Series[];
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const analysis = useAnalysis(section, mode, filters);
  const cards = useReviewCards(mode, section);

  const indicators = [...new Map(series.map((s) => [s.indicatorCode, s])).values()].slice(0, 6);
  const changes = (analysis.data?.calculations ?? []).filter((c) => CHANGE_KINDS.has(c.kind));
  const measured = changes.filter((c) => c.result.status === 'ok').slice(0, 4);
  const sources = [...new Map(series.map((s) => [`${s.source.title}|${s.source.versionLabel}`, s.source])).values()];
  const observations = series.reduce((n, s) => n + s.observations.filter((o) => o.value !== null).length, 0);
  const missing = series.reduce((n, s) => n + s.observations.filter((o) => o.value === null).length, 0);
  const followUps = (cards.data?.cards ?? []).filter((c) => OPEN_STATUSES.has(c.status)).slice(0, 3);
  const iconClass = 'size-4 shrink-0 text-primary';

  return (
    <section aria-labelledby={`insights-${section}`} className="flex flex-col gap-2" data-testid="section-insights">
      <h2 id={`insights-${section}`} className="sr-only">{t('insights.heading')}</h2>
      <div className="grid items-start gap-2 lg:grid-cols-2">
        <Question testid="insight-measure" icon={<CircleHelp aria-hidden="true" className={iconClass} />} title={t('insights.measure')}>
          {indicators.length === 0 ? <p className="text-muted-foreground">{t('insights.noSeries')}</p> : (
            <ul className="flex flex-col gap-2">
              {indicators.map((s) => (
                <li key={s.indicatorCode}>
                  <span className="font-medium">{s.name[language]}</span> <span className="text-muted-foreground">({s.unit.label[language]})</span>
                  <p className="text-muted-foreground">{s.definition[language]}</p>
                  {coverage(s) ? (
                    <p className="text-xs" data-testid="insight-period">
                      {t('insights.period')}: {formatPeriod(coverage(s)!.from, coverage(s)!.to, language)}
                      {s.frequency ? <> · {t(FREQUENCY_KEY[s.frequency])}</> : null}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Question>
        <Question testid="insight-change" icon={<History aria-hidden="true" className={iconClass} />} title={t('insights.change')}>
          {analysis.isPending ? <p className="text-muted-foreground">{t('states.loading')}</p> : measured.length === 0 ? (
            <p className="text-muted-foreground">{t('insights.noChange')}</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {measured.map((c) => (
                <li key={c.id}>
                  <span className="font-medium">{c.title[language]}</span>:{' '}
                  <span className="tabular-nums" dir="ltr">{formatDecimal(c.result.value, language, 2)}</span>{' '}
                  {c.result.unit ? (language === 'ar' ? c.result.unit.label_ar : c.result.unit.label_en) : ''}
                </li>
              ))}
              {changes.length > measured.length ? <li className="text-xs text-muted-foreground">{t('insights.notCalculated', { n: changes.length - measured.length })}</li> : null}
            </ul>
          )}
        </Question>
        <Question testid="insight-evidence" icon={<FileSearch aria-hidden="true" className={iconClass} />} title={t('insights.evidence')}>
          {sources.length === 0 ? <p className="text-muted-foreground">{t('insights.noSources')}</p> : (
            <div className="flex flex-col gap-2">
              <p>{t('insights.evidenceCounts', { observations, missing })}</p>
              <ul className="flex flex-col gap-1">
                {sources.map((src) => (
                  <li key={`${src.title}|${src.versionLabel}`} className="text-muted-foreground">
                    <span className="text-foreground">{src.title}</span> · <span dir="ltr">{src.versionLabel}</span>
                    {src.accessDate ? <> · {t('insights.accessed')} <span dir="ltr">{src.accessDate}</span></> : null}
                  </li>
                ))}
              </ul>
              <Link to={to('/sources')} className="w-fit text-primary underline underline-offset-4">{t('insights.openSources')}</Link>
            </div>
          )}
        </Question>
        <Question testid="insight-limits" icon={<TriangleAlert aria-hidden="true" className={iconClass} />} title={t('insights.limits')}>
          <ul className="flex flex-col gap-1.5">
            {indicators.filter((s) => s.limitation).map((s) => (
              <li key={s.indicatorCode}><span className="font-medium">{s.name[language]}</span>: {t('insights.notToRead')} {s.limitation![language]}</li>
            ))}
            {missing > 0 ? <li>{t('insights.limitMissing', { n: missing })}</li> : null}
            {series.some((s) => s.observations.some((o) => !o.periodComplete)) ? <li>{t('insights.limitPartial')}</li> : null}
            {mode === 'synthetic' ? <li>{t('insights.limitSynthetic')}</li> : null}
            <li className="text-muted-foreground">{t('insights.limitCausation')}</li>
          </ul>
        </Question>
        <Question testid="insight-next" icon={<Search aria-hidden="true" className={iconClass} />} title={t('insights.next')}>
          <ul className="flex flex-col gap-1.5">
            {followUps.map((c) => <li key={c.id}>{c.next_steps[language]}</li>)}
            {missing > 0 ? <li>{t('insights.nextMissing', { n: missing })}</li> : null}
            {followUps.length === 0 && missing === 0 ? <li className="text-muted-foreground">{t('insights.nextNone')}</li> : null}
            <li><Link to={to('/forecasts')} className="text-primary underline underline-offset-4">{t('insights.nextForecasts')}</Link></li>
          </ul>
        </Question>
      </div>
    </section>
  );
}
