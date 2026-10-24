# OSRIP: academic evaluation

Oman Smart Resource Intelligence Platform (OSRIP) is an academic prototype, not an official
statistics service. This document states what the prototype is meant to do, how it was built,
how it was checked, and what was measured on 23–24 October 2026. Every number below comes from
a run that can be repeated with the commands in §8. **No user study was carried out:** there are
no participants, questionnaires or satisfaction scores, and none are reported.

## 1. Problem

Figures on Oman's electricity, water, food security and trade are published by the National
Centre for Statistics and Information (NCSI) and ministries in bulletins, yearbooks, data
portals and statements: PDFs and spreadsheets with different frequencies (month, year,
year-to-date), provisional and revised values, and regional breakdowns that do not always add
up to the national figure. A reader who wants "electricity generation from June to August 2026"
must find the right table, keep months apart from year-to-date totals, notice revisions, and
avoid treating a missing month as zero. General-purpose AI assistants make this worse when they
state numbers without a source or compute them loosely.

## 2. Objectives and how each is measured

| # | Objective | Measure | Result (§9) |
|---|---|---|---|
| O1 | Every figure shown is traceable to a published source | Published figures with a source address; cited sources with an https address that answers | Every published figure of the 105 series has a source (105 of 105 series); 5 of 5 cited sources https and HTTP 200 |
| O2 | Calculations are correct and reproducible | Independent recomputation of every summary figure (counts, first/last, change, highest/lowest, totals) for every published series | 1338 of 1338 checks passed (including the source checks of O1) |
| O3 | Missing data are never shown as zero, and periods are never mixed | Checks in the same run; the missing-data step of the scenario | No missing period with a value; 2026 shown "Not published", year-to-date apart |
| O4 | Downloads equal what is on screen | CSV compared with the table for every series | 105 of 105 equal |
| O5 | The AI assistant answers only from cited evidence for the reader's selection | Integration tests; the scenario's analysis step | Selection-only figures cited (scripted model); live providers not verified (§7) |
| O6 | A reader completes the analysis task: sector → period → table → chart → sourced analysis → references → missing data | Automated scenario, each step asserted | 7 of 7 steps completed in each of 2 runs |
| O7 | Responses are fast enough for interactive use on a laptop | API timings (n = 105 per request kind); scenario step timings | Timeline median 29.3 ms, 95th percentile 43.7 ms |
| O8 | Arabic and English, right-to-left layout | Scenario screenshot in Arabic; full-stack tests in both languages | Passed (§8) |

## 3. Architecture

```
Browser: React 19 + TypeScript (Vite), i18next (en, ar, RTL), TanStack Query, zod validation
   │  /api/v1 (same origin; keys never reach the browser)
API: FastAPI (Python 3.12+)
   ├─ domain/      pure Decimal calculations: timeline, change, totals, units, comparability
   ├─ services/    observations, timeline + summary, imports and validation, reports,
   │               assistant (tools, evidence ledger, number check), providers, speech
   └─ services/sync/  NCSI listing + workbook reader, delta comparison (run by the worker)
Worker: python -m app.worker   scheduled checks of official feeds (advisory lock per feed)
PostgreSQL 15+: sources, dataset versions, observations, imports, audit, assistant, feeds
External (optional, by configuration only): Gemini / DeepSeek / Anthropic / OpenAI (answers),
   Brave or provider search, Firecrawl, Azure AI Speech
```

Rules that shape the design:

* **Calculations live on the server** (`backend/app/domain/`) as pure functions on `Decimal`;
  the interface and the AI never re-implement them.
* **The AI is a reader of tools, not a source.** It calls the platform's data tools; each result
  enters an evidence ledger with an id (`E1`, `E2`, …); a reply is accepted only if every
  number in it appears in the evidence its markers cite.
* **Official updates are staged, not trusted blindly.** The sync worker turns a new release into
  an ordinary import that is validated and, by default, waits for a data manager's approval.

## 4. Data mapping and provenance

### 4.1 Reference pack (verified-source mode)

