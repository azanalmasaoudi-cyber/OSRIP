# OSRIP design system

A **proposed** visual identity for an academic prototype (release 2.0, 2026-11-01, branch
`redesign/omani-decision-platform`; release 1.0 was `redesign/dark-dashboard`). It is a
bilingual decision-support platform rather than a dashboard, in two themes:

- **Light (the default):** white cards on a cool off-white page, navy ink.
- **Dark:** deep navy surfaces with slightly raised navy cards.

In both, the navigation is **navy**, the one action and single-series chart colour is
**emerald**, and a **soft gold** marks section rules, the active navigation item and the
focus ring on navy. It is not official government branding: no seals, emblems or crests.
Asset sources and licences are in [`assets.md`](assets.md).

**Theme choice:** Light, Dark or System. It is set in the top bar (the menu on phones) and
remembered in this browser only (`osrip.theme`). The resolved theme is written to
`<html data-theme>` before the first paint by `public/theme-init.js`, an external file because
the Content-Security-Policy forbids inline scripts. `src/lib/theme.ts` keeps it up to date,
including device changes while System is chosen.

**Layout:**
- **Sidebar** (16 rem, navy): the Overview; *Sectors* (Electricity, Water, Food Security,
  Trade); *Decision support* (AI Assistant, Studies, Reports, Sources); *More tools* (Analysis
  workspace, Datasets, Map, Scenarios, Research library); *You* (Account, Settings);
  *Administration*. Its footer holds the data mode.
- **Top bar** (64 px, white): page title, search (Ctrl+K), English/Arabic, theme and account.
- **Content** up to `--content-max` (120 rem).
- **Three columns on wide screens.** From 1792 px (`3xl`), a sector page shows the numbered
  selection steps, the results and an *AI insights and sources* column side by side, and the
  AI Assistant shows the conversation's sources beside the conversation. From 1280 px (`xl`) the
  steps sit beside the results and the insights go under them; below that, one column.
- **4K.** From 2200 px wide the root font size grows (112.5 %, 131.25 % from 2880 px, 150 % from
  3600 px), so a 4K screen at 100 % scaling keeps the proportions of a 1920 px screen; every
  size and width is in rem. Breakpoints are measured in CSS pixels and do not move.
- **Phones:** one column, no horizontal scrolling; the sidebar becomes a navy drawer that also
  holds the theme and data mode, and search opens in a dialog.
- **Motion:** only the short route fade and state changes (hover borders, open/close). No tilt,
  parallax or decorative animation; reduced motion removes the rest.

**Charts are never drawn automatically.** Every chart (sector results, the assistant's
answers, studies, research jobs, dataset analyses, analysis reports, forecasts and scenarios)
sits behind a *Show chart* button (`components/ui/chart-on-request.tsx`, or the sector page's own
button) and is drawn from the same rows as the table beside it. The assistant draws a chart
straight away only when the question itself asks for one.

**Data-quality badges** (`components/common/QualityBadges.tsx`), above every sector result and
explained on the Overview: *Verified* (published values in verified-source mode; never for
synthetic data, which shows *Synthetic demonstration data* instead), *Pending review*
(provisional, preliminary or estimated figures), *Missing data* (periods with no published
value), *Last updated* (the latest publication or retrieval date of the rows shown) and
*Source* (the publishers). All are computed from the rows on screen.

**Technical details** (the API address, the offline prototype, the answer, voice, search and
retrieval services) appear only under Settings › Services and the administrators' Service
health page, not on the main pages.

The live catalogue is at **`/design-reference`** (linked in the footer). It
renders every token, control, badge, the indicator card and every data state.
Everything on that page is labelled demonstration content.

## Tokens (`frontend/src/index.css`)

