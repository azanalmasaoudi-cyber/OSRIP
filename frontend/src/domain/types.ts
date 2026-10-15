/**
 * Domain types shared by the API adapters and the UI.
 * Codes mirror backend/app/domain/enums.py. Numeric values travel as decimal
 * strings so the API's exact values are never altered by float parsing; they
 * are converted only for display formatting.
 */

export const DATA_MODES = ['verified_source', 'synthetic'] as const;
export type DataMode = (typeof DATA_MODES)[number];

export const SECTIONS = ['electricity', 'water', 'food_security', 'trade'] as const;
export type SectionCode = (typeof SECTIONS)[number];

export type DomainCode = 'energy_essential_services' | 'food_security' | 'trade';

export type TradeFlow = 'import' | 'domestic_export' | 're_export';
export type QualityStatus = 'accepted' | 'warning' | 'withheld';
export type ValueType =
  | 'period_total'
  | 'average'
  | 'maximum'
  | 'end_of_period'
  | 'cumulative_to_date';
export type CommodityMappingStatus = 'provisional' | 'reviewed' | 'withdrawn';

export interface BilingualText {
  en: string;
  ar: string;
}

export interface UnitRef {
  code: string;
  label: BilingualText;
}

export interface SourceRef {
  title: string;
  /** Always null for synthetic data: no official publisher is ever assigned. */
  publisher: string | null;
  url: string | null;
  versionLabel: string;
  accessDate: string | null;
  /** Provenance fields supplied by the API (absent in the mock adapter). */
  referencePeriod?: string | null;
  geographicCoverage?: string | null;
  reuseConditions?: string | null;
  publishedAt?: string | null;
  /** Reference-pack code (S01…S08) and role of the reference, when loaded from the pack. */
  sourceCode?: string | null;
  sourceRole?: string | null;
}

/**
 * How a value's period is read. `year_to_date` is a partial year (January to
 * the stated month) and is never compared with a full year; `statement` is a
 * dated official statement, never plotted as a trend.
 */
export const PERIOD_KINDS = ['annual', 'year_to_date', 'quarterly', 'monthly', 'statement'] as const;
export type Frequency = (typeof PERIOD_KINDS)[number];

export const REVISION_STATUSES = [
  'reported',
  'provisional',
  'preliminary',
  'estimate',
  'official_statement',
  'reported_statement',
  'revised',
] as const;
export type RevisionStatus = (typeof REVISION_STATUSES)[number];

export type ValueOperator = '>' | '>=' | '<' | '<=' | '~';

export interface ObservationRecord {
  periodStart: string; // ISO date
  periodEnd: string; // ISO date
  periodComplete: boolean;
  /** null means missing in the source. It is never rendered or exported as 0. */
  value: string | null;
  qualityStatus: QualityStatus;
  sourceRow: string;
  /** Provenance from the reference pack (absent for other imports and the mock adapter). */
  recordRef?: string | null;
  revisionStatus?: RevisionStatus | null;
  /** "More than 95 %" is stored as operator ">" and value 95, never as 95 alone. */
  valueOperator?: ValueOperator | null;
  sourceLocator?: string | null;
  statementDate?: string | null;
  note?: string | null;
  /** The published value and unit when the API converted it to the indicator's display unit. */
  originalValue?: string | null;
  originalUnit?: string | null;
  conversionFactor?: string | null;
}

export interface Series {
  indicatorCode: string;
  section: SectionCode;
  name: BilingualText;
  definition: BilingualText;
  unit: UnitRef;
  valueType: ValueType;
  frequency?: Frequency;
  /** Last month covered by a year-to-date series (1-12). */
  ytdEndMonth?: number | null;
  /** Parent indicator: a component that must not be added to its parent. */
  parentCode?: string | null;
  /** Geography of the series (the API always supplies it). A `reporting_group` is a
   * source's combined figure for several governorates and is never split among them. */
  area?: { code: string; name: BilingualText; level?: string };
  /** What the indicator must not be read as (from the indicator registry). */
  limitation?: BilingualText | null;
  commodityCode: string | null;
  flow: TradeFlow | null;
  partnerCode: string | null;
  /** Registry name of a real partner country (fictional fixture partners have none). */
  partnerName?: BilingualText | null;
  dataMode: DataMode;
  source: SourceRef;
  note: BilingualText | null;
  observations: readonly ObservationRecord[];
}

export type SeriesResponse =
  | { status: 'ok'; dataMode: DataMode; series: readonly Series[] }
  | { status: 'no_published_data'; dataMode: DataMode; reason: 'no_verified_source_data' };

export interface Commodity {
  code: string;
  name: BilingualText;
  mappingStatus: CommodityMappingStatus;
  /** True only for invented fixture commodities that exist in synthetic mode. */
  syntheticOnly: boolean;
}