`backend/fixtures/reference/oman_reference_pack_2026-09-27.json`: **346 records** checked to
27 September 2026, from 8 registered sources (5 cited by records, 3 used in reconciliation
notes), with 9 documented notes (conflicts, revisions, limitations).

| Sector | Records | Main source |
|---|---|---|
| Food security | 109 | Statistical Year Book 2026 (S02); ministerial statements (S04, S05) |
| Trade | 108 | Monthly Statistical Bulletin, September 2026 (S01); Year Book (S02) |
| Electricity | 99 | S01 (months, governorates, year-to-date); S02 (years) |
| Water | 30 | S01; NCSI data portal (S03) |

Each record keeps: indicator code, area code, frequency, period start and end, whether the
period is complete, the value as published (with an operator such as "<" where given), the unit,
the source id with page or table locator, and the revision status (reported, provisional,
preliminary). Example: `OM-0001`, gross generation, Oman, 2022, 42,510.6 GWh, S02 p. 131.

### 4.2 NCSI Monthly Statistical Bulletin (live feed)

| Bulletin table | OSRIP indicator | Unit | Areas |
|---|---|---|---|
| 21, gross production | `ELEC_GROSS_GENERATION` | GWh | Oman, Muscat, Dhofar, Musandam, Al Wusta, Batinah + Dhahirah, Sharqiyah, other |
| 21, net production | `ELEC_NET_GENERATION` | GWh | as above |
| 22, water production | `WATER_PRODUCTION` | thousand m³ | Oman, Muscat, Dhofar, other |