| Role | Token | Light | Dark |
|---|---|---|---|
| Page | `--background` | `#f5f7fa` | `#07111f` deep navy |
| Card | `--card` | `#ffffff` | `#0d1b2e` |
| Sunken, hover | `--muted` | `#edf1f6` | `#13243b` |
| Ink / secondary ink | `--foreground` / `--muted-foreground` | `#0b1b33` navy / `#4a5874` | `#eef2f8` / `#a9b6ca` |
| Borders / form controls | `--border` / `--border-strong` | `#dbe2ec` / `#7d8ca3` | `#1d3150` / `#6c809e` |
| Primary actions, links | `--primary`, `--primary-hover` | `#047857` emerald, `#065f46` | `#34d399`, `#6ee7b7` |
| Navigation | `--sidebar`, `--sidebar-active`, `--sidebar-accent` | `#0b1f3a` navy, `#173560`, `#e2c27f` soft gold | `#061427`, `#12294a`, `#e2c27f` |
| Navy bands, brand mark | `--nav`, `--nav-active`, `--nav-ring` | `#0b1f3a`, `#173560`, `#e2c27f` | `#061427`, `#12294a`, `#e2c27f` |
| Gold | `--accent` (text), `--copper` (rules, avatar ring) | `#7a5810`, `#a7802e` | `#e2c27f`, `#d2ae68` |
| Gold chips | `--sand`, `--sand-subtle`, `--sand-foreground` | `#c4a265`, `#f6efde`, `#5b430f` | `#cdac6c`, `#262113`, `#ecd7a3` |
| Focus | `--ring` (gold `--nav-ring` on navy, via `.on-nav`) | `#1d3a66` navy | `#e2e8f2` |
| Error | `--destructive` | `#b42318` | `#f87171` |
| Data modes | `--synthetic*`, `--verified*` | amber / emerald tints | darker tints |
| Quality | `--pending*`, `--missing*` | gold tint / grey with a dashed border | darker tints |
| Charts | `--chart-1`, `--chart-2`, `--chart-grid` | `#059669` emerald, `#1d4ed8` blue, `#e3e8ef` | `#10b981`, `#7aa7ff`, `#1b2d47` |

Gold never encodes data. Emerald marks the one primary action per view and single-series
chart marks; blue is the comparison series.

**Contrast.** `npm run check:contrast` reads the tokens directly from `index.css` (the light
`:root {` block and the `:root[data-theme="dark"] {` block) and checks 46 text, control, focus,
navigation, quality-badge and chart pairs per theme against WCAG 2.x (4.5:1 for text, 3:1 for
control borders, focus rings and chart marks). All 92 pass (2026-11-01). The script now finds
each block by its selector; before, it matched the selector's first mention in the header
comment, so its "dark" results repeated the light ones.

**Type sizes.** Normal reading text (sentences, descriptions, answers, notices) is 1 rem =
12 pt = 16 CSS px (`text-base`) and is never set smaller. Labels, helper notes, tables and
metadata are 0.875 rem (14 px, `text-sm`). Only badges, chips, step numbers and photo credits
are 0.75 rem (12 px, `text-xs`). Headings step up from 1.125 rem to 2.25 rem (3.75 rem on the
landing hero), so the hierarchy stays clear.
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
| App shell | `components/layout/AppShell.tsx` | Sticky navy sidebar at `lg` and above. Below that, a white top bar with a navy drawer. Includes the skip link and focus management on route change. |
| Navigation | `components/layout/SidebarNav.tsx` | One nav tree for the sidebar and the drawer. The Energy parent uses `aria-current="true"`; Electricity and Water are separate pages. |
| Language switcher | `components/layout/LanguageSwitcher.tsx` | `aria-pressed` toggle buttons. Changes labels and direction only, never the URL. |
| Filters | `components/common/FilterBar.tsx`, `ui/select.tsx`, `state/useUrlFilter.ts` | Labelled native selects. Values are codes kept in the URL. Collapses behind a toggle on phones. |
| Indicator card | `components/common/IndicatorCard.tsx` | Latest value, unit, period, previous period and source. No computed change: formulas stay in the backend. |
| Series card | `components/common/SeriesCard.tsx` | Context, an optional chart, an accessible table and source details. |
| Charts | `series/SeriesParts.tsx` (`TimelineChart`), `dashboard/TrendChart.tsx`, `forecast/ForecastChart.tsx`, `studies/StudyCharts.tsx`, `datasets/ViewChart.tsx`, `assistant/InlineChart.tsx` | Drawn so they mirror in RTL. Single hue, bars at most 24px wide, a 4px rounded data end, hairline grid, labelled values. The table carries the same numbers for assistive technology. |
| Dialog | `components/ui/dialog.tsx` | Native `<dialog>` with `showModal()`: inert background, Escape to close, focus returns to the opener. Also used for the mobile drawer. |
| Source details | `components/common/SourceDetails.tsx` | Definition, unit, value type, mode, source, publisher, version, access date, link and note. |
| States | `components/common/StatePanel.tsx` | `loading` (skeleton), `empty` (with reset), `no_verified_data`, `error` (with retry and detail), `not_implemented`, `restricted`. Missing values are shown as the text "Missing", never 0. |
| Photo, sector image | `components/common/Photo.tsx`, `components/brand/SectorImage.tsx` | Credited figures of real places (Wikimedia Commons). Used on the landing page, the Overview and the sector headers; electricity has no licensed photograph yet and shows the labelled project illustration. |
| Quality badges | `components/common/QualityBadges.tsx` | Verified / Synthetic, Pending review, Missing data, Last updated, Source, from the rows on screen; `QualityLegend` explains them. |
| Chart on request | `components/ui/chart-on-request.tsx` | Show chart / Hide chart; the chart is not rendered until asked for. |

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
