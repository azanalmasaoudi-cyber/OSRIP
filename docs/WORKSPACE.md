# Analysis in the sector pages, Al Mulhim's results and live studies

Until November 2026 OSRIP had a separate **Analysis workspace** (`/workspace`) and separate
**Studies** and **Forecasts and Scenarios** entries in the navigation. They have been folded
into the places where people already work:

- each of the four sectors (Electricity, Water, Food Security, Trade) has three views of the
  same sector: **Data and indicators**, **Analysis** and **Tables and charts**;
- **Al Mulhim** is the one assistant: a study, a forecast or a scenario is asked for in a
  sentence, and its results are shown inside the conversation.

Nothing analytical was removed. The backend endpoints, permission checks, stored studies,
forecasts, scenarios and saved results are unchanged; the pages `/studies`, `/studies/:id` and
`/forecasts` still open from saved links, they are only not in the menu.

## The old address

`/workspace` redirects to a sector's Analysis (`frontend/src/lib/workspaceRedirect.ts`, unit
tested in `frontend/tests/workspace-redirect.test.mjs`):

- `section` (or the first section of `domain`) chooses the sector; Electricity otherwise;
- only safe values are carried over: the data mode, an indicator code
  (`^[A-Z][A-Z0-9_]{1,63}$`), an area code (`^OM(-[A-Z0-9]{1,8}){0,2}$`) and the frequency (as
  the period view). Anything else (dates, free text, unknown values) is dropped.

The sector page reads `indicator`, `area` and `view` once into the sector's selection and then
removes them from the address.

## Sector views

One view is shown at a time, so there is no box that scrolls inside the page. The tabs follow
the ARIA tab pattern: the arrow keys (mirrored in Arabic), Home and End. The chosen view is kept
in the address (`?tab=data|analysis|charts`); the Analysis is the default.

The three views share **one selection per sector** (indicator, area, period view), kept per data
mode for the browser session (`frontend/src/state/sectorSelections.ts`). Choosing an indicator in
one view chooses it in the others.