Footnote marks are read as revision status (⁽¹⁾ provisional, ⁽²⁾ preliminary). Values are read
as the workbook displays them (the cell's number format), so a figure is the one printed in the
bulletin, not a longer floating-point value. Regional rows are checked against the national
total (0.5 % tolerance) before anything is staged.

## 5. Update and validation methodology

1. An administrator switches a feed on (off by default) and chooses its interval (24 h default;
   at least 6 h).
2. The worker reads the NCSI publications list over HTTPS (allowed hosts only, size limits,
   up to three attempts with exponential backoff, `Retry-After` respected up to 60 s).
3. A new release's workbook is downloaded once (its SHA-256 identifies it) and parsed by a
   standard-library reader that refuses XML document types and entities.
4. Each figure is compared with the published figure for the same indicator, area, period,
   completeness and unit, at the precision both give: **new**, **revised** or **unchanged**.
5. New and revised figures become one import with its own source record, validated row by row;
   rejected rows are kept with reasons. A data manager approves and publishes; automatic
   publication is an explicit per-feed option, and even then only for an import without rejected
   rows.
6. Earlier releases stay published; where two releases give the same period, the newer figure
   is shown and the other is listed with the row as a revision.
7. Each check is logged (outcome, counts, error category). Failures back off (1 h, 2 h, 4 h, …,
   up to the interval) and never change published data.

**Live check, 23 October 2026** (development database): list HTTP 200; the October 2026 bulletin
workbook (2,048,496 bytes) gave 132 figures; 104 new, 22 unchanged and **6 revisions** by NCSI of
its own preliminary July and August 2026 national figures (for example August gross generation
5,743.9 → 5,745.6 GWh). The 110 figures were staged for approval; nothing was published by the
check. The NCSI data portal API (`data.gov.om`) answered HTTP 403: it needs access that this
project does not have.

## 6. AI grounding and calculation methodology

* **Deterministic numbers.** Tables, summaries (latest, change, highest, lowest, totals) and
  sector calculations are computed by the server. A total is given only for a flow
  (`period_total`) with every period in the range published and exact. Values of different
  frequencies are never mixed; annual totals are never split into months; averages are never
  derived from totals.
* **Grounded answers.** The model sees tool results (published observations with ids, OSRIP
  calculations, definitions), never the database. Every number in a reply must appear in the
  cited evidence; otherwise the reply is withheld as unverified and the evidence is shown
  instead.
* **The reader's selection.** "Request analysis" sends the applied sector, indicator, area,
  frequency and period, validated as codes and dates, as one instruction: answer for exactly
  that selection, and name any other period as an additional comparison period.
* **When the AI is unavailable** (no key, wrong key, limit, timeout): a labelled data-based report
  with the same cited figures and no interpretation; a guest is not charged.
* **Providers.** Gemini (free tier available per Google's pricing page, updated 22 October 2026;
  limits per account; free-tier content may be used to improve Google's products) is the
  recommended setup; DeepSeek (usage-billed, no free tier) runs only with an explicit billing
  acknowledgement. One retry on transient errors; a provider's `Retry-After` up to 10 s is
  waited once.
* **Speech.** Azure AI Speech with Omani Arabic voices `ar-OM-AbdullahNeural` (Al Mulhim) and
  `ar-OM-AyshaNeural` (Ilham). The spoken explanation is a few sentences from the summary, with
  numbers rounded for listening; the table and transcript keep exact figures. Nothing plays
  without a click.

## 7. Limitations and unconfigured features

| Area | Status |
|---|---|
| Live AI answers (Gemini, DeepSeek, Anthropic, OpenAI) | **Not verified.** The configured Anthropic key fails authentication; no Gemini or DeepSeek key is set. Request formats, parsing, retries and error handling are tested against recorded or mocked responses only. The scenario's analysis step uses the scripted test model. |
| Azure speech synthesis | **Not verified.** No Azure key on this machine; the controls and voice mapping were tested with a scripted test tone. |
| Web search (Brave), Firecrawl | Not verified live (wrong or missing keys). |
| NCSI feed over time | One live check verified; scheduled checks over days not observed. |
| NCSI data portal | Needs access (HTTP 403). |
| Coverage | Reference pack to 27 Sept 2026 plus the staged October bulletin; no quarterly electricity; few governorate series. |
| Concurrency | Timings are single-user on one laptop; no load test in this round. |
| Users | No user study; task completion was measured with an automated script, not people. |
| Status | Academic prototype; not an official NCSI or government product. |

## 8. Reproducible tests and results

Environment: Windows 11 laptop, PostgreSQL 17.11 development cluster (port 55432), Python 3.13.5,
Node 24.21, Microsoft Edge (`PW_CHANNEL=msedge`). Integration and browser tests create throwaway
databases.

| Check | Command (from) | Result, 23–24 Oct 2026 |
|---|---|---|
| Backend unit + integration tests | `$env:OSRIP_RUN_DB_TESTS="1"; $env:OSRIP_TEST_ADMIN_URL=(python scripts\devdb.py url); pytest` (backend) | 724 passed (1 min 43 s) |
| Full-stack browser suite, desktop + Pixel 7 | `npx playwright test -c playwright.api.config.ts` (frontend) | 149 passed, 1 skipped, 0 failed (14.9 min) |
| Demonstrations and evaluation scenario | `npx playwright test -c playwright.demo.config.ts` (frontend) | 7 of 7 passed |
| Measurements (§9) | `python tools\evaluate_osrip.py --api http://127.0.0.1:8010/api/v1 --out docs\evaluation --check-links` (root) | `docs/evaluation/measurements-2026-10-23.{md,json}` |
| Selection reaches the tools | `tests/test_assistant_selection_integration.py` | 3 passed: the rule is in the prompt; malformed selections refused (422) before any provider call; only periods inside the selection are cited |
| Official feed | `tests/test_source_sync.py`, `tests/test_zzz_source_sync_integration.py`, `e2e-api/source-feeds.spec.ts` | 9 + 3 + 3 passed |
| DeepSeek and Retry-After | `tests/test_ai_providers_deepseek.py` | 7 passed (mocked transport) |
| Spoken explanation | `tests/test_series_speech.py`, `e2e-api/sector-voice.spec.ts` | 4 + 1 passed (scripted speech) |

## 9. Demonstration scenario and measured outcomes

### 9.1 Scenario (test 9 of `frontend/e2e-demo/integrated.demo.spec.ts`)

Real API and database with the reference pack published; the scripted test model in place of
a live AI provider. Screenshots in `docs/evidence/integrated/`.

| Step | What is asserted | Screenshot |
|---|---|---|
| Choose electricity | The form is shown; no results before *Show results* | — |
| Select an available period | Gross generation · Oman · Monthly · Jun–Aug 2026, chosen from the published months offered | `20-scenario-period-chosen.png` |
| View table | 3 rows in time order: 5,755.4, 5,676.9, 5,743.9 GWh; latest 5,743.9; total 17,176.2 (a flow, every month published); no chart yet | `21-scenario-table.png` |
| Request chart | Chart appears only after *Show chart* | `22-scenario-chart-on-request.png` |
| Ask for sourced analysis | The selection chip is shown; the reply is answered, labelled AI-generated, with exactly the 3 months cited to the Monthly Statistical Bulletin, September 2026 | `23-scenario-sourced-analysis.png` |
| Inspect references | A citation chip moves focus to its evidence; the source link is `https://api.ncsi.gov.om/uploads/…` | `24-scenario-reference-inspected.png` |
| Missing-data case | Annual 2022–2026: 2026 row "Not published" (never 0), January–August 2026 (37,481.8 GWh) shown apart, no total over the gap; quarterly: no periods offered | `25-scenario-missing-year.png`, `26-scenario-no-quarterly-figures.png` |
| Arabic | The same results right to left | `27-scenario-arabic.png` |

### 9.2 Measured outcomes

**Calculation correctness** (`tools/evaluate_osrip.py`, 23 Oct 2026 21:00 UTC, verified-source
data): 105 series (every indicator × area × breakdown × frequency the availability lists), full
published range each; **1338 of 1338** independent checks passed (time order, missing never
zero, a source address for every published figure, counts, first and last, absolute and
percent change, highest, lowest, total only when additive and complete). **CSV equal to the
table: 105 of 105.**

**Citation validity:** 5 distinct sources cited by the rows; 5 of 5 https; 3 on the statistics
office (ncsi.gov.om, data.gov.om), 1 government (`.gov.om`), 1 other publisher (a news report,
marked secondary in the registry); **5 of 5 answered HTTP 200**. In the scenario, every figure in
the AI reply was backed by a cited observation (3 of 3).

**Task completion:** the scenario's 7 steps completed in 2 of 2 automated runs. This shows the
interface supports the task end to end; it is not a measure of how people perform.

**Response time** (same machine, single user):

| API request | n | Median (ms) | 95th percentile (ms) | Max (ms) |
|---|---|---|---|---|
| availability | 4 | 61.5 | 108.2 | 108.2 |
| timeline | 105 | 29.3 | 43.7 | 51.6 |
| CSV | 105 | 31.5 | 43.5 | 48.1 |

| Scenario step (browser, Vite development server) | Run 1 (ms) | Run 2 (ms) |
|---|---|---|
| Open electricity | 1,276 | 1,381 |
| Choose a published period | 411 | 406 |
| Show results (table) | 570 | 493 |
| Show chart | 229 | 169 |
| Ask for a sourced analysis (scripted model) | 873 | 1,750 |
| Inspect a reference | 163 | 119 |
| Missing-data case (navigate, choose, show) | 1,862 | 2,032 |

Run 2 is in `docs/evidence/integrated/scenario-timings.json`. Step times include the test
driver's own actions. The analysis step does not include a live model's response time, which
would usually be much longer and depends on the provider.

## 10. Conclusions within these limits

For the published data loaded, the platform's tables, summaries and downloads were correct in
every check made. Every figure was traceable to a reachable source. Missing periods and
year-to-date totals were handled as specified. The official-update path worked once against the
live NCSI site and caught NCSI's own revisions without publishing them silently. What remains
unproven is the quality of live AI answers and synthesized Arabic speech: both need credentials
that were not available. A study with real users would be needed before any claim about
usability.
