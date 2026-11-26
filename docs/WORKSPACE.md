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
in the address (`?tab=data|analysis|charts`); the guided analysis is the default.

The three views share **one selection per sector** (indicator, area, period view), kept per data
mode for the browser session (`frontend/src/state/sectorSelections.ts`). Choosing an indicator in
one view chooses it in the others.

| View | What is shown |
|---|---|
| Data and indicators | Every indicator published for the sector in the chosen data mode, as cards (latest value, unit, period, previous period, data mode, area, source details), filtered by area and frequency; period kinds are listed apart. A card is flagged **"May be out of date"** when its latest period ended longer ago than the usual publication interval (24 months for annual data, 9 for quarterly, 6 for monthly or year-to-date), and a banner counts them: old data is flagged, never hidden. Beside them: the sources behind the cards and, for Food Security and Trade, the commodity register. **Analyse** on a card makes it the selection and opens the Analysis. |
| Guided analysis | Five steps, one at a time: selection, results, analysis, objectives, recommendations (see "Guided analysis" below). Nothing in this view is written by AI. |
| Tables and charts | The period-first workflow: indicator, area or breakdown, frequency, then a start and end period from those published, **Show results**; then the table, calculations, insights and downloads, and the chart only after **Show chart**. |

States are explicit in every view: loading, error with retry, empty, no verified data, mixed
frequency (with a choice) and stale data.

All four sectors use the same components (`frontend/src/components/sector/SectorIndicators.tsx`,
`SectorGuide.tsx`, `AreaComparison.tsx`, `AskMulhim.tsx`, `SectorWorkflow.tsx`); nothing is
copied per sector.

The **data freshness** panel beside the cards lists, for the series shown (most recent first), the
end of the latest period, the unit, where it applies (the area, a published group of governorates,
and the source's stated coverage), the publication and retrieval dates, the review status and the
source's address.

## Guided analysis (23 November 2026)

A sector's **Guided analysis** tab (the default) is one task at a time, as a state machine kept in
the address (`frontend/src/lib/guideSteps.ts`, `frontend/src/components/sector/SectorGuide.tsx`):

| Step | What is shown | Moves on with |
|---|---|---|
| 1. Selection | Indicator, governorate, the wilayats of that governorate that publish the indicator (or "No published wilayat data"), breakdown, frequency, start and end period, data mode. Nothing analytical. The sector's saved reports. | **Show results** |
| 2. Results | The published observations of exactly that selection: coverage, summary, unit, period, quality badges, the table; sources collapsed. | **Analyze results** |
| 3. Analysis | The server's findings for the selection, its calculations, the chart (only after **Show chart**), rule-based review cards (factors the data point to), the comparison of governorates where valid, limitations, Al Mulhim's study, forecast, scenario and report requests, and the axis's decision brief (loaded only when opened). | **Set my objectives** |
| 4. Objectives | Reduce shortages, improve efficiency, use the surplus, strengthen production and trade, diversify; or the person's own words (matched by fixed rules, `backend/app/services/objectives.py`, never sent to an AI). | **Show recommendations** (refused, and said so, without an objective) |
| 5. Recommendations | `POST /analysis/{section}/guidance` (`backend/app/services/guidance.py`): the facts used (latest value, change, coverage, year-to-date apart), then ranked actions, each with its rationale, prerequisites, risks and missing evidence; a CSV download, *Save report* (analysts) and a full report with these objectives from Al Mulhim. | **Change objectives**, **Start again** |

- **Address.** `step`, the applied selection (`ind`, `at`, `bd`, `freq`, `from`, `to`) and the
  objectives (`goals`, `goal`) are in the address: Back and Forward move between steps, and a reload
  or a shared link returns to the same step. An address asking for a step whose inputs are missing
  shows the furthest one it can (no results before a selection, no recommendations before an
  objective).
- **Network.** Each step loads only what it shows; the results' timeline is reused by the analysis
  and the recommendations are fetched once per selection and objectives.
- **Recommendations.** Rule-based and reproducible (rules version in the reply): one template per
  sector and objective, chosen by what the published series does (rising, falling or flat; one value
  gives no direction). The text quotes only figures from the selection's timeline; better-evidenced
  actions come first; indicators OSRIP does not publish for the area are listed as missing evidence.
  They are prompts for review, not decisions or forecasts of outcomes.
- **Al Mulhim.** Asked for recommendations without an objective, it gives the results, then the
  analysis, and asks which objectives to serve; the reply lets the person tick them and send them as
  the next message. When the request names objectives, or asks for a full report, it goes straight
  through without asking again (`GOAL_RULES` in `backend/app/services/assistant/service.py`).

The **Tables and charts** tab keeps the full period-first workbench on the same selection.


## Electricity and water: annual indicators and the official outlook (24 November 2026)

**Annual indicators** (the Data and indicators view of Electricity and Water, `AnnualIndicators.tsx`,
`GET /series/annual-table`):
- One row per published series, never merged:
  - electricity: the five customer categories, net actual consumption, electricity distributed and
    electricity produced;
  - water: national production and distribution; Muscat, Dhofar and the other regions together;
    and, as a separate group, Nama Water Services' supply and delivery within its own operations
    (all governorates except Dhofar).
- Full years side by side (2022–2025 by default), or one year at a time. Each cell has its value,
  the server's year-on-year change (`timeline.build`, never a model's figure) and a mark when the
  source calls it provisional (2025). A missing year stays empty.
