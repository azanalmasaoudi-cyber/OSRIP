/**
 * SYNTHETIC DEMONSTRATION DATA — booklet Table 4.1 and Sections 4.3–4.4.
 *
 * These declared inputs exist to exercise the interface. They are not Omani
 * statistics, the years are arbitrary placeholders, and "Partner A/B/C" are
 * fictional. This module is only reachable through the mock adapter in
 * synthetic mode; it is never used to fill gaps in verified-source data.
 */

import type { Commodity, ObservationRecord, SectionCode, Series, TradeFlow } from '@/domain/types';

const SOURCE = {
  title: 'OSRIP booklet worked-example fixtures (synthetic)',
  publisher: null,
  url: null,
  versionLabel: 'fixtures-v1',
  accessDate: null,
} as const;

const PLACEHOLDER_YEARS_NOTE = {
  en: 'Synthetic fixture. Years are arbitrary placeholders, not reference dates.',
  ar: 'بيانات تجريبية افتراضية. السنوات عناصر نائبة اعتباطية وليست تواريخ مرجعية.',
} as const;

const UNITS = {
  GWh: { code: 'GWh', label: { en: 'GWh', ar: 'جيجاواط ساعة' } },
  million_m3: { code: 'million_m3', label: { en: 'million m³', ar: 'مليون م³' } },
  tonne: { code: 'tonne', label: { en: 'tonnes', ar: 'طن' } },
  OMR: { code: 'OMR', label: { en: 'OMR (nominal)', ar: 'ريال عماني (اسمي)' } },
} as const;

const SYNTH_COMMODITY = 'SYNTH_COMMODITY';

function annual(year: number, value: string | null, row: string): ObservationRecord {
  return {
    periodStart: `${year}-01-01`,
    periodEnd: `${year}-12-31`,
    periodComplete: true,
    value,
    qualityStatus: 'accepted',
    sourceRow: row,
  };
}

function tradeSeries(
  code: 'TRADE_QUANTITY' | 'TRADE_VALUE',
  flow: TradeFlow,
  partnerCode: string | null,
  value: string,
  row: string,
): Series {
  const isValue = code === 'TRADE_VALUE';
  return {
    indicatorCode: code,
    section: 'trade',
    name: isValue
      ? { en: 'Trade value', ar: 'قيمة التجارة' }
      : { en: 'Trade quantity', ar: 'كمية التجارة' },
    definition: isValue
      ? {
          en: 'Nominal monetary value traded. Not a retail price or a profit.',
          ar: 'القيمة النقدية الاسمية المتداولة. ليست سعر تجزئة ولا ربحاً.',
        }
      : {
          en: 'Physical quantity traded for the commodity and flow.',
          ar: 'الكمية المادية المتداولة للسلعة والاتجاه التجاري.',
        },
    unit: isValue ? UNITS.OMR : UNITS.tonne,
    valueType: 'period_total',
    commodityCode: SYNTH_COMMODITY,
    flow,
    partnerCode,
    dataMode: 'synthetic',
    source: SOURCE,
    note: PLACEHOLDER_YEARS_NOTE,
    observations: [annual(2002, value, row)],
  };
}

const ELECTRICITY: readonly Series[] = [
  {
    indicatorCode: 'ELEC_GENERATION',
    section: 'electricity',
    name: { en: 'Electricity generation', ar: 'توليد الكهرباء' },
    definition: {
      en: 'Energy generated during the period. Not a measure of consumption.',
      ar: 'الطاقة المولدة خلال الفترة. ليست مقياساً للاستهلاك.',
    },
    unit: UNITS.GWh,
    valueType: 'period_total',
    commodityCode: null,
    flow: null,
    partnerCode: null,
    dataMode: 'synthetic',
    source: SOURCE,
    note: PLACEHOLDER_YEARS_NOTE,
    observations: [annual(2001, '48000', 'table-4.1:electricity:earlier'), annual(2002, '50100', 'table-4.1:electricity:later')],
  },
];

