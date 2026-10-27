# OpenAI, datasets, charts and research reports

Branch `feature/openai-research-platform` (October 2026). This adds the official OpenAI SDK,
analysis of uploaded datasets, more chart types with a type switch, searchable tables, and
research and dataset reports exported as PDF, Excel and CSV. The existing features are
unchanged.

## Status: what was tested, and how

| Part | Tests (no network) | Live |
|---|---|---|
| OpenAI answers and web search through the official SDK | 16 tests with `httpx.MockTransport` (requests, streaming and stopping, structured replies, quota and rate limits, web search options) | **Not tested.** No OpenAI key is configured, so no OpenAI call has been made |
| Dataset upload and analysis (CSV, Excel, JSON) | 34 unit and 5 database tests; full-stack browser test | Checked in the browser on the local site |
| AI summary of a dataset | Unit and database tests with stub models | **Tested live with DeepSeek** (`deepseek-flash`), Arabic: every number matched the computed results, nothing removed |
| Charts (line, bars, pie, scatter, columns, histogram), chart switch, table search, filter and sort | Full-stack browser test | Checked in the browser in English and Arabic, light and dark |
| Research and dataset reports; PDF, Excel and CSV | 19 unit and 3 database tests; full-stack browser test (PDF and Excel downloads) | A dataset report in Arabic and a research report from a **live DeepSeek answer**. The PDFs were rendered to images and checked page by page |

## Architecture

```text
Browser (React)                       FastAPI backend
 Datasets page ── upload ───────────▶ datasets/parsing.py    read CSV, Excel, JSON (limits; nothing run)
                                      datasets/analysis.py   statistics, trends, unusual values, charts
 AI summary button ─────────────────▶ datasets/summary.py    answering model → numbers checked
 Chat answer "Report" ──────────────▶ analysis_reports.py    frozen report (osrip.report/1)
 Report page ── PDF / Excel / CSV ──▶ documents/            pdf.py, xlsx.py, export.py (no new libraries)
                                      assistant/provider.py  OpenAIProvider → openai_api.py (official SDK)
                                      research/search.py     OpenAIWebSearch → openai_api.py
```

Keys are read only by the backend from `backend/.env` (or the hosting secret settings). The
browser never receives a key, and no `VITE_*` setting holds one.

## OpenAI integration (official SDK, Responses API)

Checked against https://developers.openai.com/api/docs on 2026-10-26.

- `backend/app/services/openai_api.py` uses the `openai` package (declared in `pyproject.toml`
  and `requirements.lock`: `openai==2.54.0`). The SDK's own retries are off; OSRIP retries a
  transient failure once and meters every call (`provider_call`), with daily call limits and an
  optional daily budget.
- **Answers** (`OpenAIProvider`): the Responses API with function tools (`store: false`; the
  reasoning items of each turn are passed back with the tool results). One offered tool is
  named in `tool_choice`. While a question can be stopped, the call is **streamed** and closed
  when the person presses Stop, which cancels it on OpenAI's side. Background responses can be
  cancelled with `responses.cancel`.
- **Structured outputs**: `OpenAIProvider.structured()` asks for a strict `json_schema` reply.
  A refusal, an incomplete reply or a non-object is an error, never data. Other providers get
  the same shape through one forced tool call (`provider.structured_reply`).
- **Errors**: short codes only (`http_401`, `http_429`, `timeout` ...) with OpenAI's error code
  kept as a safe token (`model_not_found`, `insufficient_quota` ...); messages are never kept.
  A used-up quota or spending limit is reported as a balance problem and not retried; a fallback
  provider may answer instead.
- **Web search** (`OpenAIWebSearch`): the `web_search` tool (not the legacy preview) with
  `tool_choice: required`, Oman as the approximate location, `search_context_size`, an
  optional domain filter, and `include: ["web_search_call.action.sources"]`. Cited statements
  are labelled as a provider's summary; the other sources the search consulted follow as
  addresses with no text, to be read before anything is said about them.

### Settings (`backend/.env`, server only)