| View | What is shown |
|---|---|
| Data and indicators | Every indicator published for the sector in the chosen data mode, as cards (latest value, unit, period, previous period, data mode, area, source details), filtered by area and frequency; period kinds are listed apart. A card is flagged **"May be out of date"** when its latest period ended longer ago than the usual publication interval (24 months for annual data, 9 for quarterly, 6 for monthly or year-to-date), and a banner counts them: old data is flagged, never hidden. Beside them: the sources behind the cards and, for Food Security and Trade, the commodity register. **Analyse** on a card makes it the selection and opens the Analysis. |
| Analysis | The current selection (indicator, area, period view), changeable here. For it: the server's validated findings (`POST /studies/preview`, the deterministic trend study, not stored) with method, assumptions, limitations, references and the section's rule-based recommendations, which need a person's review; the governorates compared (only when the server finds at least two governorates' own values comparable, otherwise the page says why; no licensed boundary geometry, so no choropleth); **Ask Al Mulhim** (Study, Forecast, Scenario: each opens the conversation with the request written for this selection, in the reader's language, sent only when the person presses Send); this session's studies (each opens again under its reply); and the axis's decision brief. Nothing in this view is written by AI. |
| Tables and charts | The period-first workflow: indicator, area or breakdown, frequency, then a start and end period from those published, **Show results**; then the table, calculations, insights and downloads, and the chart only after **Show chart**. |

States are explicit in every view: loading, error with retry, empty, no verified data, mixed
frequency (with a choice) and stale data.

All four sectors use the same components (`frontend/src/components/sector/SectorIndicators.tsx`,
`SectorAnalysis.tsx`, `AreaComparison.tsx`, `AskMulhim.tsx`, `SectorWorkflow.tsx`); nothing is
copied per sector.

## Al Mulhim: studies, forecasts and scenarios from a sentence

`backend/app/services/assistant/routing.py` recognises, in Arabic and English, what a sentence
asks OSRIP to run (`intent`: `study`, `forecast` or `scenario`). A stated change ("increases by
15%", «زادت 20%») makes a scenario even when the word forecast is used. In Automatic mode a
study or a forecast is answered in Analyze mode and a scenario in Scenario mode; a mode the
person chose is kept. The service adds the intent's rules to the model's instructions
(`INTENT_RULES` in `service.py`), and the reply records the intent (shown as a badge).

| Request | What runs | What the reply shows |
|---|---|---|
| "Create a detailed study of electricity consumption in Oman." / «أنشئ دراسة عن الأمن الغذائي» | `run_study`: the allowlisted study engine; the study is stored | The whole study inside the reply: title, question, method, findings, table, interpretation, recommendations, limitations and references, with a link to its own page (`/studies/<id>`). |
| "Forecast electricity demand in Oman." / «تنبأ باستهلاك المياه» | `get_forecast`: a stored forecast run if there is one; otherwise `forecasting.preview`, the same engine and policy, computed and not stored | The estimate with its 80% interval, method, training cut-off and backtest metrics, labelled as a model estimate, not an official statistic. When the history is too short (annual: 8 training and 4 test periods; monthly: 24 and 12) there is **no number**, and the engine's reasons are shown. |
| "What happens if water demand increases by 15% over five years?" / «ماذا لو زادت الواردات 20%؟» | `scenario_projection` from the latest published value (a total change over several years becomes its compound yearly rate) | The base, assumptions, formula, a table and a chart, labelled **hypothetical scenario, not a forecast**. Without a stated change, Al Mulhim asks for it and assumes nothing. |

The numbers come from the tools, never from the model: the server checks every number the model
writes against the evidence it cites, and the tables and charts are drawn from the tool results
(`structured.studies`, `structured.forecasts`, `structured.scenarios`). One forecast card is
shown per series, the most informative one (an estimate before a withheld result before "no such
series").

## Reports in Al Mulhim and the sectors (20 November 2026)

The Reports Dashboard is no longer in the navigation. Report generation, saving, viewing and
exporting all stay, and are reached from Al Mulhim and from each sector:

- **Asking for a report.** `routing.intent` recognises a report request in Arabic or English
  ("Create a report on water in Muscat for 2024", «أنشئ تقريرًا عن الكهرباء»). It is checked
  before the other intents, and `routing.report_type` names what the report covers: a study,
  forecast or scenario report when those words appear, otherwise the sector's data. The model
  identifies the sector, indicator, area (national unless named) and period, and calls
  **`build_report`**.
- **Building it.** `build_report` uses `reports.build_content`, the same function a saved
  platform report is frozen with: the published observations, the section's calculations, its
  rule-based review cards and the dataset versions. It runs inside the assistant's read-only
  transaction, so nothing is stored. For a study, forecast or scenario report the model also runs
  `run_study`, `get_forecast` or `scenario_projection`, and their results appear beside the report.
  The grounding check accepts only the report's own figures in the text.
- **Showing it.** The reply carries `structured.report`, built from the tool's result, never
  from the model. It shows:
  - the title;
  - the scope: sector, area, period, and when it was prepared;
  - each series as a table, with a chart (the first one open);
  - the calculations;
  - "findings to review and next steps" from the review cards (rule-based, for a person to check).

  Its sources are kept in one collapsed list rather than spread through the conversation. At most
  12 series and 60 rows each are shown; a saved report holds all of them.
- **Downloading and saving.**
  - Anyone can download the report's tables as CSV. The file is built in the browser, with the
    same formula-safe rules as the server's exports.
  - With the **report.create** permission (analysts), *Save report* sends the reply's section
    and filters to the existing `POST /reports`. That stores a frozen platform report at
    `/reports/:id`, with its CSV, PDF and Excel exports
    (`/reports/{id}/export.csv|pdf|xlsx`).
  - Without that permission, the save is refused by the API (403), as before. Any signed-in
    person can still use *Create a report* under the answer for a PDF, Excel or CSV of the
    answer; it now includes the report's tables, calculations, review cards and sources.
  - Visitors are asked to sign in to save.
- **In the sectors.** A sector's Analysis has a **Report** button among Ask Al Mulhim's requests
  ("Create a report on {indicator} in {area}", written for the current selection and sent only
  when the person presses Send). It also has **Saved reports for this sector**: the platform
  reports this person may open (published ones, and their own private ones), each at its saved
  address, with a link to all saved reports.
- **Unchanged.**
  - `/reports`, `/reports/:id` and `/reports/analysis/:id` still open: saved links work.
  - Private reports are "not found" to anyone but their owner.
  - Every report endpoint and permission check is as it was. No database change.

## Live studies under a reply

A reply prepared as a study has **Open the study**. The live study opens under that reply and
closes with the same button. A study chosen from a sector's list opens under its reply on Al
Mulhim's page (`/assistant?study=<id>`). While it runs, everything is labelled **provisional**.
The panel shows:

- **Progress:** the steps actually reached, in order. For example: question received, checking OSRIP's published data, calculating, validating tables (units, periods, values), searching the web, reading sources, checking numbers and citations.
- **Sources:** each source appears as it is retrieved, with its data status (approved official observation, synthetic demonstration data, unreviewed external evidence, calculated, forecast, scenario).
  - Each source opens a dialog with its details. Web text is labelled untrusted.
  - Closing the dialog returns focus to the source.
- **Partial failures:** failed searches, unreadable pages, or a table rejected by validation are listed. They are never hidden.
- **Tables and charts:** each dataset is drawn only after it passes validation, on the server and again in the browser. Each one shows its data status and its state:
  - provisional;
  - final (the answer rests on it);
  - not used in the answer;
  - provisional, study stopped.
- **When the study completes:**
  - the validated findings, one per sentence of the checked answer;
  - the narration controls;
  - recommendations;
  - assumptions;
  - method;
  - references (the cited sources).
- **Controls:** Stop research, which cancels the request (it is never charged). A study opened again is rebuilt from its stored events and looks as it did.

## Narration and highlighting

The spoken explanation is generated by the server from the **same validated findings** the panel shows: one segment (`N1`, `N2`, …) per finding, with the evidence markers removed.

Each segment names what it is about:

- the dataset rows whose source it cites;
- the whole table, when it cites a study;
- no target, when nothing in its paragraph is cited. Then only the finding itself is highlighted, at section level.

Segments are played **one at a time**:

| Mode | How it plays |
|---|---|
| Server speech (Azure, or the test provider) | `POST /assistant/voice/speak` with `segment_id`, in the persona's voice |
| Browser voice | Used when there is no server speech, in a voice of the persona's gender |
| Neither | Step-through only (previous and next) |

The segment being read is known from real playback events (start and end of that segment). While it plays, its rows, its points on the chart, its finding and its sources are highlighted. **There is no word-level timing.** The interface says that highlighting follows sentences, not words. Stop interrupts playback and keeps the highlight on the sentence reached.

## Live study events (protocol)

Events come from `app/services/assistant/study_events.py`. They are stored in `study_event` and streamed as server-sent events:

- `GET /api/v1/assistant/requests/{request_id}/events` (signed in);
- `GET /api/v1/assistant/guest/requests/{request_id}/events` (guest cookie).

The study id is the request id the client sent with the question.

| Event | Payload |
|---|---|
| `study.started` | `attempt`, `mode`, `language`, `data_mode` |
| `stage` | `stage`, `label` (EN/AR): only steps actually reached |
| `search` | `evidence_id`, `status`, `query`, `provider`, `role`, `display_only` |
| `evidence` | `evidence_id`, `kind`, `data_status`, `title`, `area`, `period_start`/`period_end`, `value`, `unit`, `source` (title, publisher, url, dataset version, record), web fields, `status` |
| `dataset` | `dataset_id` (D1…), `origin`, `provisional`, `data_status`, `title`, `table` (columns with units, rows of decimal strings or null), `charts` (referencing only the table's columns), `rows_meta` (`row_id`, `evidence_id`), `evidence_ids`, `source_evidence_id`, `study` (method, assumptions, limitations) |
| `warning` | `code` (`search_failed`, `tool_error`, `page_unreadable`, `dataset_rejected`, `withheld`), `detail` (EN/AR) |
| `study.completed` | `status`, `message_id`, `findings` (F1…), `narration` (N1…, with `targets`), `final_datasets`, `provisional_datasets`, `recommendations`, `assumptions`, `method` |
| `study.cancelled` / `study.failed` | `reason` / `code` |

Every event carries `study_id`, `seq` and `result_version`.

**Consistency rules:**

1. **Validated before written.** A dataset that fails the shared table rules is never written. A `warning` is sent instead.
   - The rules: unique columns, a unit on every numeric column, decimal strings, known columns only, charts that reference only the table's own columns, one row id per row.
   - The browser checks every dataset again with the same rules before drawing it.
2. **In order, once.** `seq` orders events and is the resume point (`Last-Event-ID`). A repeated event is ignored.
3. **Newer wins.** `result_version` rises with every dataset and with completion. An older version never replaces a newer one.
4. **Stale events are ignored.**
   - Events of another study (cancelled or superseded) are ignored.
   - Nothing is applied after `study.cancelled`, `study.failed` or `study.completed`, except a new attempt of the same request.
   - The server stops writing at the first terminal event.
5. **Nothing final without completion.** Datasets become final only when completion names them. After a stop or failure, nothing becomes final.
6. **No invention.** Every number comes from published observations, OSRIP's deterministic calculations and studies, or a scenario the person stated (labelled `assumption_scenario`). "Generate data" means calculated results or labelled scenarios, never new official observations.

`GET …/requests/{id}/study` returns all of a study's events as JSON. Events are deleted with their conversation, account or guest session.

## Libraries

- **Charts:** OSRIP's existing SVG/HTML charts (line, ranked bar, heatmap). ECharts was not approved (C56).
- **Transitions:** `motion` (already installed), restrained: sources and tables fade in. Users who ask for reduced motion get no movement.
- No 3D charts are used.
- No new package.

## Verification

- **Backend:** `tests/test_live_study.py` covers:
  - findings and narration;
  - one unit per table;
  - rejected tables;
  - completion rules;
  - the event order and replay;
  - server-sent events with resume;
  - study and comparison tables;
  - cancellation;
  - a failed search;
  - ownership;
  - segment speech;
  - deletion with the conversation;
  - preview without storage.
- **Backend, requests in a sentence:** `tests/test_assistant_intents.py` (the recognised requests in Arabic and English, the intent rules, one forecast card per series) and `tests/test_assistant_intents_integration.py` (the real study, forecast and scenario tools through the API against the database, with synthetic series: an estimate, a withheld forecast, an Arabic forecast, a scenario, a scenario without a stated change, a stored study).
- **Browser, full stack:**
  - `e2e-api/sector-analysis.spec.ts`: the three views in all four sectors and their keyboard tabs; cards, stale flags and sources; Analyse; the selection shared with Tables and charts; the comparison state; Al Mulhim's prefilled requests; the `/workspace` redirect with unsafe values dropped; Arabic right to left in dark mode without sideways scrolling;
  - `e2e-api/mulhim-results.spec.ts`: a study, a forecast (English and Arabic) and a scenario asked in a sentence, with their results in the reply; a scenario without a stated change asked for; the saved study page; the live study under its reply with the row highlighted while its sentence is read, and interruption; a partial failure; keyboard access to sources; a study reopened from a sector with unchanged values in Arabic; crafted streams with late, superseded and invalid events;
  - `e2e-api/sector-phone.spec.ts` (Pixel 7): the sector views and a live study on a phone, without sideways scrolling.
- **Browser, offline prototype:** `e2e/shell.spec.ts` (the Data and indicators view, language switching with the filters kept, the `/workspace` redirect, the menu without the removed entries).
