import type { ResultsModel, ResultTable } from '@/components/results/model';

/**
 * Downloads made in the browser for a live assistant study (a stored analysis is exported by
 * the server). The same rules as the server's exports: text cells that a spreadsheet would
 * run as a formula (= + - @ tab, carriage return) are prefixed with an apostrophe; numbers
 * stay numbers, negative ones included; missing values are empty cells, never zero. The
 * report escapes every value and contains no script.
 */

const NUMBER = /^-?\d+(\.\d+)?$/;
const FORMULA_START = new Set(['=', '+', '-', '@', '\t', '\r']);

export function safeCell(value: string | null | undefined): string {
  if (value == null) return '';
  if (NUMBER.test(value)) return value;
  return FORMULA_START.has(value.charAt(0)) ? `'${value}` : value;
}

function csvField(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function tableToCsv(table: ResultTable, language: 'en' | 'ar', meta: string[] = []): string {
  const lines: string[] = meta.map((m) => csvField(safeCell(`# ${m}`)));
  lines.push(table.columns.map((c) => {
    const unit = c.unit ? ` (${language === 'ar' ? c.unit.label_ar : c.unit.label_en})` : '';
    return csvField(safeCell(`${c.label[language]}${unit}`));
  }).join(','));
  for (const row of table.rows) {
    lines.push(table.columns.map((c) => {
      const v = row[c.key] ?? null;
      return csvField(c.kind === 'number' ? (v ?? '') : safeCell(v));
    }).join(','));
  }
  // A byte-order mark first, so spreadsheet programs read Arabic text as UTF-8.
  return `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`;
}

export function download(name: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function escapeHtml(value: string | null | undefined): string {
  return (value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function tableHtml(table: ResultTable, language: 'en' | 'ar'): string {
  const head = table.columns.map((c) => `<th scope="col">${escapeHtml(c.label[language])}${c.unit ? ` (${escapeHtml(language === 'ar' ? c.unit.label_ar : c.unit.label_en)})` : ''}</th>`).join('');
  const body = table.rows.map((r) => `<tr>${table.columns.map((c) => {
    const v = r[c.key] ?? null;
    return c.kind === 'number' ? `<td class="num">${v === null ? '—' : escapeHtml(v)}</td>` : `<td><bdi>${escapeHtml(v)}</bdi></td>`;
  }).join('')}</tr>`).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

export interface ReportLabels {
  summary: string;
  tables: string;
  sources: string;
  recommendations: string;
  dataGaps: string;
  decisionSupport: string;
  charts: string;
  columns: { problem: string; evidence: string; action: string; quantity: string; horizon: string; constraints: string; cost: string; outcome: string; priority: string; kpi: string };
}

const CSS = 'body{font-family:"IBM Plex Sans","IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif;color:#14211f;background:#fff;max-width:72rem;margin:2rem auto;padding:0 1rem;line-height:1.5}'
  + 'h1{font-size:1.5rem}h2{font-size:1.15rem;border-bottom:2px solid #163d36;margin-top:2rem}table{border-collapse:collapse;width:100%;font-size:.85rem;margin:.5rem 0}'
  + 'th,td{border:1px solid #c9d3d0;padding:.3rem .45rem;text-align:start;vertical-align:top}th{background:#eef3f1}td.num{text-align:end;direction:ltr}'
  + '.muted{color:#4a5a57}@media print{body{margin:0}}';

export function modelToHtml(model: ResultsModel, language: 'en' | 'ar', labels: ReportLabels): string {
  const dir = language === 'ar' ? 'rtl' : 'ltr';
  const parts = [
    `<!doctype html><html lang="${language}" dir="${dir}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`,
    `<title>${escapeHtml(model.title)}</title><style>${CSS}</style></head><body><h1>${escapeHtml(model.title)}</h1>`,
    `<h2>${escapeHtml(labels.summary)}</h2><ul>${model.summary.map((s) => `<li>${escapeHtml(s)}</li>`).join('')}</ul>`,
    `<h2>${escapeHtml(labels.tables)}</h2><p class="muted">${escapeHtml(labels.charts)}</p>`,
    ...model.tables.map((t) => `<h3>${escapeHtml(t.id)} · ${escapeHtml(t.title)}</h3>${t.subtitle ? `<p class="muted">${escapeHtml(t.subtitle)}</p>` : ''}${tableHtml(t, language)}`),
  ];
  if (model.recommendations.length) {
    const c = labels.columns;
    const head = [c.problem, c.evidence, c.action, c.quantity, c.horizon, c.constraints, c.cost, c.outcome, c.priority, c.kpi]
      .map((h) => `<th scope="col">${escapeHtml(h)}</th>`).join('');
    const rows = model.recommendations.map((r) => `<tr>${[
      r.problem, `${r.evidence}${r.evidenceIds.length ? ` [${r.evidenceIds.join(', ')}]` : ''}`, r.action,
      r.quantity ? `${r.quantity} ${r.quantityUnit ?? ''}` : (r.quantityNote ?? '—'), r.horizon ?? '—', r.constraints ?? '—', r.cost ?? '—',
      r.outcome ?? '—', r.priority?.label ?? '—', r.kpi ?? '—',
    ].map((x) => `<td>${escapeHtml(x)}</td>`).join('')}</tr>`).join('');
    parts.push(`<h2>${escapeHtml(labels.recommendations)}</h2><p class="muted">${escapeHtml(labels.decisionSupport)}</p><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`);
  }
  if (model.dataGaps.length) {
    parts.push(`<h2>${escapeHtml(labels.dataGaps)}</h2><ul>${model.dataGaps.map((g) => `<li>${escapeHtml(g.missing)}${g.blocks ? ` — ${escapeHtml(g.blocks)}` : ''}</li>`).join('')}</ul>`);
  }
  parts.push(`<h2>${escapeHtml(labels.sources)}</h2><ol>${model.sources.map((s) => {
    const link = s.url && /^https?:\/\//.test(s.url) ? `<a href="${escapeHtml(s.url)}" rel="noreferrer noopener">${escapeHtml(s.title)}</a>` : escapeHtml(s.title);
    return `<li><bdi>${escapeHtml(s.id)}</bdi> · ${escapeHtml(s.publisher ?? '')} · ${link}${s.period ? ` · <bdi>${escapeHtml(s.period)}</bdi>` : ''}${s.dataset ? ` · <bdi>${escapeHtml(s.dataset)}</bdi>` : ''}</li>`;
  }).join('')}</ol></body></html>`);
  return parts.join('');
}