const WATER: readonly Series[] = [
  {
    indicatorCode: 'WATER_CONSUMPTION',
    section: 'water',
    name: { en: 'Water consumption', ar: 'استهلاك المياه' },
    definition: {
      en: 'Consumption as defined by the source. Not physical delivery and not an estimate of leakage.',
      ar: 'الاستهلاك وفق تعريف المصدر. ليس التوصيل الفعلي ولا تقديراً للتسرب.',
    },
    unit: UNITS.million_m3,
    valueType: 'period_total',
    commodityCode: null,
    flow: null,
    partnerCode: null,
    dataMode: 'synthetic',
    source: SOURCE,
    note: PLACEHOLDER_YEARS_NOTE,
    observations: [annual(2001, '330', 'table-4.1:water:earlier'), annual(2002, '343', 'table-4.1:water:later')],
  },
];

const TRADE: readonly Series[] = [
  tradeSeries('TRADE_QUANTITY', 'import', null, '80000', 'sec-4.3:imports:total'),
  tradeSeries('TRADE_QUANTITY', 'domestic_export', null, '20000', 'sec-4.3:exports:total'),
  tradeSeries('TRADE_QUANTITY', 'import', 'PARTNER_A', '48000', 'sec-4.3:imports:partner-a'),
  tradeSeries('TRADE_QUANTITY', 'import', 'PARTNER_B', '20000', 'sec-4.3:imports:partner-b'),
  tradeSeries('TRADE_QUANTITY', 'import', 'PARTNER_C', '12000', 'sec-4.3:imports:partner-c'),
  tradeSeries('TRADE_VALUE', 'import', null, '40000000', 'sec-4.4:imports:value'),
  tradeSeries('TRADE_VALUE', 'domestic_export', null, '12000000', 'sec-4.4:exports:value'),
];

const FOOD: readonly Series[] = [
  {
    indicatorCode: 'FOOD_PRODUCTION',
    section: 'food_security',
    name: { en: 'Commodity production', ar: 'إنتاج السلعة' },
    definition: {
      en: 'Domestic production of the mapped commodity in its registered product form.',
      ar: 'الإنتاج المحلي للسلعة المطابقة بشكلها المسجل.',
    },
    unit: UNITS.tonne,
    valueType: 'period_total',
    commodityCode: SYNTH_COMMODITY,
    flow: null,
    partnerCode: null,
    dataMode: 'synthetic',
    source: SOURCE,
    note: PLACEHOLDER_YEARS_NOTE,
    observations: [annual(2002, '100000', 'sec-4.3:production')],
  },
  // Food security reuses the SAME national trade observations (shared registry, no duplication).
  ...TRADE.filter((s) => s.indicatorCode === 'TRADE_QUANTITY' && s.partnerCode === null),
];

export const SYNTHETIC_SERIES: Readonly<Record<SectionCode, readonly Series[]>> = {
  electricity: ELECTRICITY,
  water: WATER,
  food_security: FOOD,
  trade: TRADE,
};

/** Shared commodity registry used by BOTH Food Security and Trade. */
export const COMMODITY_REGISTRY: readonly Commodity[] = [
  { code: 'WHEAT', name: { en: 'Wheat', ar: 'القمح' }, mappingStatus: 'provisional', syntheticOnly: false },
  { code: 'RICE', name: { en: 'Rice', ar: 'الأرز' }, mappingStatus: 'provisional', syntheticOnly: false },
  { code: 'TOMATOES', name: { en: 'Tomatoes', ar: 'الطماطم' }, mappingStatus: 'provisional', syntheticOnly: false },
  {
    code: SYNTH_COMMODITY,
    name: { en: 'Synthetic demonstration commodity', ar: 'سلعة تجريبية افتراضية' },
    mappingStatus: 'provisional',
    syntheticOnly: true,
  },
];
