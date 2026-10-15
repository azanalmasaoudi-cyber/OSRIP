import { datasetSchema, type Dataset } from '@/api/studyEvents';
import type { DataMode, Series } from '@/domain/types';

/**
 * Datasets for the workspace's own views, built from data the API already served (a series,
 * a governorate comparison) and checked with the same schema as the assistant's live tables,
 * so a table and its chart always come from one validated object. Nothing is calculated
 * here: values are copied as the API's decimal strings, missing stays missing.
 */

export function periodLabel(kind: string | undefined, start: string, end: string): string {
  if (kind === 'annual' && start.slice(5) === '01-01') return start.slice(0, 4);
  if (kind === 'monthly') return start.slice(0, 7);
  if (kind === 'quarterly') return `${start.slice(0, 4)} Q${Math.floor((Number(start.slice(5, 7)) - 1) / 3) + 1}`;
  return `${start} – ${end}`;
}

const statusOf = (mode: DataMode) => (mode === 'verified_source' ? 'approved_official' : 'synthetic_demonstration');

/** One series over time, optionally limited to the chosen years (both chart and table). */
export function seriesDataset(series: Series, fromYear: string | null, toYear: string | null): Dataset | null {
  const observations = [...series.observations]
    .filter((o) => (!fromYear || o.periodEnd.slice(0, 4) >= fromYear) && (!toYear || o.periodStart.slice(0, 4) <= toYear))
    .sort((a, b) => a.periodStart.localeCompare(b.periodStart));
  if (!observations.length) return null;
  const unit = { code: series.unit.code, label_en: series.unit.label.en, label_ar: series.unit.label.ar };
  const rows = observations.map((o) => ({
    period: periodLabel(series.frequency, o.periodStart, o.periodEnd),
    value: o.value,
    status: o.value === null ? 'missing_in_source' : 'published',
  }));
  const candidate = {
    dataset_id: 'D1',
    origin: 'workspace',
    provisional: false,
    data_status: statusOf(series.dataMode),
    title: series.name,
    subtitle: series.area ? series.area.name : null,
    table: {
      columns: [
        { key: 'period', label: { en: 'Period', ar: 'الفترة' }, kind: 'period' },
        { key: 'value', label: series.name, kind: 'number', unit },
        { key: 'status', label: { en: 'Status', ar: 'الحالة' }, kind: 'status' },
      ],
      rows,
    },
    charts: rows.filter((r) => r.value !== null).length >= 2
      ? [{ type: 'line', title: series.name, x: 'period', series: [{ column: 'value', label: series.name, nature: 'observed' }], unit }]
      : [],
    rows_meta: rows.map((_, i) => ({ row_id: `r${i + 1}`, evidence_id: null })),
    evidence_ids: [],
  };
  const parsed = datasetSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

interface ComparisonRow { area: string; name: { en: string; ar: string }; value: string | null; status: string }
export type ComparisonInput = Comparison;
interface Comparison {
  status: string;
  indicator_name?: { en: string; ar: string } | null;
  unit?: { code: string; label_en: string; label_ar: string } | null;
  period_start?: string | null;
  period_end?: string | null;
  period_kind?: string | null;
  rows?: ComparisonRow[] | null;
}

/** Governorates side by side, only when the server found them comparable and at least two
 * have their own published value (otherwise there is no valid coverage to show). */
export function comparisonDataset(data: Comparison | undefined, mode: DataMode): Dataset | null {
  if (!data || data.status !== 'ok' || !data.rows || !data.unit) return null;
  const published = data.rows.filter((r) => r.value !== null && r.status === 'published');
  if (published.length < 2) return null;
  const name = data.indicator_name ?? { en: '', ar: '' };
  const period = data.period_start && data.period_end ? periodLabel(data.period_kind ?? undefined, data.period_start, data.period_end) : '';
  const rows = data.rows.map((r) => ({ area: r.name.en, area_ar: r.name.ar, value: r.value, status: r.status }));
  const parsed = datasetSchema.safeParse({
    dataset_id: 'D1',
    origin: 'workspace',
    provisional: false,
    data_status: statusOf(mode),
    title: name,
    subtitle: { en: `Governorates, ${period}`, ar: `المحافظات، ${period}` },
    table: {
      columns: [
        { key: 'area', label: { en: 'Governorate', ar: 'المحافظة' }, kind: 'text' },
        { key: 'area_ar', label: { en: 'Governorate (Arabic)', ar: 'المحافظة' }, kind: 'text' },
        { key: 'value', label: name, kind: 'number', unit: data.unit },
        { key: 'status', label: { en: 'Status', ar: 'الحالة' }, kind: 'status' },
      ],
      rows,
    },
    charts: [{ type: 'bar', title: name, x: 'area', series: [{ column: 'value', label: name, nature: 'observed' }], unit: data.unit }],
    rows_meta: rows.map((_, i) => ({ row_id: `r${i + 1}`, evidence_id: null })),
    evidence_ids: [],
  });
  return parsed.success ? parsed.data : null;
}

/**
 * Whether a series may be out of date: its latest period ended longer ago than the usual
 * publication interval for its frequency (annual 24 months, quarterly 9, monthly or
 * year-to-date 6). A dated statement has no schedule, so it is never called stale.
 */
const STALE_MONTHS: Partial<Record<string, number>> = { annual: 24, quarterly: 9, monthly: 6, year_to_date: 6 };

export function isStale(series: Series, now: Date = new Date()): boolean {
  const months = STALE_MONTHS[series.frequency ?? 'annual'];
  const withValue = series.observations.filter((o) => o.value !== null);
  const latest = withValue.reduce<string | null>((m, o) => (m === null || o.periodEnd > m ? o.periodEnd : m), null);
  if (months === undefined || latest === null) return false;
  const end = new Date(`${latest}T00:00:00Z`);
  const limit = new Date(end);
  limit.setUTCMonth(limit.getUTCMonth() + months);
  return now > limit;
}
