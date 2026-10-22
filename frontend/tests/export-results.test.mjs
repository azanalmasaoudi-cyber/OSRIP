import assert from 'node:assert/strict';
import { test } from 'node:test';
import { escapeHtml, modelToHtml, safeCell, tableToCsv } from '../src/lib/exportResults.ts';

const table = {
  id: 'D1', title: 'T', nature: 'observed', charts: [], sourceIds: [], details: [],
  columns: [
    { key: 'period', label: { en: 'Period', ar: 'الفترة' }, kind: 'period' },
    { key: 'value', label: { en: 'Balance', ar: 'الميزان' }, kind: 'number', unit: { code: 'million_OMR', label_en: 'million OMR', label_ar: 'مليون ريال عماني' } },
    { key: 'note', label: { en: 'Note', ar: 'ملاحظة' }, kind: 'text' },
  ],
  rows: [
    { period: '2025', value: '-219', note: '=HYPERLINK("http://x")' },
    { period: '2024', value: null, note: '+cmd' },
    { period: '2023', value: '6103.5', note: '@SUM(A1), "quoted"' },
  ],
};

test('Text cells that a spreadsheet would run are neutralised; numbers stay numbers', () => {
  assert.equal(safeCell('=1+1'), "'=1+1");
  assert.equal(safeCell('-2+3'), "'-2+3");
  assert.equal(safeCell('-219'), '-219');
  assert.equal(safeCell('\tx'), "'\tx");
  assert.equal(safeCell(null), '');
  const csv = tableToCsv(table, 'en', ['Title']);
  assert.ok(csv.startsWith('﻿'), 'byte-order mark for spreadsheet programs');
  const lines = csv.slice(1).trim().split('\n');
  assert.equal(lines[1], 'Period,Balance (million OMR),Note');
  assert.equal(lines[2], '2025,-219,"\'=HYPERLINK(""http://x"")"');
  assert.equal(lines[3], "2024,,'+cmd", 'a missing value is an empty cell, never zero');
  assert.equal(lines[4], '2023,6103.5,"\'@SUM(A1), ""quoted"""');
  assert.ok(!lines.some((l) => /^[=+@]/.test(l) || /,[=+@]/.test(l)));
  assert.ok(tableToCsv(table, 'ar').includes('الميزان (مليون ريال عماني)'));
});

test('The report escapes every value and contains no script', () => {
  assert.equal(escapeHtml('<script>"x"&\'y\''), '&lt;script&gt;&quot;x&quot;&amp;&#39;y&#39;');
  const model = {
    kind: 'study', id: 'abc', title: '<script>alert(1)</script>', question: null, textLanguage: 'ar',
    status: { code: 'completed', label: 'Done', tone: 'verified' }, running: false, dataMode: 'synthetic',
    summary: ['<img src=x onerror=alert(1)>'], cards: [], dataGaps: [], scenario: null, forecast: null, method: [],
    assumptions: [], limitations: [], prioritization: null, tables: [table],
    sources: [{ id: 'E1', title: 'Bad link', url: 'javascript:alert(1)', dataStatus: 'web', kind: 'web' }],
    recommendations: [], downloads: { csv: null, report: null },
  };
  const labels = {
    summary: 'S', tables: 'T', sources: 'So', recommendations: 'R', dataGaps: 'G', decisionSupport: 'D', charts: 'C',
    columns: { problem: 'p', evidence: 'e', action: 'a', quantity: 'q', horizon: 'h', constraints: 'c', cost: 'co', outcome: 'o', priority: 'pr', kpi: 'k' },
  };
  const html = modelToHtml(model, 'ar', labels);
  assert.ok(html.startsWith('<!doctype html><html lang="ar" dir="rtl">'));
  assert.ok(!html.includes('<script') && !html.includes('<img'));
  assert.ok(!html.includes('href="javascript'), 'only http(s) links become links');
  assert.ok(html.includes('&#39;=HYPERLINK') || html.includes('=HYPERLINK(&quot;'));
});

test('The report ends with the conclusion, escaped, and recommendation columns in the agreed order', () => {
  const model = {
    kind: 'balance', id: 'abc', title: 'Water', question: null, textLanguage: 'en',
    status: { code: 'ok', label: 'Done', tone: 'verified' }, running: false, dataMode: 'synthetic',
    summary: [], cards: [], dataGaps: [], scenario: null, forecast: null, method: [], assumptions: [], limitations: [],
    prioritization: null, tables: [], sources: [],
    recommendations: [{ id: 'R1', problem: 'Issue', evidence: 'Ev', evidenceIds: [], action: 'Act', quantity: null, quantityUnit: null,
      quantityNote: 'n', horizon: 'Short', constraints: 'Feasible?', cost: 'Unknown', outcome: 'Effect', priority: null, priorityBasis: null,
      kpi: 'KPI', nature: { code: 'recommendation', label: 'R' }, option: { code: 'storage', label: 'Storage' } }],
    conclusion: { findings: ['<b>gap</b>'], limitations: ['Missing peak'], immediate: [{ id: 'R1', action: 'Act' }], mediumTerm: [],
      nextStudy: [{ question: 'Q?', data: 'Data', where: null }] },
    downloads: { csv: null, report: null },
  };
  const labels = {
    summary: 'S', tables: 'T', sources: 'So', recommendations: 'R', dataGaps: 'G', decisionSupport: 'D', charts: 'C',
    conclusion: { title: 'Conclusion', findings: 'Findings', limits: 'Limits', immediate: 'Now', mediumTerm: 'Later', next: 'Next', none: 'None' },
    columns: { problem: 'Issue', evidence: 'Evidence', action: 'Action', quantity: 'Qty', horizon: 'Horizon', constraints: 'Feasibility',
      cost: 'Cost', outcome: 'Effect', priority: 'Priority', kpi: 'KPI' },
  };
  const html = modelToHtml(model, 'en', labels);
  const order = ['Issue', 'Evidence', 'Action', 'Qty', 'Feasibility', 'Horizon', 'Cost', 'Effect', 'Priority', 'KPI']
    .map((h) => html.indexOf(`<th scope="col">${h}</th>`));
  assert.deepEqual([...order].sort((a, b) => a - b), order, 'columns in the agreed order');
  assert.ok(order.every((i) => i > 0));
  assert.ok(html.indexOf('<h2>Conclusion</h2>') > html.indexOf('<h2>R</h2>'), 'the conclusion follows the recommendations');
  assert.ok(html.includes('&lt;b&gt;gap&lt;/b&gt;') && !html.includes('<b>gap'));
  assert.ok(html.includes('<h3>Later</h3><p class="muted">None</p>'), 'an empty part says so');
});
