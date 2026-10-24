import { Fragment, type ReactNode } from 'react';

/**
 * A small, safe Markdown renderer for assistant answers: headings, paragraphs (single line
 * breaks kept), bulleted and numbered lists, pipe tables, **bold**, *italic*, `code`, links
 * (http and https only, opened in a new tab) and citation markers such as [E3], drawn by
 * `cite`. It builds React elements from the text and never inserts HTML, so nothing in an
 * answer can run or change the page. Anything it does not recognise stays plain text.
 */
export function Markdown({ text, cite }: { text: string; cite: (id: string) => ReactNode }) {
  return <>{blocks(text).map((block, i) => renderBlock(block, i, cite))}</>;
}

type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] };

const HEADING = /^(#{1,4})\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function cells(row: string): string[] {
  return row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

function blocks(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? '';
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      out.push({ kind: 'heading', level: heading[1]!.length, text: heading[2] ?? '' });
      i += 1;
      continue;
    }
    if (TABLE_ROW.test(line) && TABLE_RULE.test(lines[i + 1] ?? '')) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && TABLE_ROW.test(lines[i] ?? '')) {
        rows.push(cells(lines[i] ?? ''));
        i += 1;
      }
      out.push({ kind: 'table', head, rows });
      continue;
    }
    const ordered = NUMBERED.test(line);
    if (ordered || BULLET.test(line)) {
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (i < lines.length && pattern.test(lines[i] ?? '')) {
        items.push(pattern.exec(lines[i] ?? '')?.[1] ?? '');
        i += 1;
      }
      out.push({ kind: 'list', ordered, items });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length) {
      const next = lines[i] ?? '';
      if (!next.trim() || HEADING.test(next) || BULLET.test(next) || NUMBERED.test(next)
        || (TABLE_ROW.test(next) && TABLE_RULE.test(lines[i + 1] ?? ''))) break;
      para.push(next);
      i += 1;
    }
    out.push({ kind: 'paragraph', lines: para });
  }
  return out;
}

function renderBlock(block: Block, key: number, cite: (id: string) => ReactNode): ReactNode {
  switch (block.kind) {
    case 'heading': {
      const className = block.level <= 2 ? 'mt-2 text-base font-semibold' : 'mt-1 text-sm font-semibold';
      return block.level <= 2
        ? <h3 key={key} className={className} dir="auto">{inline(block.text, cite)}</h3>
        : <h4 key={key} className={className} dir="auto">{inline(block.text, cite)}</h4>;
    }
    case 'list': {
      const items = block.items.map((item, j) => <li key={j} dir="auto">{inline(item, cite)}</li>);
      return block.ordered
        ? <ol key={key} className="list-decimal space-y-1 ps-5">{items}</ol>
        : <ul key={key} className="list-disc space-y-1 ps-5">{items}</ul>;
    }
    case 'table':
      return (
        <div key={key} className="max-w-full overflow-x-auto">
          <table className="min-w-[16rem] border-collapse text-sm">
            <thead>
              <tr>{block.head.map((h, j) => <th key={j} scope="col" className="border-b border-border-strong px-2 py-1 text-start font-semibold" dir="auto">{inline(h, cite)}</th>)}</tr>
            </thead>
            <tbody>
              {block.rows.map((row, j) => (
                <tr key={j}>{row.map((c, k) => <td key={k} className="border-b border-border px-2 py-1 tabular-nums" dir="auto">{inline(c, cite)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      return (
        <p key={key} dir="auto">
          {block.lines.map((l, j) => <Fragment key={j}>{j > 0 ? <br /> : null}{inline(l, cite)}</Fragment>)}
        </p>
      );
  }
}

// Bold, inline code, a link, a citation marker, then italic: the first that matches wins.
const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\[(E\d+)\]|(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])|(?<![\w_])_([^_\s][^_]*?)_(?![\w_])/g;

function inline(text: string, cite: (id: string) => ReactNode): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const [, bold, code, label, url, citation, italic, underscored] = m;
    if (bold !== undefined) out.push(<strong key={n}>{bold}</strong>);
    else if (code !== undefined) out.push(<code key={n} className="rounded bg-muted px-1 font-mono text-[0.85em]">{code}</code>);
    else if (label !== undefined && url !== undefined) {
      out.push(<a key={n} href={url} target="_blank" rel="noreferrer noopener" className="text-primary underline underline-offset-2">{label}</a>);
    } else if (citation !== undefined) out.push(<Fragment key={n}>{cite(citation)}</Fragment>);
    else out.push(<em key={n}>{italic ?? underscored}</em>);
    last = at + m[0].length;
    n += 1;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
