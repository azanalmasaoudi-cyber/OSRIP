/**
 * PREVIEW-ONLY DATA. Used by the dashboard solely when the HTTP adapter is configured and the
 * OSRIP API does not answer, so the interface can still be reviewed. Every value is a
 * synthetic placeholder: not Omani statistics, years are arbitrary, no publisher is assigned.
 * Everything built from this module is marked synthetic and labelled "Preview data" in the UI.
 */

import type { ComparisonInput } from '@/components/workspace/datasets';
import type { BilingualText, SectionCode, Series, SeriesResponse, TradeFlow, UnitRef } from '@/domain/types';

const FIRST_YEAR = 2001;

const SOURCE = {
  title: 'OSRIP interface preview fixtures (synthetic, not Omani statistics)',
  publisher: null,
  url: null,
  versionLabel: 'preview-v1',
  accessDate: null,
} as const;

const NOTE: BilingualText = {
  en: 'Preview data shown because the OSRIP API is unavailable. Synthetic placeholder values; years are arbitrary.',
  ar: 'بيانات معاينة معروضة لأن واجهة OSRIP البرمجية غير متاحة. قيم افتراضية تجريبية والسنوات اعتباطية.',
};

const NATIONAL = { code: 'OM', name: { en: 'Oman (national)', ar: 'عُمان (وطني)' }, level: 'country' };

const UNITS = {
  GWh: { code: 'GWh', label: { en: 'GWh', ar: 'جيجاواط ساعة' } },
  million_m3: { code: 'million_m3', label: { en: 'million m³', ar: 'مليون م³' } },
  tonne: { code: 'tonne', label: { en: 'tonnes', ar: 'طن' } },
  OMR_million: { code: 'OMR_million', label: { en: 'OMR million (nominal)', ar: 'مليون ريال عماني (اسمي)' } },
} as const satisfies Record<string, UnitRef>;

function preview(input: {
  code: string;
  section: SectionCode;
  name: BilingualText;
  definition: BilingualText;
  unit: UnitRef;
  values: readonly string[];
  flow?: TradeFlow;
}): Series {
  return {
    indicatorCode: input.code,
    section: input.section,
    name: input.name,
    definition: input.definition,
    unit: input.unit,
    valueType: 'period_total',
    frequency: 'annual',
    area: NATIONAL,
    commodityCode: null,
    flow: input.flow ?? null,
    partnerCode: null,
    dataMode: 'synthetic',
    source: SOURCE,
    note: NOTE,
    observations: input.values.map((value, i) => ({
      periodStart: `${FIRST_YEAR + i}-01-01`,
      periodEnd: `${FIRST_YEAR + i}-12-31`,
      periodComplete: true,
      value,
      qualityStatus: 'accepted',
      sourceRow: `preview:${input.code}:${input.flow ?? 'total'}:${FIRST_YEAR + i}`,
    })),
  };
}

const PREVIEW_SERIES: Readonly<Record<SectionCode, readonly Series[]>> = {
  electricity: [
    preview({
      code: 'ELEC_GENERATION', section: 'electricity', unit: UNITS.GWh,
      name: { en: 'Electricity generation', ar: 'توليد الكهرباء' },
      definition: { en: 'Energy generated during the period. Not a measure of consumption.', ar: 'الطاقة المولدة خلال الفترة. ليست مقياساً للاستهلاك.' },
      values: ['30200', '32900', '34100', '36800', '38200', '39500', '41900', '43600'],
    }),
    preview({
      code: 'ELEC_CONSUMPTION', section: 'electricity', unit: UNITS.GWh,
      name: { en: 'Electricity consumption', ar: 'استهلاك الكهرباء' },
      definition: { en: 'Energy billed to consumers during the period.', ar: 'الطاقة المفوترة للمستهلكين خلال الفترة.' },
      values: ['26800', '28900', '30100', '32400', '33600', '35100', '36900', '38400'],
    }),
  ],
  water: [
    preview({
      code: 'WATER_PRODUCTION', section: 'water', unit: UNITS.million_m3,
      name: { en: 'Desalinated water production', ar: 'إنتاج المياه المحلاة' },
      definition: { en: 'Water produced by desalination plants during the period.', ar: 'المياه المنتجة من محطات التحلية خلال الفترة.' },
      values: ['360', '378', '392', '410', '426', '441', '455', '472'],
    }),
    preview({
      code: 'WATER_CONSUMPTION', section: 'water', unit: UNITS.million_m3,
      name: { en: 'Water consumption', ar: 'استهلاك المياه' },
      definition: { en: 'Consumption as defined by the source. Not an estimate of leakage.', ar: 'الاستهلاك وفق تعريف المصدر. ليس تقديراً للتسرب.' },
      values: ['300', '316', '329', '343', '357', '369', '382', '396'],
    }),
  ],
  food_security: [
    preview({
      code: 'FISH_LANDINGS', section: 'food_security', unit: UNITS.tonne,
      name: { en: 'Fish landings', ar: 'إنزال الأسماك' },
      definition: { en: 'Fish landed at national ports during the period.', ar: 'الأسماك المنزلة في الموانئ الوطنية خلال الفترة.' },
      values: ['280000', '348000', '437000', '580000', '550000', '794000', '862000', '835000'],
    }),
    preview({
      code: 'VEGETABLE_PRODUCTION', section: 'food_security', unit: UNITS.tonne,
      name: { en: 'Vegetable production', ar: 'إنتاج الخضروات' },
      definition: { en: 'Domestic vegetable production during the period.', ar: 'الإنتاج المحلي من الخضروات خلال الفترة.' },
      values: ['410000', '432000', '455000', '471000', '498000', '512000', '536000', '561000'],
    }),
  ],
  trade: [
    preview({
      code: 'TRADE_VALUE', section: 'trade', unit: UNITS.OMR_million, flow: 'import',
      name: { en: 'Trade value', ar: 'قيمة التجارة' },
      definition: { en: 'Nominal monetary value traded. Not a retail price or a profit.', ar: 'القيمة النقدية الاسمية المتداولة. ليست سعر تجزئة ولا ربحاً.' },
      values: ['9100', '9800', '10400', '11800', '10900', '12300', '13100', '13800'],
    }),
    preview({
      code: 'TRADE_VALUE', section: 'trade', unit: UNITS.OMR_million, flow: 'domestic_export',
      name: { en: 'Trade value', ar: 'قيمة التجارة' },
      definition: { en: 'Nominal monetary value traded. Not a retail price or a profit.', ar: 'القيمة النقدية الاسمية المتداولة. ليست سعر تجزئة ولا ربحاً.' },
      values: ['5200', '5900', '6400', '7700', '7100', '8300', '9000', '9600'],
    }),
  ],
};

