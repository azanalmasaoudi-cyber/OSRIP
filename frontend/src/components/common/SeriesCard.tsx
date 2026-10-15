import { useTranslation } from 'react-i18next';

import { ColumnChart } from './Charts';
import { DataModeBadge } from './DataModeBadge';
import { SourceDetailsButton } from './SourceDetails';
import { WatchButton } from './WatchButton';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { DisplayOption } from '@/domain/filters';
import type { ObservationRecord, Series } from '@/domain/types';
import { DATA_MODE_KEY, FLOW_KEY, FREQUENCY_KEY, QUALITY_KEY, REVISION_STATUS_KEY } from '@/i18n/keys';
import { formatPeriod, type AppLanguage } from '@/lib/format';
import { monthName, sourceTitle, useProvenance } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useCodeLabels } from '@/lib/useLabels';

/** The period label, naming year-to-date coverage instead of calling it merely incomplete. */
function usePeriodLabel(series: Series) {
  const { t } = useTranslation();
  return (obs: ObservationRecord, language: AppLanguage): { period: string; qualifier: string | null } => {
    const period = formatPeriod(obs.periodStart, obs.periodEnd, language);
    if (obs.periodComplete) return { period, qualifier: null };
    if (series.frequency === 'year_to_date') {
      const month = Number(obs.periodEnd.slice(5, 7));
      return { period, qualifier: t('provenance.ytdThrough', { month: monthName(month, language) }) };
    }
    return { period, qualifier: t('table.incompletePeriod') };
  };
}

/**
 * One series: context, optional chart, and an accessible table with provenance.
 * Missing values render as an explicit label, never as 0 (T02). A stated bound keeps
 * its operator, and a converted value names the published figure it came from.
 */