| Setting | Meaning |
|---|---|
| `OSRIP_OPENAI_API_KEY` | The API key (never in the frontend, logs or Git) |
| `OSRIP_OPENAI_MODEL` | Answering model, e.g. `gpt-6.1-sol` (balanced), `gpt-6-luna` (cheapest), `gpt-6-astra` (most capable) |
| `OSRIP_OPENAI_SEARCH_MODEL` | Model for the web search route |
| `OSRIP_OPENAI_TIMEOUT_SECONDS` | Seconds per call (default 60) |
| `OSRIP_OPENAI_REASONING_EFFORT` | `none` … `xhigh`; lower is cheaper and faster (unset: the model's default) |
| `OSRIP_OPENAI_SEARCH_CONTEXT_SIZE` | `low`, `medium` (default) or `high` |
| `OSRIP_OPENAI_SEARCH_ALLOWED_DOMAINS` | Optional JSON list, e.g. `["ncsi.gov.om", "data.gov.om"]` |
| `OSRIP_ASSISTANT_PROVIDER=openai` / `OSRIP_RESEARCH_PROVIDER=openai` | Use OpenAI for answers / web search |
| `OSRIP_PROVIDER_PRICES`, `OSRIP_PROVIDER_DAILY_BUDGET_USD`, `OSRIP_PROVIDER_DAILY_CALL_LIMIT` | Cost estimates and spending limits |

### Setting up OpenAI (account owner)

1. Sign in at https://platform.openai.com and set up API billing for the organisation or project
   (https://platform.openai.com/settings/organization/billing). A ChatGPT subscription is not API
   access.
2. Create a project key at https://platform.openai.com/api-keys. Give it only the project it
   needs; set a monthly budget on the project's limits page.
3. Put the key in `backend/.env` on the server (`OSRIP_OPENAI_API_KEY=...`) with
   `OSRIP_OPENAI_MODEL` and, for search, `OSRIP_OPENAI_SEARCH_MODEL`. Never paste it into the chat,
   a `VITE_*` variable, a commit or an issue.
4. Restart the API, then check from `backend/`:

   ```powershell
   .\.venv\Scripts\python.exe -m app.cli provider-check openai
   ```

   Without the settings it prints the missing names and makes no call (tested). With them it
   makes one small live call. Settings › AI and search providers › Test does the same in the site.

### Cost

OpenAI's price list (https://developers.openai.com/api/docs/pricing, 2026-10-26), USD per
million tokens: `gpt-6.1-sol` 2.00 input / 10.00 output; `gpt-6-luna` 0.10 / 0.50;
`gpt-6-astra` 10.00 / 50.00. The `web_search` tool costs 10.00 per 1,000 searches, plus the
search content tokens at the model's input rate.

Rough estimate for one research answer with `gpt-6.1-sol`, assuming 5 model rounds of about
6,000 input tokens and 400 output tokens each, and 3 searches: 30,000 × 2.00 / 1M + 2,000 ×
10.00 / 1M + 3 × 0.01 ≈ **0.11 USD**, before search content tokens. An ordinary data question
(2–3 rounds, no search) is about 0.02–0.04 USD. A dataset summary is one call of a few
thousand tokens, under 0.02 USD. These are estimates, not measurements. OSRIP records the
real tokens of every call; set `OSRIP_PROVIDER_PRICES` to see estimated costs and to enforce
`OSRIP_PROVIDER_DAILY_BUDGET_USD`:

```text
OSRIP_PROVIDER_PRICES={"openai": {"input_per_mtok": 2.0, "output_per_mtok": 10.0, "per_search": 0.01}}
OSRIP_PROVIDER_DAILY_BUDGET_USD=5
```

## Datasets

`/datasets` (sidebar, More tools), for accounts with `dataset.analyze` (analysts, data
managers, administrators; migration 0024).

- **Formats**: CSV (UTF-8 or Windows-1256; delimiter detected), Excel `.xlsx` (the first sheet
  with values, or a named sheet; dates read as dates), JSON (records, columns and rows, or
  column arrays; numbers keep their digits).
- **Limits**: 5 MB, 20,000 rows and 60 columns per file; 50 datasets per account; 20 AI
  summaries per account per day (all configurable). Nothing in a file is run (no formulas,
  macros, links or external entities).
- **Privacy**: a dataset belongs to its owner only (others get "not found"), is never added to
  the published statistics, and is never sent to a model as rows. The AI summary gets the
  computed results only, with the file's names and labels marked as data, not instructions.
- **Analysis** (deterministic, exact decimal arithmetic): column kinds and units, count, sum,
  mean, median, quartiles, standard deviation, minimum and maximum with their rows; trends per
  series (change, percentage change, compound annual growth over full years, least-squares
  slope, unusual jumps); unusual values by the modified z-score (Iglewicz and Hoaglin) or IQR
  fences; comparisons between groups with shares; correlations (labelled: not causation);
  duplicate rows; missing values counted and left out, never treated as zero. Trends are not
  made up over repeated periods: values are never summed or averaged behind the reader's back.
- **AI summary**: written by the configured answering model (OpenAI with structured outputs,
  or DeepSeek, Anthropic or Gemini through a forced tool call). Every number is checked against
  the computed results; a sentence with any other number is removed, and the count is shown.

## Charts and tables

- New chart types beside the study charts: **pie** (shares, offered only for zero or positive
  values with a meaningful total), **scatter** (most correlated pair) and **grouped columns**,
  plus a histogram. The server lists the types that stay valid for each table, and the page
  offers them as a switch. Studies (`osrip.study/1`) keep line, bar and heatmap only.
- Tables of the dataset: search across columns (Arabic-Indic digits included), filter by a
  column's value, sort (numbers by value; missing values last), 50 rows per page, CSV of the
  rows found.
- Arabic: right to left, the time axis mirrored, Latin digits as elsewhere on the site.

## Research reports and exports

- **From a dataset**: research questions, executive summary (the checked AI summary in the
  report's language, or the computed findings), the dataset, statistics, trends, unusual
  values, comparisons, correlations, charts, conclusions and limits, references.
- **From an answer**: only an answer that passed the evidence check, from the person's own
  conversation. Its citations become numbered references; platform calculations are listed
  as C1, C2 … with their method and inputs.
- Reports are frozen (database trigger), private and deletable.
- **PDF**: written directly, embedding a subset of a TrueType font with Arabic and Latin
  letters. Arabic letters are shaped (joined forms, lam-alef), lines are ordered right to left
  with numbers and English names kept readable, and charts are vector drawings from the
  report's own tables. On Linux the API image installs DejaVu Sans; elsewhere set
  `OSRIP_REPORT_FONT_PATH`. Without a font the export answers 503 `pdf_font_missing`.
- **Excel**: the report, one sheet per table and per chart's values, references; numbers as
  numbers, text never a formula; right-to-left sheets in Arabic. Dataset workbooks start with
  the rows.
- **CSV**: the same content, text protected against spreadsheet formulas.
- Platform reports (`/reports/{id}`) can now be downloaded as PDF and Excel too.

## Security and spending

- Keys only in `backend/.env` or the host's secret settings; `.env` files are git-ignored. The
  repository was scanned for keys before each push.
- Every new endpoint requires sign-in (CSRF-checked); datasets need `dataset.analyze`; every
  record is checked against its owner. Request bodies are validated (sizes, lengths, counts).
- Uploads: size limit read before parsing; Excel archives checked for entry count and size;
  XML with document types or entities refused; cells are text.
- Spending: daily call limit and optional daily budget per provider, per-account assistant
  limits, 20 dataset summaries per account per day, the OpenAI timeout, and no SDK retry storms.
- Web pages, uploaded files and model replies are untrusted: they never become instructions,
  and every number shown is checked against evidence or computed by the server.

## Limitations

- **OpenAI has not been called live**: there is no OpenAI key in this environment. The code
  follows the documentation and is tested against its documented shapes only.
- PDF text: short-vowel marks are left out; letters outside the basic Arabic alphabet (such as
  Persian letters) keep their isolated form; the ordering is a simplified version of the Unicode
  bidirectional algorithm (enough for report text, not for every possible mix).
- Excel workbooks contain tables of each chart's values, not native Excel charts.
- Dataset analysis covers one period column and up to eight numeric columns for trends and
  correlations; bigger files are limited to the configured sizes.
- The Docker images were prepared but not built here (Docker was not available).