export function previewSeries(section: SectionCode, frequency?: string): SeriesResponse {
  const series = PREVIEW_SERIES[section].filter((s) => !frequency || s.frequency === frequency);
  return { status: 'ok', dataMode: 'synthetic', series };
}

export const PREVIEW_GOVERNORATES = [
  { code: 'OM-MA', name_en: 'Muscat', name_ar: 'مسقط' },
  { code: 'OM-BS', name_en: 'North Al Batinah', name_ar: 'شمال الباطنة' },
  { code: 'OM-ZU', name_en: 'Dhofar', name_ar: 'ظفار' },
  { code: 'OM-BJ', name_en: 'South Al Batinah', name_ar: 'جنوب الباطنة' },
  { code: 'OM-DA', name_en: 'Ad Dakhiliyah', name_ar: 'الداخلية' },
  { code: 'OM-SS', name_en: 'North Ash Sharqiyah', name_ar: 'شمال الشرقية' },
  { code: 'OM-SJ', name_en: 'South Ash Sharqiyah', name_ar: 'جنوب الشرقية' },
  { code: 'OM-ZA', name_en: 'Ad Dhahirah', name_ar: 'الظاهرة' },
  { code: 'OM-BU', name_en: 'Al Buraimi', name_ar: 'البريمي' },
  { code: 'OM-WU', name_en: 'Al Wusta', name_ar: 'الوسطى' },
  { code: 'OM-MU', name_en: 'Musandam', name_ar: 'مسندم' },
] as const;

const GOVERNORATE_VALUES: Partial<Record<string, readonly string[]>> = {
  ELEC_CONSUMPTION: ['14200', '7100', '4300', '3900', '3100', '1700', '1500', '1200', '900', '300', '200'],
  WATER_CONSUMPTION: ['148', '72', '45', '40', '30', '18', '16', '12', '9', '3', '3'],
};

/** Governorates side by side for the two preview indicators that have a regional split. */
export function previewComparison(indicator: string | null): ComparisonInput {
  const values = indicator ? GOVERNORATE_VALUES[indicator] : undefined;
  const series = indicator ? Object.values(PREVIEW_SERIES).flat().find((s) => s.indicatorCode === indicator) : undefined;
  if (!values || !series) return { status: 'insufficient_coverage' };
  const lastYear = FIRST_YEAR + (series.observations.length - 1);
  return {
    status: 'ok',
    indicator_name: series.name,
    unit: { code: series.unit.code, label_en: series.unit.label.en, label_ar: series.unit.label.ar },
    period_start: `${lastYear}-01-01`,
    period_end: `${lastYear}-12-31`,
    period_kind: 'annual',
    rows: PREVIEW_GOVERNORATES.map((g, i) => ({
      area: g.code,
      name: { en: g.name_en, ar: g.name_ar },
      value: values[i] ?? null,
      status: values[i] ? 'published' : 'missing_in_source',
    })),
  };
}
