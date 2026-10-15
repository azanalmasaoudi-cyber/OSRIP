# OSRIP design system

A **proposed** visual identity for an academic prototype (release 0.8, 2026-10-02):
deep navy for structure and navigation, teal for primary actions, warm ivory page
backgrounds, restrained copper accents, sand details and subtle geometric patterns
inspired by Omani architecture. It is not official government branding. Asset sources
and licences are in [`assets.md`](assets.md).

The live catalogue is at **`/design-reference`** (linked in the footer). It
renders every token, control, badge, the indicator card and every data state.
Everything on that page is labelled demonstration content.

## Tokens (`frontend/src/index.css`)

| Role | Token | Light | Dark |
|---|---|---|---|
| Page | `--background` | `#f8f5ee` warm ivory | `#0c1525` |
| Card | `--card` | `#fffdf8` | `#132038` |
| Sunken | `--muted` | `#f0ebe0` | `#1a2944` |
| Ink / secondary ink | `--foreground` / `--muted-foreground` | `#14213a` navy ink / `#4d5869` | `#ede7da` / `#aab4c5` |
| Primary actions, links | `--primary`, `--primary-hover` | `#0b6b66` teal, `#08544f` | `#5ccdc1`, `#80dbd1` |
| Navigation and structure | `--nav`, `--nav-active` | `#0f2340` deep navy, `#1d3a63` | `#08111f`, `#1a2d4e` |
| Marks on navy | `--nav-accent` | `#4fc3b6` (active-page rule and icon) | `#5ccdc1` |
| Accent | `--accent`, `--copper` | `#a0502a` copper text, `#b86b3a` rules | `#e6a679`, `#d38a56` |
| Details | `--sand`, `--sand-subtle` | `#b08d57`, `#efe4ce` | `#c9a96e`, `#2e2a20` |
| Focus | `--ring` (page), `--nav-ring` (navy surfaces) | `#a0502a` copper, `#e8c48e` | `#e6a679`, `#e8c48e` |
| Error | `--destructive` | `#a8321f` | `#f0907c` |
| Data modes | `--synthetic*`, `--verified*` | amber / teal tints | |
| Charts | `--chart-1`, `--chart-2`, `--chart-grid` | `#0b6b66` teal, `#1d3a63` navy, `#e3dccd` | `#5ccdc1`, `#9fb6dd`, `#2a3b5b` |

Copper is used sparingly: the page-header rule, the "what it does not do" callout, the
avatar ring at rest and the focus ring. It is never used to encode data. Teal marks the
one primary action per view.

**Contrast.** `npm run check:contrast` reads the tokens directly from `index.css` (light
`:root` and the dark media-query block) and checks 35 text, control, focus and chart pairs
per theme against WCAG 2.x (4.5:1 for text, 3:1 for control borders, focus rings and chart
marks). All 70 pass (2026-10-02).

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
