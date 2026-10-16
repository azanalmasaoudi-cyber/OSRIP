# OSRIP design system

A **proposed** visual identity for an academic prototype (release 1.0, 2026-10-16, branch
`redesign/dark-dashboard`). It is a dashboard design in two themes:

- **Dark (the default):** a near-black page with slightly raised charcoal cards.
- **Light:** a near-white page with white cards.

Both have thin borders, rounded corners, white or ink text with muted secondary text, and
emerald as the one action and chart colour. Copper and sand are small accents. It is not
official government branding. Asset sources and licences are in [`assets.md`](assets.md).

**Theme choice:** Light, Dark or System. It is set in the top bar (Settings on the Account
page; the menu on phones) and remembered in this browser only (`osrip.theme`). The resolved
theme is written to `<html data-theme>` before the first paint by `public/theme-init.js`, an
external file because the Content-Security-Policy forbids inline scripts. `src/lib/theme.ts`
keeps it up to date, including device changes while System is chosen.

**Layout:**
- **Sidebar** (15 rem): Overview; the four resources; Map, Studies, Scenarios, Sources and
  AI Assistant; Reports and the Research library; Account; administration. Its footer holds
  the data mode.
- **Top bar** (56 px): page title, search (Ctrl+K), English/Arabic, theme and the account menu.
- **Phones:** the sidebar becomes a menu drawer that also holds the theme and data mode, and
  search opens in a dialog.

The live catalogue is at **`/design-reference`** (linked in the footer). It
renders every token, control, badge, the indicator card and every data state.
Everything on that page is labelled demonstration content.

## Tokens (`frontend/src/index.css`)

| Role | Token | Light | Dark |
|---|---|---|---|
| Page | `--background` | `#f5f5f6` | `#09090b` near-black |
| Card | `--card` | `#ffffff` | `#141416` charcoal |
| Sunken, hover | `--muted` | `#eeeef0` | `#1c1c1f` |
| Ink / secondary ink | `--foreground` / `--muted-foreground` | `#0a0a0b` / `#55555d` | `#f4f4f5` / `#a1a1aa` |
| Borders / form controls | `--border` / `--border-strong` | `#e2e2e6` / `#85858f` | `#26262a` / `#6e6e78` |
| Primary actions, links | `--primary`, `--primary-hover` | `#047857` emerald, `#065f46` | `#34d399`, `#6ee7b7` |
| Sidebar and top bar | `--sidebar`, `--sidebar-active`, `--sidebar-accent` | `#fbfbfc`, `#ececef`, `#047857` | `#0c0c0e`, `#1c1c20`, `#34d399` |
| Introduction stage, brand mark | `--nav`, `--nav-active`, `--nav-ring` | `#0c3326` deep emerald, `#165040`, `#e8c48e` | `#06120d`, `#153a2c`, `#e8c48e` |
| Accent | `--accent`, `--copper` | `#a0502a` copper text, `#b86b3a` rules | `#e6a679`, `#d38a56` |
| Details | `--sand`, `--sand-subtle` | `#b08d57`, `#f1ead9` | `#c9a96e`, `#2a261d` |
| Focus | `--ring` | `#3f3f46` (neutral, distinct from the emerald selection) | `#d4d4d8` |
| Error | `--destructive` | `#b42318` | `#f87171` |
| Data modes | `--synthetic*`, `--verified*` | amber / emerald tints | darker tints |
| Charts | `--chart-1`, `--chart-2`, `--chart-grid` | `#059669` emerald, `#2563eb` blue, `#e7e7ea` | `#10b981`, `#60a5fa`, `#232327` |

Copper is used sparingly (the "what it does not do" callout, the avatar ring at rest). It is
never used to encode data. Emerald marks the one primary action per view and single-series
chart marks; blue is the comparison series.

