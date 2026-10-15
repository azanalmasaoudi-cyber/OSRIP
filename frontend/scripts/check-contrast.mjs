// WCAG 2.x contrast for the OSRIP colour tokens. Text needs 4.5 (3 for large), UI/focus needs 3.
// Run: npm run check:contrast. The tokens are read from src/index.css (the light :root block and
// the :root block inside the prefers-color-scheme: dark media query), so they cannot drift.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const css = readFileSync(fileURLToPath(new URL('../src/index.css', import.meta.url)), 'utf8');

function block(source, startIndex) {
  const open = source.indexOf('{', startIndex);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  throw new Error('unbalanced CSS');
}

function tokens(body) {
  const out = {};
  for (const m of body.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b/g)) out[m[1]] = m[2];
  return out;
}

const light = tokens(block(css, css.indexOf(':root')));
const darkMedia = css.indexOf('@media (prefers-color-scheme: dark)');
const dark = { ...light, ...tokens(block(css, css.indexOf(':root', darkMedia))) };

const lum = (hex) => {
  const c = hex.replace('#', '').match(/../g).map((h) => parseInt(h, 16) / 255);
  const l = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const checks = [
  // [fg, bg, min, label] (token names without the leading --)
  ['foreground', 'background', 4.5, 'body text'],
  ['foreground', 'card', 4.5, 'card text'],
  ['muted-foreground', 'background', 4.5, 'secondary text on page'],
  ['muted-foreground', 'card', 4.5, 'secondary text on card'],
  ['muted-foreground', 'muted', 4.5, 'secondary text on muted'],
  ['primary', 'background', 4.5, 'link text'],
  ['primary', 'card', 4.5, 'link on card'],
  ['primary', 'muted', 4.5, 'link on muted'],
  ['primary-foreground', 'primary', 4.5, 'primary button label'],
  ['primary-foreground', 'primary-hover', 4.5, 'primary button hover'],
  ['nav-foreground', 'nav', 4.5, 'sidebar text'],
  ['nav-muted', 'nav', 4.5, 'sidebar secondary'],
  ['nav-foreground', 'nav-active', 4.5, 'sidebar active item'],
  ['nav-ring', 'nav', 3, 'sidebar focus ring'],
  ['nav-ring', 'nav-active', 3, 'sidebar focus on active'],
  ['accent', 'background', 4.5, 'copper accent text'],
  ['accent', 'card', 4.5, 'copper accent on card'],
  ['accent', 'muted', 4.5, 'copper accent on muted'],
  ['copper-foreground', 'copper-subtle', 4.5, 'copper chip text'],
  ['ring', 'background', 3, 'focus ring on page'],
  ['ring', 'card', 3, 'focus ring on card'],
  ['ring', 'muted', 3, 'focus ring on muted'],
  ['sand-foreground', 'sand-subtle', 4.5, 'sand chip text'],
  ['sand-foreground', 'background', 4.5, 'sand eyebrow text'],
  ['destructive', 'background', 4.5, 'error text'],
  ['destructive', 'card', 4.5, 'error text on card'],
  ['synthetic-foreground', 'synthetic', 4.5, 'synthetic badge'],
  ['verified-foreground', 'verified', 4.5, 'verified badge'],
  ['border-strong', 'card', 3, 'form control border'],
  ['border-strong', 'background', 3, 'form control border on page'],
  ['chart-1', 'card', 3, 'chart series 1 vs surface'],
  ['chart-2', 'card', 3, 'chart series 2 vs surface'],
  ['copper', 'card', 3, 'avatar ring (copper) vs surface'],
  ['nav-accent', 'nav', 3, 'emerald mark on navigation'],
  ['nav-accent', 'nav-active', 3, 'emerald mark on active item'],
];

let fails = 0;
for (const [name, t] of Object.entries({ light, dark })) {
  console.log(`\n== ${name}`);
  for (const [f, b, min, label] of checks) {
    if (!t[f] || !t[b]) {
      console.log(`MISSING token --${!t[f] ? f : b}`);
      fails++;
      continue;
    }
    const r = ratio(t[f], t[b]);
    const ok = r >= min;
    if (!ok) fails++;
    console.log(`${ok ? 'PASS' : 'FAIL'} ${r.toFixed(2).padStart(5)} (>=${min}) ${label}  ${t[f]} on ${t[b]}`);
  }
}
console.log(`\n${fails} failing pair(s)`);
process.exitCode = fails ? 1 : 0;
