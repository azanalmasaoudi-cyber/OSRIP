# Implementation notes for updating the booklet

The booklet is a design-stage document: it describes proposals and planned tests.
This file lists, section by section, what was actually implemented and measured, so
the booklet can be revised from evidence rather than from intentions. Each item
names its evidence. Wording is suggested, not prescribed. Measured values are from
2026-09-25 on a laptop (TEST_RESULTS.md) and must not be generalised.

## Chapter 1 — Introduction and scope

* §1.3 Objective 3 ("one evaluated forecasting model"): the forecasting feature is
  implemented, but **no series is eligible**, so no model has been evaluated on data.
  Suggested wording: "a forecasting experiment, run only for an eligible series; with
  the data available at submission, the forecast was withheld with reasons."
* §1.4 Commodities: wheat, rice and tomatoes remain provisional demonstration choices
  (no product form or HS codes confirmed, SPEC_CONFLICTS C14).

## Chapter 2 — Background

* §2.4 Forecast evaluation is implemented as written: last-value baseline; candidate
  least-squares linear trend; rolling origin with an expanding window; one step
  ahead; transformations fitted inside each training window; identical held-out
  dates; individual predictions and errors stored; MAE and RMSE in the indicator's
  unit, never as accuracy. A seasonal baseline was **not** implemented (no series
  has several complete seasons). No prediction interval is produced, by design.
  Evidence: `backend/app/domain/forecasting.py`, `tests/test_forecasting.py`.
* Minimum history is not stated in the booklet; the implementation uses annual 8 + 4,
  quarterly 12 + 4, monthly 24 + 12 (training + held out) as project assumptions
  (C10). The booklet should state and justify its own values.

## Chapter 3 — Design (now implementation)

* §3.2–3.4 Sources and modes: implemented. A verified source must name a direct
  file or statistical table; a catalogue page is refused by the API and the database
  (C16). Synthetic sources cannot have a publisher. Modes are separated with
  composite foreign keys.
* §3.3 Import: implemented as upload → map → validate → error preview → approve →
  publish. Approval must acknowledge the number of rejected rows. Publication is one
  transaction and idempotent (tested with four concurrent requests). A failure during
  publication keeps the previous snapshot (T11).
* §3.5–3.8 Calculations: implemented with Table 3.1 guards. One deviation found in
  the audit: change calculations now cover **the latest pair of periods within the
  selected years** (earlier pairs via the year filter), because computing every
  consecutive pair produced 29 MB responses for 63 monthly series.
* §3.9 Requirements and roles: implemented. Publication and approval are explicit
  per-user grants that no role implies (C6). The "authorized reviewer" of Table 3.5
  is the analyst role (C5).
* §3.9 Performance target: the two-second cached-read target was tested (below); it
  is **not** demonstrated under concurrency. There is no application cache.
* §3.10 Architecture: the analysis worker runs in the API process (allowed by §3.10);
  there is no job queue. External refresh jobs do not exist (sources are uploaded).
* §3.11 Schema: implemented in migrations 0001–0005. The `forecasts` entity is
  `analysis_run` (kind `forecast`, definition in `parameters`) plus
  `forecast_prediction` (append-only). Areas now carry a sourced registry: 11
  governorates (ISO 3166-2 codes) and 63 wilayats (OSRIP codes), with references and
  a stored completeness check; no geometry.
* §3.12 API: implemented and documented (`docs/API.md`, `docs/api/openapi.json`, 41
  paths). Additional routes beyond Table 3.5: sources, import mapping/rows/errors,
  rejection, admin, areas, coverage, forecast eligibility and runs, exports.
  A read that mixes frequencies returns `422 incompatible_series`; the interface reads
  each period kind separately and lists the kinds apart, or the reader chooses one
  frequency (audit defect D4).
* §3.13 Rules: R01–R04 implemented; thresholds (3 %, 50 %, 10 %) are run parameters
  shown as "not an official standard" (C22). Reviews are append-only (database
  trigger).
* §3.14 Interface and maps: implemented bilingual interface with the same query
  state in both languages (Latin digits in both, C9). The optional map is an
  orientation basemap (MapLibre GL JS, OpenFreeMap / OpenStreetMap tiles with
  attribution) with **no data layer**, because no licensed current boundary dataset
  matching the 63 wilayats was found (geoBoundaries outdated or incomplete; HDX
  COD-AB has 49 admin-2 units derived from GADM). The accessible table is the
  selection mechanism; areas without data read "No data". Navigation gained
  Geography and Forecast experiment pages.
