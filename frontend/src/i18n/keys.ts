import type { AppLanguage } from '@/lib/format';
import type {
  CommodityMappingStatus,
  DataMode,
  Frequency,
  QualityStatus,
  RevisionStatus,
  TradeFlow,
  ValueType,
} from '@/domain/types';

/**
 * Explicit code -> translation-key maps. Using literal keys (rather than
 * building keys with template strings) keeps react-i18next's key typing exact.
 */
export const DATA_MODE_KEY = {
  verified_source: 'dataMode.verified_source',
  synthetic: 'dataMode.synthetic',
} as const satisfies Record<DataMode, string>;

export const FLOW_KEY = {
  import: 'flow.import',
  domestic_export: 'flow.domestic_export',
  re_export: 'flow.re_export',
} as const satisfies Record<TradeFlow, string>;

export const QUALITY_KEY = {
  accepted: 'quality.accepted',
  warning: 'quality.warning',
  withheld: 'quality.withheld',
} as const satisfies Record<QualityStatus, string>;

export const COMMODITY_STATUS_KEY = {
  provisional: 'commodityStatus.provisional',
  reviewed: 'commodityStatus.reviewed',
  withdrawn: 'commodityStatus.withdrawn',
} as const satisfies Record<CommodityMappingStatus, string>;

export const VALUE_TYPE_KEY = {
  period_total: 'valueType.period_total',
  average: 'valueType.average',
  maximum: 'valueType.maximum',
  end_of_period: 'valueType.end_of_period',
  cumulative_to_date: 'valueType.cumulative_to_date',
} as const satisfies Record<ValueType, string>;

export const FREQUENCY_KEY = {
  annual: 'frequency.annual',
  year_to_date: 'frequency.year_to_date',
  quarterly: 'frequency.quarterly',
  monthly: 'frequency.monthly',
  statement: 'frequency.statement',
} as const satisfies Record<Frequency, string>;

export const REVISION_STATUS_KEY = {
  reported: 'revisionStatus.reported',
  provisional: 'revisionStatus.provisional',
  preliminary: 'revisionStatus.preliminary',
  estimate: 'revisionStatus.estimate',
  official_statement: 'revisionStatus.official_statement',
  reported_statement: 'revisionStatus.reported_statement',
  revised: 'revisionStatus.revised',
} as const satisfies Record<RevisionStatus, string>;

export const VERSION_STATUS_KEY = {
  draft: 'versionStatus.draft',
  validated: 'versionStatus.validated',
  approved: 'versionStatus.approved',
  published: 'versionStatus.published',
  superseded: 'versionStatus.superseded',
  rejected: 'versionStatus.rejected',
} as const;

export const LANGUAGE_KEY = {
  en: 'language.en',
  ar: 'language.ar',
} as const satisfies Record<AppLanguage, string>;
