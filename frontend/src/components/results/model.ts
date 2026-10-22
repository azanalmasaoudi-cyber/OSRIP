import type { StoredBalance } from '@/api/balance';
import { balanceExportUrl } from '@/api/balance';
import type { StudyColumn, StudyChart } from '@/api/studies';
import type { Dataset, StudyEvidence } from '@/api/studyEvents';
import type { AppLanguage } from '@/lib/format';
import type { LiveStudyState } from '@/state/liveStudy';

/**
 * One shape for the results area, built from either a stored shortage and surplus analysis
 * or a live assistant study. Nothing is calculated here: values, tables and charts are taken
 * from the validated server documents as they are; only the language is chosen.
 */

type Row = Record<string, string | null>;
export type Tone = 'verified' | 'sand' | 'muted' | 'outline' | 'accent';

export interface ResultTable {
  id: string;
  title: string;
  subtitle?: string | null;
  status?: { code: string; label: string; tone: Tone } | null;
  nature: 'observed' | 'calculated' | 'scenario';
  columns: StudyColumn[];
  rows: Row[];
  rowIds?: string[];
  charts: StudyChart[];
  sourceIds: string[];
  provisional?: boolean;
  details: { label: string; text: string }[];
}

export interface ResultSource {
  id: string;
  title: string;
  publisher?: string | null;
  url?: string | null;
  publication?: string | null;
  accessed?: string | null;
  published?: string | null;
  period?: string | null;
  value?: string | null;
  valueOperator?: string | null;
  unit?: string | null;
  dataset?: string | null;
  record?: string | null;
  dataStatus: string;
  kind: string;
  olderContext?: boolean;
  sourceClass?: string | null;
}

export interface ResultRecommendation {
  id: string;
  problem: string;
  evidence: string;
  evidenceIds: string[];
  action: string;
  quantity: string | null;
  quantityUnit: string | null;
  quantityNote: string | null;
  horizon: string | null;
  constraints: string | null;
  cost: string | null;
  outcome: string | null;
  priority: { code: string; label: string } | null;
  priorityBasis: string | null;
  kpi: string | null;
  nature: { code: string; label: string };
  /** The kind of response (efficiency, storage, exports where feasible ...), when classified. */
  option: { code: string; label: string } | null;
}

/** How a study ends: findings, the limits of its evidence, what to do now and later, and what
 * the next study needs. */
export interface ResultConclusion {
  findings: string[];
  limitations: string[];
  immediate: { id: string; action: string }[];
  mediumTerm: { id: string; action: string }[];
  nextStudy: { question: string; data: string; where: string | null }[];
}

export interface ResultCard {
  id: string;
  title: string;
  status: { code: string; label: string; tone: Tone };
  gap: string | null;
  gapUnit: string | null;
  period: string | null;
  reason: string;
}

export interface ResultsModel {
  kind: 'balance' | 'study';
  id: string;
  title: string;
  question: string | null;
  /** The language of generated sentences (a study answers in the language it was asked in). */
  textLanguage: AppLanguage;
  status: { code: string; label: string; tone: Tone };
  running: boolean;
  dataMode: string | null;
  summary: string[];
  cards: ResultCard[];
  dataGaps: { missing: string; blocks: string; where: string | null }[];
  scenario: { status: string; text: string | null; assumptions: string[]; table: ResultTable | null } | null;
  forecast: string | null;
  method: string[];
  assumptions: string[];
  limitations: string[];
  prioritization: string | null;
  tables: ResultTable[];
  sources: ResultSource[];
  recommendations: ResultRecommendation[];
  conclusion: ResultConclusion | null;
  downloads: { csv: string | null; report: string | null };
}

/** The labels the adapters need (kept out of here so this file stays free of React). */
export interface Labels {
  balanceStatus: Record<string, string>;
  analysisStatus: Record<string, string>;
  studyStatus: Record<string, string>;
  priority: Record<string, string>;
  horizon: Record<string, string>;
  nature: Record<string, string>;
  option: Record<string, string>;
  studyRecommendation: string;
  notQuantified: string;
}

const STATUS_TONE: Record<string, Tone> = {
  surplus: 'verified', shortfall: 'accent', balanced: 'outline', not_determinable: 'sand',
  ok: 'verified', partial: 'sand', not_available: 'sand',
  running: 'sand', connecting: 'muted', completed: 'verified', cancelled: 'muted', failed: 'accent', none: 'muted', idle: 'muted',
};

