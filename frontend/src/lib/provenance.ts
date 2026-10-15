import { useTranslation } from 'react-i18next';

import { formatDecimal, type AppLanguage } from './format';
import type { ObservationRecord, Series, ValueOperator } from '@/domain/types';

const UNIT_CODES = [
  'thousand_m3',
  'million_m3',
  'thousand_tonnes',
  'million_tonnes',
  'tonne',
  'thousand_OMR',
  'million_OMR',
  'OMR',
  'feddan',
  'thousand_connections',
  'thousand_head',
] as const;
type KnownUnit = (typeof UNIT_CODES)[number];

const OPERATOR_SYMBOL: Record<ValueOperator, string> = { '>': '>', '>=': '≥', '<': '<', '<=': '≤', '~': '≈' };

function isKnownUnit(code: string): code is KnownUnit {
  return (UNIT_CODES as readonly string[]).includes(code);
}

/** The dataset title, prefixed with its reference code unless the title already names it. */
export function sourceTitle(series: Series): string {
  const { title, sourceCode } = series.source;
  return sourceCode && !title.includes(sourceCode) ? `${sourceCode} · ${title}` : title;
}

/** Month name for a year-to-date end month (1-12). */
export function monthName(month: number, language: AppLanguage): string {
  const locale = language === 'ar' ? 'ar-OM-u-nu-latn' : 'en-GB';
  return new Intl.DateTimeFormat(locale, { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2001, month - 1, 1)));
}

/**
 * Display helpers for reference-pack provenance: a stated bound (">" 95) keeps its
 * operator, and a converted value names the published value and unit it came from.
 */
export function useProvenance() {
  const { t } = useTranslation();

  const unitLabel = (code: string | null | undefined): string => {
    if (!code) return '';
    return isKnownUnit(code) ? t(`unitCode.${code}`) : code;
  };

  /** "> 95" with an accessible reading ("more than 95"); null values stay null. */
  const value = (obs: ObservationRecord, language: AppLanguage, digits?: number) => {
    const formatted = formatDecimal(obs.value, language, digits);
    if (formatted === null) return null;
    if (!obs.valueOperator) return { text: formatted, spoken: formatted };
    return {
      text: `${OPERATOR_SYMBOL[obs.valueOperator]} ${formatted}`,
      spoken: `${t(`valueOperator.${obs.valueOperator}`)} ${formatted}`,
    };
  };

  const convertedFrom = (obs: ObservationRecord, language: AppLanguage): string | null => {
    if (!obs.originalValue || !obs.originalUnit) return null;
    return t('provenance.convertedFrom', {
      value: formatDecimal(obs.originalValue, language) ?? obs.originalValue,
      unit: unitLabel(obs.originalUnit),
    });
  };

  return { unitLabel, value, convertedFrom };
}