* §3.15 Security: Argon2id passwords; server-side sessions (HttpOnly, SameSite=Strict,
  Secure) with only token digests stored; CSRF tokens; login throttling; audit log
  without secrets; parameterised queries; upload limits. Not implemented: password
  reset, rate limits beyond sign-in. The backup exercise was performed (below).

## Chapter 4 — Evaluation (replace planned status with results)

* §4.2–4.4 Worked examples: every Table 4.2 value is reproduced by the software and
  asserted independently at the API and in the interface (4.375 % stored, 4.38 %
  shown; 3.939393… %; 160,000 t; 62.5 %; 50 %; 60 %; −OMR 28 m; OMR 500 and 600 per
  tonne).
* §4.5 Table 4.3: T01–T12 all executed and passed on 2026-09-25 (TRACEABILITY.md).
  Totals for the audit run: 168 backend tests, 31 full-stack browser tests (desktop
  and phone), 15 mock-mode browser tests (2 phone-only skipped on desktop), lint,
  type-check, build and contrast checks. Five defects were found and fixed (D1–D5).
* §4.6 Model evaluation: **not performed on real data**; T10 (withheld with reason)
  passes. The engine was verified against hand-computed values on synthetic series,
  which demonstrates software behaviour only.
* §4.6 Usability evaluation: **not conducted** (clearance not yet obtained).
* §4.7 Performance, measured with the documented workload
  (`backend/scripts/perf_workload.py`): laptop (i7-1355U, 15.7 GB, Windows 11),
  uvicorn with one worker, PostgreSQL on the same machine, 7,572 observations.
  Sequential warm reads: p95 between 1.8 ms (health) and 542 ms (63 monthly series).
  10 concurrent clients: median 320 ms, p95 4,687 ms, 7.4 requests/s, 0 errors.
  Import of 7,560 rows: validate 593 ms, publish 1,739 ms. Report generation: median
  935 ms. Suggested wording: "The two-second target was met for single-client reads
  in the test environment but not under ten concurrent clients with one server
  process; production measurements remain to be made."
* §4.7 Reproducibility: code version cannot be recorded as a commit hash (no git
  repository yet); input snapshots have SHA-256 checksums; parameters are stored
  with each run; outputs (reports, runs, predictions) are saved and immutable.
* Table 4.4 Evidence status, suggested update: Scope — supervisor confirmation still
  needed; Schema and architecture — implemented and tested; Synthetic arithmetic —
  executed against application outputs; Official commodity extract — not secured;
  Application deployment — configuration prepared, not deployed; Forecast
  performance — not measurable (no eligible series); Usability study — not
  conducted; Security and performance — tested locally (TEST_RESULTS.md).
* §3.15 Backup: performed on 2026-09-25. `pg_dump` of the development database
  (30 tables, 351 rows) restored into a separate new database; migration version,
  every table's row count and the MD5 of every published version's observations
  were identical; the application read the known fixture from the restored copy;
  integrity triggers still active. Backup 0.36 s, restore 0.66 s. Limits: one
  machine, small database, no schedule or off-site copy.

## Appendix updates

* Appendix A: replace the planned verification column with the implemented tests
  from TRACEABILITY.md.
* Appendix B: all listed validation rules are implemented; duplicates are resolved
  by rejecting every row sharing a natural key (C17).
* Appendix C risk "Insufficient time series" occurred: the response "use descriptive
  analysis or baseline" was applied (forecast withheld, descriptive calculations shown).

## Increment 0.5.0 (2026-09-26): beyond the booklet's design

These features come from later build briefs, not the booklet. If they are kept, the booklet needs new sections.

* **Accounts (§3.9, §3.15):**
  - Self-registration with e-mail confirmation.
  - Password recovery and single-use magic links, stored as digests with expiry.
  - Google and Microsoft sign-in (OpenID Connect with PKCE, state, nonce and ID-token checks). There is no automatic account merge; linking requires a signed-in session.
  - New accounts get the Viewer role only; administrators grant roles on a Users page.
  - Tested against a scripted provider only (see TEST_RESULTS).
* **Assistant (new):**
  - Claude via the Anthropic Messages API, server side.
  - Read-only tools inside a READ ONLY database transaction.
  - Arithmetic is done by the platform's domain functions.
  - Every number in a reply must match cited evidence, or the reply is withheld.
  - Tested with a scripted model and a mocked HTTP API; not against the live service.
  - The booklet should describe the privacy implication: questions and retrieved statistics are sent to the model provider.
* **Statistical scope:**
  - Verified-source statistics start in January 2022 (import rule).
  - NCSI data could not be downloaded without a portal account. A conversion tool with exact region spellings is ready; verified mode shows "Data unavailable" until files are imported.
* **Landing page:** an original, labelled SVG portrait illustration, not a photograph. It still needs cultural review.