**Contrast.** `npm run check:contrast` reads the tokens directly from `index.css` (the light
`:root` block and the `:root[data-theme="dark"]` block) and checks 42 text, control, focus,
sidebar and chart pairs per theme against WCAG 2.x (4.5:1 for text, 3:1 for control borders,
focus rings and chart marks). All 84 pass (2026-10-16).

**AI Assistant avatar.** `AssistantAvatar` (`.assistant-avatar` in `index.css`): a fictional,
AI-generated face in a circle, always next to the visible label "AI Assistant" /
"المساعد الذكي". Ring colours follow real states: copper at rest, teal while listening or
speaking (a ripple while the microphone is open, a spinner while processing), red on error.
While synthesised speech plays, the ring width and three small level bars follow the
measured loudness (`--assistant-voice`); this is a speaking animation, not lip
synchronisation. Under reduced motion the face and bars stay still.
**Type.** IBM Plex Sans with IBM Plex Sans Arabic (OFL 1.1), self-hosted, in
weights 400, 500 and 600. Arabic gets an Arabic-first font stack and a taller
line height. Letter-spacing and uppercase apply only in LTR, because
letter-spacing breaks Arabic joining. Numbers use Latin digits in both
languages (an existing decision, see `SPEC_CONFLICTS.md`).

**Patterns.** `pattern-lattice` (eight-point star lattice) and
`pattern-crenellation` (stepped merlons) are CSS mask utilities, so either can
take any token colour through `bg-*`. They are kept at low opacity and never
placed behind charts.

## Components

| Component | File | Notes |
|---|---|---|
| App shell | `components/layout/AppShell.tsx` | Sticky green sidebar at `lg` and above. Below that, a green top bar with a drawer. Includes the skip link and focus management on route change. |
| Navigation | `components/layout/SidebarNav.tsx` | One nav tree for the sidebar and the drawer. The Energy parent uses `aria-current="true"`; Electricity and Water are separate pages. |
| Language switcher | `components/layout/LanguageSwitcher.tsx` | `aria-pressed` toggle buttons. Changes labels and direction only, never the URL. |
| Filters | `components/common/FilterBar.tsx`, `ui/select.tsx`, `state/useUrlFilter.ts` | Labelled native selects. Values are codes kept in the URL. Collapses behind a toggle on phones. |
| Indicator card | `components/common/IndicatorCard.tsx` | Latest value, unit, period, previous period and source. No computed change: formulas stay in the backend. |
| Series card | `components/common/SeriesCard.tsx` | Context, an optional chart, an accessible table and source details. |
| Charts | `components/common/Charts.tsx` | HTML/CSS so they mirror in RTL. Single hue, bars at most 24px wide, a 4px rounded data end, hairline grid, labelled values. The table carries the same numbers for assistive technology. |
| Dialog | `components/ui/dialog.tsx` | Native `<dialog>` with `showModal()`: inert background, Escape to close, focus returns to the opener. Also used for the mobile drawer. |
| Source details | `components/common/SourceDetails.tsx` | Definition, unit, value type, mode, source, publisher, version, access date, link and note. |
| States | `components/common/StatePanel.tsx` | `loading` (skeleton), `empty` (with reset), `no_verified_data`, `error` (with retry and detail), `not_implemented`, `restricted`. Missing values are shown as the text "Missing", never 0. |
| Photo | `components/common/Photo.tsx` | Credited figure. Photographs appear only on the landing page (and as credit thumbnails). |

## Accessibility and motion

- Real RTL: `dir` on `<html>`, logical properties (`ms-`, `pe-`, `start-`),
  directional icons flipped, and the drawer opening from the inline-start
  side.
- Keyboard: skip link, one global `:focus-visible` outline (sand on green
  surfaces), native controls, and focus moved to `<main>` after navigation.
- `prefers-reduced-motion`: transitions, animations and smooth scrolling are
  turned off.
- Responsive: checked at 390, 1024, 1280 and 1440 px wide with no horizontal
  scroll. Dark mode follows `prefers-color-scheme`.
