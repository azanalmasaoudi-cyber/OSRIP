# Research that reads sources and saves verified figures

The assistant can search the web, read original documents, and save figures that the backend can
check into the platform's published data. The model proposes figures; backend validation (or a
reviewer) decides. Nothing the model writes reaches the data otherwise.

## Workflow

Question → `web_search` → `read_web_page` (the original document) → `submit_observations` →
validation → saving through the import workflow → answer with a research summary.

| Tool | What it may do |
|---|---|
| `web_search` | Search through the configured route (DeepSeek Search, Brave, ...). Results are logged and cached (`research_search`). |
| `read_web_page` | Read a page that a search result pointed to (never an address the model or a page suggests). Every read is stored with its text (`research_document`). |
| `get_observations`, `latest_period`, ... | Read published, approved observations only. |
| `submit_observations` | Propose figures read in documents. Only for signed-in users with `research.submit` (analysts, data managers, administrators, or a per-user grant). Never for guests. |
| `research_status` | What was saved or is waiting, with sources and record ids. |
| `make_table`, `make_chart` | Tables and charts built by the backend from published rows (a chart only when the question asks for one). |

The model has no SQL, file system or general write access. Fetched text is untrusted evidence.

## When a figure is saved automatically

All of these must hold (`app/services/research/saving.py`):

1. It comes from a document read in full in this answer or job, not from a search snippet or
   summary.
2. The document is on an official Omani host (`app/services/research/sources.py`).
3. The value as written appears in the stored document text; the passage around it is kept.
4. Indicator, area and unit are platform codes; the unit is one the indicator is already published
   in (nothing is rescaled); the period's dates match its kind (month, quarter, calendar year, or
   January to a month end for a year-to-date total), start in 2022 or later and ended by the date
   the document was read.
5. It is not already published (same series, period and value: `duplicate`) and does not differ from
   a published or submitted figure (`conflict`, kept for a reviewer, never written over).
6. `OSRIP_RESEARCH_AUTO_SAVE=true`.

Otherwise the figure is `pending` (with its reasons) or `rejected`. A model's confidence is never a
check. Pending and conflicting figures are not observations: tables, charts, summaries and answers
cannot use them.

Saving registers a source for the document (publisher, title, address, publication date, retrieval
date), stages the figures as an ordinary import, validates, approves and publishes them as the
research service account, all or nothing, under an advisory lock. A figure is reported as saved
only after that publication commits, with its observation id. The same figure from the same
document is stored once (a unique index), so repeating a run adds nothing.

Reviewers (`research.review`) see pending, conflicting and saved figures in the research queue. "Approve
and save" publishes a mapped figure through the same path; for a conflict it is saved beside the
published value as a revision with its own source.

## Data updates by sector

An administrator creates a schedule with kind `data_update` (Settings, scheduled reports: sector,
frequency, pages and credits per run, monthly cap). It runs only when enabled, with paid use
allowed and `OSRIP_SCHEDULED_REPORTS_ENABLED=true`; "Run now" queues one run. The research worker
runs it without a browser (`app/services/research/data_update.py`): one run per schedule at a
time, a lock per sector, cancellation before each model round, and the job's result lists the
documents read and the figures saved, skipped, pending or refused. A failed search, page or model
call changes no published data.

## Sources

* DeepSeek Search and Fetch (`OSRIP_RESEARCH_PROVIDER=deepseek`, `OSRIP_RESEARCH_FETCH_PROVIDER=deepseek`):
  see AI_PROVIDERS.md. Official Omani hosts are read directly first, because DeepSeek Fetch timed
  out on them.
* NCSI news pages are drawn in the browser; their articles are read from NCSI's own API
  (`api.ncsi.gov.om/V1/news/view/{id}`), and the saved source keeps the page address.
* The NCSI Monthly Statistical Bulletin workbook remains the structured connector (source sync).
* data.gov.om's raw-data API (`POST /api/1.1/data/details`) refused every anonymous request
  (HTTP 403, data and metadata alike) on 2026-10-25; it needs portal credentials this deployment
  does not have, and the datasets its search returned date from 2016. It is not used.

## Year-to-date totals

Totals to different months (January to July, January to August) are different periods. The public
observations API shows each indicator's latest end month by default and lists the others
(`ytd_end_months_available`); `ytd_end_month` selects one. Values are never mixed.
