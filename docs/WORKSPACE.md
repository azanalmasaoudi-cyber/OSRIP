# Analytical workspace and live studies

The Analysis workspace (`/workspace`) is OSRIP's analytical workspace. It was on the Overview
page until the Overview became the project introduction; its reference charts are now drawn
only when the reader presses "Show chart". It covers the three domains:

- Energy and Essential Services (Electricity and Water);
- Food Security;
- Trade.

You can filter and compare the published data. You can also ask the assistant a question and watch its study take shape as it researches. This arrived with migration `0019_study_events`.

## Layout

| Screen | What is shown |
|---|---|
| Wide (1024 px and more) | Filters across the top. Then two areas side by side: the analysis on the left, with **Data** and **Study** tabs; and the assistant column on the right, with the persona's portrait, its real state, and the chat. |
| Phone | The same filters, with three tabs: **Data**, **Study**, **Assistant**. Asking a question brings the Study tab forward. "Ask a follow-up" returns to the Assistant tab, and the conversation is kept. |

- The floating assistant button is hidden on this page, because the assistant is already on screen.
- The chat mounts only when the person presses "Ask …". Opening the workspace alone creates no guest session.
- Tabs follow the ARIA tab pattern:
  - Tab reaches the selected tab;
  - the arrow keys move between tabs, mirrored in Arabic;
  - Home and End jump to the first and last tab.

## Data tab

- **Filters:** domain, section, indicator, governorate (or national), from year, to year, and data mode. They are stored in the address as codes, so they survive a reload or a language switch.
- **Indicator cards:** latest value, unit, period, previous period, data mode, area and source details.
  - A card is flagged **"May be out of date"** when its latest period ended longer ago than the usual publication interval: 24 months for annual data, 9 for quarterly, 6 for monthly or year-to-date.
  - A banner counts the flagged series. Old data is flagged, never hidden.
- **History of the chosen indicator:** one dataset is built from the published series and checked with the same schema as the assistant's tables (below). It is drawn as a line chart and as a sortable, filterable table, both from exactly the same rows.
  - The period filter limits both.
  - Missing values stay missing.
  - Every chart has its table.
- **Governorates:** each governorate's own published value, drawn as a ranked bar chart and a table.
  - This view appears only when the server finds the values comparable (same unit and period length) and at least two governorates publish their own value.
  - Otherwise the page says why no geographic view is shown.
  - No licensed boundary geometry exists in OSRIP, so no choropleth map is drawn.
- **States:** loading, error with retry, empty, no verified data, mixed frequency (with a choice) and stale data. Each is explicit.

## Study tab

**Study of the current selection.** The deterministic trend study of the chosen indicator and area, computed by the server (`POST /studies/preview`) and not stored. It shows:

- findings;
- method;
- assumptions;
- limitations;
- references (dataset version, period and source link);
- the section's rule-based recommendations, which need a person's review before anyone acts on them.

**Assistant study.** The question's live study. While it runs, everything is labelled **provisional**. The panel shows:

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
- **Controls:**
  - Stop research, which cancels the request (it is never charged);
  - Ask a follow-up;
  - "Studies in this session", to return to an earlier study. It is rebuilt from its stored events and looks as it did.
- **Opening a study from a reply:** each reply prepared as a study has an "Open the study" button. It opens the study in the workspace from any page.

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
- **Browser:** `e2e-api/workspace.spec.ts` (desktop) and `e2e-api/workspace-phone.spec.ts` (Pixel 7) cover:
  - filters, cards and stale flags;
  - chart and table consistency;
  - sorting;
  - the geographic and verified-data states;
  - a live study with the row highlighted while its sentence is read;
  - interruption;
  - a partial failure;
  - keyboard access to sources and tabs;
  - returning to an earlier study;
  - the Arabic interface with unchanged values;
  - crafted streams with late, superseded and invalid events;
  - phone tabs.