- *Download CSV* (`GET /series/annual-table.csv?…&language=en|ar`) gives the same cells, one line
  per indicator, area and year, with nature, revision status, the provisional flag, the
  year-on-year change, source and page. The notes come first as comment lines.
- The notes under the table say what the data do not support: 2022 consumption (36,427.1 GWh) and
  distribution (36,178.6 GWh) are different published indicators; no shortage, surplus or leakage
  is computed from production minus consumption or distribution; the utility's figures are not the
  national ones.

**The official outlook** (`SectorOutlook.tsx`, `GET /outlook`, table `outlook_item`, migration 0036):
- Forecasts, targets, plans and options from the PWP 7-year statements 2026–2032 (Issue 20), held
  apart from observations. Each item has a class: observed base year, estimate, forecast, policy
  target, planned or under consideration.
- Each item also has its scope, unit (MW, percent, m³ per day, or a date for an event), the
  statement's own status note, the source page and the file's SHA-256.
- Items are staged as pending (`POST /outlook/batches`, `import.create`). Only those approved by a
  person with `import.approve` (`POST /outlook/{id}/review`, audited) are shown.
- **Reviewed in Data Management** (*Official outlook: review*, `OutlookReview.tsx`; 26 Nov 2026):
  - items waiting for review, approved or rejected, by sector;
  - each with its kind of evidence, value or date, year, scope and the statement's status note;
  - its source, page, retrieval date, file hash and batch.
  *Approve* needs no note; *Reject* needs one. The decision's date and note are shown to
  reviewers only, never in the public outlook. An administrator without `import.approve`
  sees where to grant it.
- The database refuses an observed or estimated item dated in or after the statement's year, so a
  2032 value cannot be an observation.
- In the guided analysis's Analysis step the outlook opens only on request ("Show the official
  outlook 2026–2032 (not observed)"). It is grouped by class, with a legend; a target or plan is never shown as achieved.

**Al Mulhim** recognises outlook questions in Arabic and English (peak demand, renewable share and
targets, storage, planned plants, capacity; not a scenario request). It calls `get_outlook` and
answers with the approved items and their classes; the reply shows them as the sector does, under
"Official outlook 2026–2032". With no approved item the tool reports `no_data` and gives no figure.

**Importing the pack** (`backend/scripts/stage_electricity_water.py`, see
`docs/data-imports/2026-11-electricity-water/README.md`):
- The default run is a dry run. It maps the workbook, compares every figure with the value read
  from its source PDF (a difference stops it) and with what is already published or waiting. It
  then writes the import files, the outlook items and a report, and changes nothing.
- `--stage --as USER` creates validated imports (waiting for approval in Data Management) and
  pending outlook items. It is idempotent.
- `--reject --as USER` withdraws what is not yet published or approved.
- No wilayat figure is derived from a governorate total.

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