export function fromBalance(stored: StoredBalance, language: AppLanguage, labels: Labels): ResultsModel {
  const a = stored.analysis;
  const pick = (x: { en: string; ar: string } | null | undefined) => (x ? x[language] : '');
  const unitLabel = (u: { label_en: string; label_ar: string } | null | undefined) => (u ? (language === 'ar' ? u.label_ar : u.label_en) : null);
  const tables: ResultTable[] = a.balances.map((b) => ({
    id: b.id,
    title: pick(b.title),
    subtitle: b.period ? `${pick(b.status_label)} · ${b.period}` : pick(b.status_label),
    status: { code: b.status, label: labels.balanceStatus[b.status] ?? b.status, tone: STATUS_TONE[b.status] ?? 'outline' },
    nature: b.status === 'not_determinable' ? 'observed' : 'calculated',
    columns: b.table.columns,
    rows: b.table.rows,
    charts: b.charts,
    sourceIds: b.evidence,
    details: [
      { label: 'reason', text: pick(b.reason) },
      { label: 'interpretation', text: pick(b.interpretation) },
      ...b.constraints.map((c) => ({ label: 'constraints', text: pick(c) })),
      ...b.notes.map((n) => ({ label: 'notes', text: pick(n) })),
    ],
  }));
  const sc = a.scenario;
  const scenarioTable: ResultTable | null = sc.status === 'ok' && sc.table ? {
    id: 'SC', title: labels.nature.scenario ?? 'Scenario', subtitle: sc.assumptions.map(pick).join(' '),
    status: null, nature: 'scenario', columns: sc.table.columns, rows: sc.table.rows, charts: sc.charts, sourceIds: [],
    details: sc.assumptions.map((x) => ({ label: 'assumptions', text: pick(x) })),
  } : null;
  return {
    kind: 'balance',
    id: stored.id,
    title: pick(a.title),
    question: pick(a.question),
    textLanguage: language,
    status: { code: a.status, label: labels.analysisStatus[a.status] ?? a.status, tone: STATUS_TONE[a.status] ?? 'outline' },
    running: false,
    dataMode: a.data_mode,
    summary: a.summary.map(pick),
    cards: a.balances.map((b) => ({
      id: b.id, title: pick(b.title),
      status: { code: b.status, label: pick(b.status_label), tone: STATUS_TONE[b.status] ?? 'outline' },
      gap: b.gap ?? null, gapUnit: unitLabel(b.gap_unit), period: b.period ?? null, reason: pick(b.reason),
    })),
    dataGaps: a.data_gaps.map((g) => ({ missing: pick(g.missing), blocks: pick(g.blocks), where: g.where ? pick(g.where) : null })),
    scenario: { status: sc.status, text: sc.reason ? pick(sc.reason) : null, assumptions: sc.assumptions.map(pick), table: scenarioTable },
    forecast: pick(a.forecast.text),
    method: [pick(a.method)],
    assumptions: a.assumptions.map(pick),
    limitations: a.limitations.map(pick),
    prioritization: pick(a.prioritization),
    tables: scenarioTable ? [...tables, scenarioTable] : tables,
    sources: a.sources.map((s) => ({
      id: s.id, title: s.title, publisher: s.publisher, url: s.url, publication: s.publication, accessed: s.accessed,
      period: s.period_label, value: s.value, valueOperator: s.value_operator, unit: unitLabel(s.unit), dataset: s.dataset_version,
      record: s.record_ref, dataStatus: s.data_status, kind: 'observation', olderContext: s.older_context,
    })),
    recommendations: a.recommendations.map((r) => ({
      id: r.id, problem: pick(r.problem), evidence: pick(r.evidence), evidenceIds: r.evidence_ids, action: pick(r.action),
      quantity: r.quantity ?? null, quantityUnit: unitLabel(r.quantity_unit), quantityNote: pick(r.quantity_note),
      horizon: labels.horizon[r.horizon] ?? r.horizon, constraints: pick(r.constraints), cost: pick(r.cost), outcome: pick(r.outcome),
      priority: { code: r.priority, label: labels.priority[r.priority] ?? r.priority }, priorityBasis: pick(r.priority_basis),
      kpi: pick(r.kpi), nature: { code: r.nature, label: labels.nature[r.nature] ?? r.nature },
      option: r.option ? { code: r.option, label: labels.option[r.option] ?? r.option } : null,
    })),
    conclusion: a.conclusion ? {
      findings: a.conclusion.main_findings.map((f) => pick(f.text)),
      limitations: a.conclusion.evidence_limitations.map(pick),
      immediate: a.conclusion.immediate_actions.flatMap((id) => {
        const r = a.recommendations.find((x) => x.id === id);
        return r ? [{ id, action: pick(r.action) }] : [];
      }),
      mediumTerm: a.conclusion.medium_term_options.flatMap((id) => {
        const r = a.recommendations.find((x) => x.id === id);
        return r ? [{ id, action: pick(r.action) }] : [];
      }),
      nextStudy: a.conclusion.next_study.map((n) => ({ question: pick(n.question), data: pick(n.data), where: n.where ? pick(n.where) : null })),
    } : null,
    downloads: { csv: balanceExportUrl(stored.id, 'csv', language), report: balanceExportUrl(stored.id, 'html', language) },
  };
}