export function SeriesCard({ series, display = 'chart' }: { series: Series; display?: DisplayOption }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useCodeLabels();
  const provenance = useProvenance();
  const periodLabel = usePeriodLabel(series);
  const unitLabel = series.unit.label[language];
  const isStatement = series.frequency === 'statement';
  // Statements are dated figures, never a trend; bounded values (">95") cannot be drawn as exact bars.
  const showChart =
    display === 'chart' && !isStatement && series.observations.length >= 2 && series.observations.every((o) => !o.valueOperator);
  // Latest period with a published value, for this series only (never taken from another series).
  const latestWithValue = [...series.observations].sort((a, b) => a.periodEnd.localeCompare(b.periodEnd)).reverse()
    .find((o) => o.value !== null) ?? null;
  const latestLabel = latestWithValue ? periodLabel(latestWithValue, language) : null;
  const hasRevision = series.observations.some((o) => o.revisionStatus);
  const hasReference = series.observations.some((o) => o.recordRef || o.sourceLocator);
  const conversion = series.observations.find((o) => o.conversionFactor);
  const isGroup = series.area?.level === 'reporting_group';

  return (
    <Card data-testid="series-card" data-indicator={series.indicatorCode} data-period-kind={series.frequency} className="flex flex-col">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle>{series.name[language]}</CardTitle>
          <DataModeBadge mode={series.dataMode} />
        </div>
        <CardDescription>{series.definition[language]}</CardDescription>
        {series.limitation ? (
          <p className="mt-1 rounded-md bg-sand-subtle/60 px-3 py-2 text-xs" data-testid="series-limitation">
            <span className="font-semibold text-sand-foreground">{t('table.limitation')}: </span>
            {series.limitation[language]}
          </p>
        ) : null}
        {series.area || series.frequency ? (
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
            {series.area ? (
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground">{t('table.geography')}</dt>
                <dd className="font-medium" data-testid="series-geography">
                  {series.area.name[language]}
                  {isGroup ? <span className="ms-1 text-muted-foreground">({t('provenance.reportingGroup')})</span> : null}
                </dd>
              </div>
            ) : null}
            {series.frequency ? (
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground">{t('table.frequency')}</dt>
                <dd className="font-medium" data-testid="series-period-kind">{t(FREQUENCY_KEY[series.frequency])}</dd>
              </div>
            ) : null}
            <div className="flex gap-1.5">
              <dt className="text-muted-foreground">{t('table.unit')}</dt>
              <dd className="font-medium">{unitLabel}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-muted-foreground">{t('table.latestAvailable')}</dt>
              <dd className="font-medium" data-testid="series-latest">
                {latestLabel
                  ? `${latestLabel.period}${latestLabel.qualifier ? ` (${latestLabel.qualifier})` : ''}`
                  : t('states.dataUnavailable')}
              </dd>
            </div>
          </dl>
        ) : null}
        {series.flow || series.commodityCode ? (
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
            {series.flow ? (
              <>
                <div className="flex gap-1.5">
                  <dt className="text-muted-foreground">{t('table.flow')}</dt>
                  <dd className="font-medium">{t(FLOW_KEY[series.flow])}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-muted-foreground">{t('table.partner')}</dt>
                  <dd className="font-medium">{series.partnerName?.[language] ?? labels.partner(series.partnerCode)}</dd>
                </div>
              </>
            ) : null}
            {series.commodityCode ? (
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground">{t('table.commodity')}</dt>
                <dd className="font-medium">{labels.commodity(series.commodityCode)}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        {series.frequency === 'year_to_date' || isStatement || isGroup || series.parentCode || conversion ? (
          <ul className="mt-2 flex flex-col gap-1 text-xs text-muted-foreground" data-testid="series-reading-notes">
            {series.frequency === 'year_to_date' ? <li>{t('provenance.ytdNote')}</li> : null}
            {isStatement ? <li>{t('provenance.statementNote')}</li> : null}
            {isGroup ? <li>{t('provenance.reportingGroupNote')}</li> : null}
            {series.parentCode ? <li>{t('provenance.componentNote')}</li> : null}
            {conversion ? (
              <li data-testid="series-conversion">
                {t('provenance.conversionNote', { unit: unitLabel, factor: conversion.conversionFactor ?? '' })}
              </li>
            ) : null}
          </ul>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        {showChart ? <ColumnChart series={series} /> : null}
        <div className="relative overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              {t('table.caption', { indicator: series.name[language], unit: unitLabel })} – {t(DATA_MODE_KEY[series.dataMode])}
            </caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="py-2 pe-4 text-start font-medium">{t('table.period')}</th>
                <th scope="col" className="py-2 pe-4 text-end font-medium">
                  {t('table.value')} ({unitLabel})
                </th>
                <th scope="col" className="py-2 pe-4 text-start font-medium">
                  {hasRevision ? t('provenance.revision') : t('table.quality')}
                </th>
                <th scope="col" className="py-2 text-start font-medium">
                  {hasReference ? t('provenance.reference') : t('table.sourceRow')}
                </th>
              </tr>
            </thead>
            <tbody>
              {series.observations.map((obs) => {
                const shown = provenance.value(obs, language);
                const label = periodLabel(obs, language);
                const original = provenance.convertedFrom(obs, language);
                return (
                  <tr key={`${obs.periodStart}_${obs.periodEnd}_${obs.recordRef ?? ''}`} className="border-b border-border last:border-0">
                    <td className="py-2.5 pe-4">
                      {label.period}
                      {label.qualifier ? <span className="ms-2 text-xs text-muted-foreground">({label.qualifier})</span> : null}
                    </td>
                    <td className="py-2.5 pe-4 text-end font-medium tabular-nums" data-testid="observation-value">
                      {shown ? (
                        <>
                          <span dir="ltr" aria-hidden={obs.valueOperator ? true : undefined}>{shown.text}</span>
                          {obs.valueOperator ? <span className="sr-only">{shown.spoken}</span> : null}
                        </>
                      ) : (
                        <span className="font-normal italic text-muted-foreground" data-missing="true">
                          {t('states.missingValue')}
                        </span>
                      )}
                      {original ? (
                        <span className="block text-xs font-normal text-muted-foreground" data-testid="observation-original">{original}</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 pe-4">
                      {obs.revisionStatus ? t(REVISION_STATUS_KEY[obs.revisionStatus]) : t(QUALITY_KEY[obs.qualityStatus])}
                      {obs.revisionStatus && obs.qualityStatus !== 'accepted' ? (
                        <span className="block text-xs text-muted-foreground">{t(QUALITY_KEY[obs.qualityStatus])}</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 font-mono text-xs break-all text-muted-foreground" dir="ltr">
                      {obs.recordRef ? (
                        <span data-testid="observation-record" className="break-normal">
                          <span className="whitespace-nowrap">{obs.recordRef}</span>
                          {obs.sourceLocator ? <span className="block whitespace-nowrap">{obs.sourceLocator}</span> : null}
                        </span>
                      ) : (
                        obs.sourceRow
                      )}
                      {obs.note ? <span className="block font-sans" dir="auto">{obs.note}</span> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-xs text-muted-foreground">
          <span>
            {t('table.source')}: <bdi>{sourceTitle(series)}</bdi> · <span dir="ltr">{series.source.versionLabel}</span>
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <WatchButton series={series} />
            <SourceDetailsButton series={series} />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
