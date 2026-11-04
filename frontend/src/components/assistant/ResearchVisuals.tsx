import { Download, ImageIcon, ListChecks, Network, Table2 } from 'lucide-react';
import { useContext, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { apiBaseUrl } from '@/api/config';
import type { DiagramBlock, GeneratedImageBlock, ResearchChartBlock, ResearchTableBlock } from '@/api/assistant';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { csvField, download, safeCell } from '@/lib/exportResults';
import { formatCompact, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

import { CitationChip, SourcesShown } from './StructuredReply';

/**
 * What Deep internet research built from the figures it found: tables whose every row the server
 * checked against the sources it cites, charts drawn from those rows only, diagrams that carry no
 * figure the evidence does not hold, the research plan, and illustrations, which are labelled as
 * AI pictures and never as data. Nothing here is written by the model as free text.
 */

const PALETTE = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)'] as const;
const ARABIC = /[؀-ۿ]/;

/** The SVG as a standalone file: the theme's colour variables replaced by their values. */
function svgFile(svg: SVGSVGElement): string {
  const styles = getComputedStyle(document.documentElement);
  const text = new XMLSerializer().serializeToString(svg)
    .replace(/var\((--[a-z0-9-]+)\)/g, (_, name: string) => styles.getPropertyValue(name).trim() || '#555');
  return `<?xml version="1.0" encoding="UTF-8"?>\n${text}`;
}

export function ResearchPlan({ plan }: { plan: string[] }) {
  const { t } = useTranslation();
  return (
    <details className="text-sm" data-testid="research-plan" data-questions={plan.length}>
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
        <ListChecks aria-hidden="true" className="me-1 inline size-3.5" />
        <span className="font-semibold">{t('chat.plan.title')}</span>
        <span className="ms-1">· {t('chat.plan.count', { count: plan.length })}</span>
      </summary>
      <ol className="mt-2 list-decimal ps-5" dir="auto">
        {plan.map((q, i) => <li key={i}>{q}</li>)}
      </ol>
    </details>
  );
}

export function ResearchTables({ tables, messageId }: { tables: ResearchTableBlock[]; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const sourcesShown = useContext(SourcesShown);
  const csv = (table: ResearchTableBlock) => {
    const header = sourcesShown ? [...table.columns, t('chat.researchTable.sources')] : table.columns;
    const lines = [header.map((h) => csvField(safeCell(h))).join(',')];
    for (const row of table.rows) {
      const cells = sourcesShown ? [...row.cells, row.citations.join(' ')] : row.cells;
      lines.push(cells.map((c) => csvField(safeCell(c))).join(','));
    }
    // A byte-order mark first, so spreadsheet programs read Arabic text as UTF-8.
    return `${String.fromCharCode(0xfeff)}${lines.join('\n')}\n`;
  };
  return (
    <>
      {tables.map((table) => (
        <figure key={table.id} className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-3"
          data-testid="research-table" data-table={table.id} data-rows={table.rows.length} data-message={messageId}>
          <figcaption className="flex flex-wrap items-center gap-2 text-sm font-semibold" dir="auto">
            <Table2 aria-hidden="true" className="size-3.5" />
            <bdi>{table.title}</bdi>
            <Badge variant="outline">{t('chat.researchTable.badge')}</Badge>
          </figcaption>
          <div className="max-w-full overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  {table.columns.map((c) => <th key={c} scope="col" className="px-2 py-1.5 text-start font-medium"><bdi>{c}</bdi></th>)}
                  {sourcesShown ? <th scope="col" className="px-2 py-1.5 text-start font-medium">{t('chat.researchTable.sources')}</th> : null}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0" data-testid="research-table-row">
                    {row.cells.map((cell, j) => (
                      <td key={j} className="px-2 py-1.5 tabular-nums" dir="auto"><bdi>{cell}</bdi></td>
                    ))}
                    {sourcesShown ? (
                      <td className="px-2 py-1.5 whitespace-nowrap">
                        {row.citations.map((id) => <CitationChip key={id} messageId={messageId} id={id} known />)}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {table.note ? <p className="text-xs text-muted-foreground" dir="auto">{table.note}</p> : null}
          {table.dropped ? (
            <p className="text-xs text-muted-foreground" data-testid="research-table-dropped">{t('chat.researchTable.dropped', { count: table.dropped })}</p>
          ) : null}
          <Button type="button" variant="ghost" size="sm" className="w-fit" data-testid="research-table-csv"
            onClick={() => download(`osrip-${table.id.toLowerCase()}-${messageId}-${language}.csv`, csv(table), 'text/csv;charset=utf-8')}>
            <Download aria-hidden="true" />{t('chat.table.csv')}
          </Button>
        </figure>
      ))}
    </>
  );
}

function ResearchChart({ chart, messageId }: { chart: ResearchChartBlock; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const values = chart.series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const W = 600;
  const H = 260;
  const pad = { top: 18, bottom: 46, left: 52, right: 12 };
  const slot = (W - pad.left - pad.right) / chart.labels.length;
  const y = (v: number) => pad.top + ((max - v) / span) * (H - pad.top - pad.bottom);
  const x = (i: number) => pad.left + slot * i + slot / 2;
  const ticks = [0, 1, 2, 3].map((k) => min + (span * k) / 3);
  const groupWidth = Math.min(64, slot * 0.7);
  const bar = groupWidth / chart.series.length;
  const fmt = (v: number | null) => (v === null ? '—' : formatDecimal(String(v), language, 2) ?? String(v));
  const summary = chart.labels.map((label, i) =>
    `${label}: ${chart.series.map((s) => `${s.name} ${fmt(s.values[i] ?? null)}`).join(', ')}`).join('; ');
  const short = (label: string) => (label.length > 14 ? `${label.slice(0, 13)}…` : label);
  return (
    <figure className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="research-chart"
      data-chart={chart.kind} data-points={chart.labels.length} data-table={chart.table_id} data-message={messageId}>
      <figcaption className="text-sm font-semibold" dir="auto">
        <bdi>{chart.title}</bdi>{chart.unit ? <span className="ms-1 font-normal text-muted-foreground">({chart.unit})</span> : null}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-2xl [direction:ltr]" role="img" aria-label={`${chart.title}. ${summary}`}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={pad.left} x2={W - pad.right} y1={y(tick)} y2={y(tick)} stroke="var(--chart-grid)" strokeWidth={tick === 0 ? 1.5 : 1} />
            <text x={pad.left - 6} y={y(tick) + 4} textAnchor="end" className="fill-muted-foreground text-[11px] tabular-nums">{formatCompact(tick, language)}</text>
          </g>
        ))}
        {chart.kind === 'bar'
          ? chart.labels.map((_, i) => chart.series.map((s, k) => {
            const v = s.values[i];
            if (v === null || v === undefined) return null;
            const top = Math.min(y(v), y(0));
            return (
              <rect key={`${i}-${k}`} x={x(i) - groupWidth / 2 + bar * k} y={top} width={Math.max(2, bar - 2)}
                height={Math.max(1, Math.abs(y(v) - y(0)))} rx={3} fill={PALETTE[k % PALETTE.length]} data-point={`${i}-${k}`} />
            );
          }))
          : chart.series.map((s, k) => {
            const points = s.values.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(' ');
            return (
              <g key={s.name}>
                <polyline points={points} fill="none" stroke={PALETTE[k % PALETTE.length]} strokeWidth={2.5} />
                {s.values.map((v, i) => (v === null ? null : (
                  <circle key={i} cx={x(i)} cy={y(v)} r={4} fill="var(--card)" stroke={PALETTE[k % PALETTE.length]} strokeWidth={2} data-point={`${i}-${k}`} />
                )))}
              </g>
            );
          })}
        {chart.labels.map((label, i) => (
          <text key={i} x={x(i)} y={H - pad.bottom + 18} textAnchor="middle" className="fill-muted-foreground text-[11px]"
            direction={ARABIC.test(label) ? 'rtl' : 'ltr'}>{short(label)}</text>
        ))}
      </svg>
      {chart.series.length > 1 ? (
        <ul className="flex flex-wrap gap-3 text-xs" data-testid="research-chart-legend">
          {chart.series.map((s, k) => (
            <li key={s.name} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block size-2.5 rounded-sm" style={{ background: PALETTE[k % PALETTE.length] }} /><bdi>{s.name}</bdi>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs text-muted-foreground">{t('chat.researchChart.basis', { table: chart.table_id })}</p>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">{t('chat.chart.data')}</summary>
        <table className="mt-1 text-xs" data-testid="research-chart-data">
          <thead><tr><th scope="col" className="px-2 py-1 text-start font-medium" />{chart.series.map((s) => <th key={s.name} scope="col" className="px-2 py-1 text-start font-medium"><bdi>{s.name}</bdi></th>)}</tr></thead>
          <tbody>
            {chart.labels.map((label, i) => (
              <tr key={i}><th scope="row" className="px-2 py-1 text-start font-normal"><bdi>{label}</bdi></th>
                {chart.series.map((s) => <td key={s.name} className="px-2 py-1 tabular-nums" dir="ltr">{fmt(s.values[i] ?? null)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

export function ResearchCharts({ charts, messageId }: { charts: ResearchChartBlock[]; messageId: number }) {
  return <>{charts.map((c) => <ResearchChart key={c.id} chart={c} messageId={messageId} />)}</>;
}

// ------------------------------------------------------------------ diagrams

type Box = { id: string; label: string; detail?: string | null; x: number; y: number };
const BOX_W = 168;
const BOX_H = 56;

/** Up to two lines of about 22 characters, cut with an ellipsis. */
function lines(label: string): string[] {
  const words = label.split(/\s+/);
  const out: string[] = [''];
  for (const word of words) {
    const last = out[out.length - 1] ?? '';
    if ((last + ' ' + word).trim().length <= 22) out[out.length - 1] = (last + ' ' + word).trim();
    else if (out.length < 2) out.push(word);
    else { out[1] = `${(out[1] ?? '').slice(0, 20)}…`; break; }
  }
  return out;
}

/** Layers by the longest path from a node with no incoming link (cycles are cut). */
function layers(diagram: DiagramBlock): Map<string, number> {
  const level = new Map(diagram.nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < diagram.nodes.length; pass += 1) {
    let changed = false;
    for (const e of diagram.edges) {
      const next = (level.get(e.from) ?? 0) + 1;
      if (next > (level.get(e.to) ?? 0) && next < diagram.nodes.length) { level.set(e.to, next); changed = true; }
    }
    if (!changed) break;
  }
  return level;
}

function layout(diagram: DiagramBlock, rtl: boolean, narrow: boolean): { boxes: Box[]; width: number; height: number } {
  if (diagram.kind === 'cycle' || diagram.kind === 'mindmap') {
    const centre = diagram.kind === 'mindmap';
    const ring = centre ? diagram.nodes.slice(1) : diagram.nodes;
    const r = Math.max(150, ring.length * 38);
    const cx = r + BOX_W / 2 + 10;
    const cy = r + BOX_H / 2 + 10;
    const boxes: Box[] = ring.map((node, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length;
      return { ...node, x: cx + (rtl ? -1 : 1) * r * Math.cos(a), y: cy + r * Math.sin(a) };
    });
    if (centre && diagram.nodes[0]) boxes.unshift({ ...diagram.nodes[0], x: cx, y: cy });
    return { boxes, width: cx * 2, height: cy * 2 };
  }
  const level = layers(diagram);
  const columns = new Map<number, string[]>();
  for (const node of diagram.nodes) columns.set(level.get(node.id) ?? 0, [...(columns.get(level.get(node.id) ?? 0) ?? []), node.id]);
  const depth = Math.max(...columns.keys()) + 1;
  const breadth = Math.max(...[...columns.values()].map((c) => c.length));
  // Hierarchies run top to bottom; so do flowcharts in a narrow card, to stay readable.
  const vertical = diagram.kind === 'hierarchy' || (narrow && depth > 2);
  const stepMain = vertical ? BOX_H + 56 : BOX_W + 56;
  const stepCross = vertical ? BOX_W + 24 : BOX_H + 28;
  const width = vertical ? breadth * stepCross + 20 : depth * stepMain + 20;
  const height = vertical ? depth * stepMain + 20 : breadth * stepCross + 20;
  const boxes = diagram.nodes.map((node) => {
    const l = level.get(node.id) ?? 0;
    const column = columns.get(l) ?? [];
    const offset = ((breadth - column.length) * stepCross) / 2 + column.indexOf(node.id) * stepCross;
    const main = 10 + l * stepMain + (vertical ? BOX_H : BOX_W) / 2;
    const cross = 10 + offset + (vertical ? BOX_W : BOX_H) / 2;
    const px = vertical ? cross : main;
    return { ...node, x: rtl && !vertical ? width - px : px, y: vertical ? main : cross };
  });
  return { boxes, width, height };
}

/** Where the line from a box's centre towards (tx, ty) leaves the box. */
function edgePoint(b: Box, tx: number, ty: number): [number, number] {
  const dx = tx - b.x;
  const dy = ty - b.y;
  const scale = Math.min(Math.abs((BOX_W / 2 + 4) / (dx || 1e-9)), Math.abs((BOX_H / 2 + 4) / (dy || 1e-9)));
  return [b.x + dx * scale, b.y + dy * scale];
}

function Diagram({ diagram, messageId }: { diagram: DiagramBlock; messageId: number }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const rtl = language === 'ar';
  const svgRef = useRef<SVGSVGElement>(null);
  const frameRef = useRef<HTMLElement>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => setNarrow((entry?.contentRect.width ?? 999) < 560));
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);
  const marker = `arrow-${useId().replace(/:/g, '')}`;
  const { boxes, width, height } = layout(diagram, rtl, narrow);
  const at = new Map(boxes.map((b) => [b.id, b]));
  const edges = diagram.edges.length || diagram.kind !== 'mindmap'
    ? diagram.edges
    : boxes.slice(1).map((b) => ({ from: boxes[0]?.id ?? '', to: b.id, label: null }));
  const described = diagram.edges.map((e) => `${at.get(e.from)?.label ?? e.from} → ${at.get(e.to)?.label ?? e.to}`).join('; ');
  return (
    <figure ref={frameRef} className="m-0 flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="research-diagram"
      data-kind={diagram.kind} data-nodes={diagram.nodes.length} data-message={messageId} data-layout={narrow ? 'narrow' : 'wide'}>
      <figcaption className="flex flex-wrap items-center gap-2 text-sm font-semibold" dir="auto">
        <Network aria-hidden="true" className="size-3.5" /><bdi>{diagram.title}</bdi>
        <Badge variant="outline">{t(`chat.diagram.kind.${diagram.kind}`)}</Badge>
      </figcaption>
      <div className="max-w-full overflow-x-auto">
        <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${width} ${height}`} width={width} height={height}
          className="h-auto max-w-full" role="img" aria-label={`${diagram.title}. ${described}`}>
          <defs>
            <marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--chart-2)" />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const a = at.get(e.from);
            const b = at.get(e.to);
            if (!a || !b) return null;
            const [x1, y1] = edgePoint(a, b.x, b.y);
            const [x2, y2] = edgePoint(b, a.x, a.y);
            return (
              <g key={i} data-edge={`${e.from}-${e.to}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--chart-2)" strokeWidth={1.75} markerEnd={`url(#${marker})`} />
                {e.label ? <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} textAnchor="middle" fontSize="11" fill="var(--muted-foreground)"
                  direction={ARABIC.test(e.label) ? 'rtl' : 'ltr'}>{e.label}</text> : null}
              </g>
            );
          })}
          {boxes.map((b, i) => {
            const text = lines(b.label);
            const first = diagram.kind === 'mindmap' && i === 0;
            return (
              <g key={b.id} data-node={b.id}>
                <title>{b.detail ? `${b.label}: ${b.detail}` : b.label}</title>
                <rect x={b.x - BOX_W / 2} y={b.y - BOX_H / 2} width={BOX_W} height={BOX_H} rx={10}
                  fill={first ? 'var(--chart-1)' : 'var(--card)'} stroke={first ? 'var(--chart-1)' : 'var(--chart-2)'} strokeWidth={1.5} />
                {text.map((line, k) => (
                  <text key={k} x={b.x} y={b.y + (k - (text.length - 1) / 2) * 15 + 4} textAnchor="middle" fontSize="13"
                    fontWeight={600} fill={first ? '#ffffff' : 'var(--foreground)'} direction={ARABIC.test(line) ? 'rtl' : 'ltr'}>{line}</text>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
      {diagram.nodes.some((n) => n.detail) ? (
        <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground" dir="auto">
          {diagram.nodes.filter((n) => n.detail).map((n) => <li key={n.id}><span className="font-medium text-foreground">{n.label}</span>: {n.detail}</li>)}
        </ul>
      ) : null}
      <Button type="button" variant="ghost" size="sm" className="w-fit" data-testid="research-diagram-svg"
        onClick={() => { if (svgRef.current) download(`osrip-${diagram.id.toLowerCase()}-${messageId}.svg`, svgFile(svgRef.current), 'image/svg+xml'); }}>
        <Download aria-hidden="true" />{t('chat.diagram.download')}
      </Button>
    </figure>
  );
}

export function ResearchDiagrams({ diagrams, messageId }: { diagrams: DiagramBlock[]; messageId: number }) {
  return <>{diagrams.map((d) => <Diagram key={d.id} diagram={d} messageId={messageId} />)}</>;
}

// ------------------------------------------------------------------ illustrations

export function GeneratedImages({ images, messageId }: { images: GeneratedImageBlock[]; messageId: number }) {
  const { t } = useTranslation();
  return (
    <>
      {images.map((image) => {
        const src = `${apiBaseUrl}/assistant/images/${encodeURIComponent(image.id)}`;
        return (
          <figure key={image.id} className="m-0 flex max-w-md flex-col gap-2 rounded-lg border border-border bg-card p-3"
            data-testid="generated-image" data-image={image.id} data-message={messageId}>
            <img src={src} alt={t('chat.image.alt', { prompt: image.prompt })} className="h-auto w-full rounded-md bg-muted" loading="lazy" />
            <figcaption className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="sand" data-testid="generated-image-label"><ImageIcon aria-hidden="true" className="me-1 size-3" />{t('chat.image.label')}</Badge>
              <span className="text-muted-foreground">{t('chat.image.model', { model: image.model })}</span>
              <a href={src} download={`osrip-illustration-${messageId}.png`} className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-2">
                <Download aria-hidden="true" className="size-3" />{t('chat.image.download')}
              </a>
            </figcaption>
          </figure>
        );
      })}
    </>
  );
}