function datasetTable(d: Dataset, study: LiveStudyState, language: AppLanguage): ResultTable {
  const final = study.status === 'completed' && Boolean(study.completion?.final_datasets.includes(d.dataset_id));
  const nature = d.data_status === 'assumption_scenario' ? 'scenario' : d.data_status === 'calculated' ? 'calculated' : 'observed';
  const ids = [...d.evidence_ids, ...(d.source_evidence_id ? [d.source_evidence_id] : [])];
  return {
    id: d.dataset_id,
    title: d.title[language],
    subtitle: d.subtitle ? d.subtitle[language] : null,
    status: null,
    nature,
    columns: d.table.columns.filter((c) => !c.key.endsWith('_ar')),
    rows: d.table.rows,
    rowIds: d.rows_meta.map((m) => m.row_id),
    charts: d.charts,
    sourceIds: [...new Set(ids)],
    provisional: !final && study.status !== 'completed' ? true : d.provisional,
    details: d.study ? [
      ...(d.study.reason ? [{ label: 'reason', text: d.study.reason[language] }] : []),
      ...d.study.findings.map((f) => ({ label: 'interpretation', text: f[language] })),
      { label: 'method', text: d.study.method[language] },
    ] : [],
  };
}

function evidenceSource(e: StudyEvidence, language: AppLanguage): ResultSource {
  const period = e.period_start && e.period_end ? (e.period_start === e.period_end ? e.period_start : `${e.period_start} – ${e.period_end}`) : null;
  return {
    id: e.evidence_id,
    title: e.source?.title ?? e.title[language],
    publisher: e.source?.publisher ?? null,
    url: e.source?.url ?? null,
    published: e.published ?? null,
    accessed: e.retrieved_at ? e.retrieved_at.slice(0, 10) : null,
    period,
    value: e.value ?? null,
    valueOperator: e.value_operator ?? null,
    unit: e.unit ? e.unit[language] : null,
    dataset: e.source?.dataset_version ?? null,
    record: e.source?.record_ref ?? null,
    dataStatus: e.data_status,
    kind: e.kind,
    sourceClass: e.source_class ?? null,
  };
}

export function fromStudy(study: LiveStudyState, ref: { id: string; question: string }, language: AppLanguage, labels: Labels): ResultsModel {
  const completion = study.completion;
  const running = study.status === 'running' || study.status === 'connecting';
  const textLanguage: AppLanguage = completion?.language ?? study.language ?? language;
  const method = completion?.method ?? {};
  const assumptions = completion?.assumptions ?? [];
  return {
    kind: 'study',
    id: ref.id,
    title: ref.question,
    question: ref.question,
    textLanguage,
    status: { code: study.status, label: labels.studyStatus[study.status] ?? study.status, tone: STATUS_TONE[study.status] ?? 'outline' },
    running,
    dataMode: study.dataMode,
    summary: completion ? (completion.findings.length ? completion.findings.map((f) => f.text) : completion.narration.map((n) => n.text)) : [],
    cards: [],
    dataGaps: study.warnings.map((w) => ({ missing: w.detail[language], blocks: '', where: null })),
    scenario: null,
    forecast: null,
    method: typeof method.answer_provider === 'string' ? [String(method.answer_provider)] : [],
    assumptions,
    limitations: [],
    prioritization: null,
    tables: study.datasets.map((d) => datasetTable(d, study, language)),
    sources: study.evidence.map((e) => evidenceSource(e, language)),
    recommendations: (completion?.recommendations ?? []).map((r, i) => ({
      id: `A${i + 1}`, problem: r.finding, evidence: labels.studyRecommendation, evidenceIds: r.citations ?? [], action: r.action,
      quantity: null, quantityUnit: null, quantityNote: labels.notQuantified, horizon: null, constraints: null, cost: null,
      outcome: [r.expected_benefit, r.uncertainty].filter(Boolean).join(' — '), priority: null, priorityBasis: null, kpi: null, option: null,
      nature: { code: 'recommendation', label: labels.nature.recommendation ?? 'Recommendation' },
    })),
    conclusion: null,
    downloads: { csv: null, report: null },
  };
}

/** The first and last period labels of a table (for chart captions). */
export function periodRange(table: ResultTable): string | null {
  const key = table.columns.find((c) => c.kind === 'period')?.key;
  if (!key) return null;
  const values = table.rows.map((r) => r[key]).filter((v): v is string => Boolean(v));
  if (!values.length) return null;
  const first = values[0] ?? '';
  const last = values[values.length - 1] ?? '';
  return first === last ? first : `${first} – ${last}`;
}
