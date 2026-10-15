# Verification record

An empty cell is not a pass (booklet Appendix A). Each increment lists what was
actually executed, in which environment, and what was not.

## Release-candidate audit (2026-09-25)

Full record: [TEST_RESULTS.md](TEST_RESULTS.md). All checks pass after five fixes
(D1 phone overflow on Geography; D2/D3 lint findings; D4 mixed-frequency sections
unreadable and reports failing; D5 oversized change calculations). New evidence:
ESLint, a complete upload → publication → report → revision journey, quality checks
on desktop and phone (keyboard, focus, images, failed requests, negative numbers,
Arabic layout), a scripted performance workload and a passed backup-and-restore
exercise. Not run: Docker deployment, screen reader, axe, Firefox/Safari, usability study.

## Geographic exploration and forecast eligibility increment (2026-09-25)

Environment as below (PostgreSQL 17.11 local cluster, Python 3.13.5, Node 24.17,
Edge for Playwright). New dependencies: `maplibre-gl` 6.11.2 (BSD-3-Clause) and
`@mapbox/mapbox-gl-rtl-text` 0.4.0 (BSD-2-Clause) from npm.

### Registry completeness, checked against authoritative sources

| Source (accessed 2026-09-25) | States | Used for |
|---|---|---|
| Ministry of Finance, *Oman by Region*, English (page updated 2026-09-21) and Arabic (updated 2026-04-29) | 11 governorates, 61 wilayats, each wilayat's governorate | Names (EN, AR), existence, parents |
| Ministry of Interior statement, 2022-06-19 | Al Jabal Al Akhdar (A'Dakhiliya) and Sinaw (A'Sharqiyah North) are wilayats | Existence, Arabic names, parents of the two wilayats |
| Oman News Agency, 2022-11-16 | The two new wilayats raise the total to **63** | English names; the expected total |
| Wikipedia *ISO 3166-2:OM* (secondary; the ISO platform requires accepting its terms and was not consulted) | 11 governorate codes | `iso_3166_2` |

Result: 11 governorates and 61 + 2 = 63 wilayats seeded (migration 0005), each
with EN/AR names, parent, verification date and references naming what each one
supports. The completeness check is stored (`area_registry_verification`) and
compared live with the registry by `GET /areas`. No coordinates, centroids or
boundaries were created.

### Boundary sources evaluated (none adopted)

| Candidate | Finding | Decision |
|---|---|---|
| geoBoundaries OMN ADM1 | 2010, 7 units (predates the 11-governorate structure) | Rejected: outdated |
| geoBoundaries OMN ADM2 | 61 units (before 2022); licence "Other – Direct Permission" | Rejected: incomplete, redistribution unclear |
| HDX COD-AB Oman (OCHA) | 11 admin-1 units but 49 admin-2; listed as CC BY-IGO but "downloaded from www.gadm.org" | Rejected: wilayats do not match 63; GADM terms forbid redistribution, so the licence chain is unclear |
| GADM | Non-commercial, no redistribution | Rejected |

No boundary file was downloaded. The map is an orientation basemap
(OpenFreeMap vector tiles from OpenStreetMap, attribution shown); selection and
statistics use the registry table.

### Checks executed

| Check | How | Result |
|---|---|---|
| Registry: 11 ISO governorate codes; wilayats per governorate 4/3/6/6/6/3/9/7/5/4/10; the 2022 wilayats' names, parents and references; every entry sourced for existence, both names and parent; unique codes; OSRIP codes labelled not official; no coordinate or geometry fields | `tests/test_geography_forecast_integration.py` | Passed (expected values are literals from the sources) |
| Database: wilayat under the national area refused (hierarchy trigger); governorate without a verification date refused; verification record append-only; forecast predictions append-only | same | Passed |
| Statistical coverage: counts only observations recorded for the exact area (a governorate's data is not shown for its wilayats, nor national data for governorates); a missing value is counted as missing, not as a value; verified mode never shows synthetic coverage | same | Passed |
| Forecast eligibility (pure): 2 points → `insufficient_history`; missing, withheld, gaps, internal incomplete periods → ineligible; trailing year-to-date dropped with a note; synthetic → demonstration only | `tests/test_forecasting.py` | 16 passed |
| Forecast evaluation (pure): identical held-out dates for baseline and candidate; training ends before each target; expanding window; baseline predictions 120/126/125/131 and errors 6/−1/6/7 → MAE 5, RMSE √30.5 (worked by hand); candidate first fold = 851/7 (hand least squares); a linear series → candidate errors 0, baseline 2; changing a later value never changes earlier forecasts; stored error is exactly actual − predicted | same | Passed |
| Forecast runs (API): booklet fixture series ineligible; an analyst's request is recorded as **withheld** with the reason and no predictions (T10); a 12-year synthetic series runs, stores 8 predictions with errors, reproduces the numbers above, labels the run "software demonstration … not a validated forecast for Oman"; viewers and anonymous users cannot run; unknown series refused | `tests/test_geography_forecast_integration.py` | Passed |
| Whole backend suite | `OSRIP_RUN_DB_TESTS=1 pytest` | 166 passed |
| Migration 0005 up, down, up on the dev database | `alembic` | Clean |
| Lint and format | `ruff check`, `ruff format --check` | Passed |
| Full stack | `playwright test -c playwright.api.config.ts` | 17 passed. New: registry 11/63 and "Complete"; verified mode shows "0 of 75" and "No data" everywhere; the map-unavailable state appears while the table works; governorate filter + selection of Al Jabal Al Akhdar (sources, "not official" code, 2022 note, "missing data, not zero"), kept across a language switch; national area shows its synthetic values while Muscat shows "No data"; forecast unavailable in both modes with reasons and the synthetic label; analyst request on an ineligible series recorded as withheld |
| Mock-mode suite, type-check, production build | `playwright test`, `npm run build` | 15 passed (2 phone-only skipped by design); build OK. The map library is a separate lazily loaded chunk (1.06 MB, 286 kB gzip) |
| Live map in the in-app browser (EN, AR, 375 px) | Manual | Basemap loads with OpenFreeMap / OpenMapTiles / OpenStreetMap attribution; Arabic labels shaped by the RTL plugin; no horizontal overflow |

Bug found and fixed: Vite's dependency pre-bundling broke MapLibre's worker URL
(the page correctly fell back to "Map not available"); the worker is now built
by Vite and passed to `setWorkerUrl`.

### Forecast evaluation outcome

No eligible series exists. There are no verified-source observations, and the
synthetic fixtures have one or two periods per series. **Forecast unavailable**
is therefore the state in both modes. No forecast performance is claimed
(booklet Table 4.4: "Forecast performance — not measured").

### Not done

| Item | Status |
|---|---|
| Boundary geometry, choropleth, clicking areas on the map | No suitable licensed current dataset (see above). Needs a licensed file matching the 63 wilayats, and a decision by the team |
| Service areas (water) | None registered; they need their own sources |
| Seasonal naive baseline | Not implemented; relevant only once a monthly or quarterly series with several complete seasons exists |
| Prediction intervals | Deliberately none (method `none`, documented with each run) |
| Arabic review of new texts | Needs a qualified Arabic speaker |

## Calculations, review cards and reports increment (2026-09-25)

Environment as below (PostgreSQL 17.11 local cluster, Python 3.13.5, Node 24.17,
Edge for Playwright).

### Booklet Table 4.2 fixtures, verified independently

Each expected value is a literal from the booklet, asserted against the API
(`tests/test_analysis_integration.py`) and against the interface
(`frontend/e2e-api/analysis.spec.ts`). They are not recomputed with the
implementation's own formulas.

| Fixture | Expected | API result | Interface shows |
|---|---|---|---|
| Electricity generation 48,000 → 50,100 GWh | +2,100 GWh; 4.375% | `2100`; `4.375` (unrounded) | 2,100 GWh; 4.38% (= 4.375) |
| Water consumption 330 → 343 million m³ | +13; ≈ 3.94% | `13`; `3.939393…` | 3.94% |
| Apparent availability, production 100,000 t + imports 80,000 − domestic exports 20,000, stock change = 0 (declared) | 160,000 t | `160000` with caveat `stock_change_assumed_zero` | 160,000 tonne; formula states the assumption |
| Local production contribution | 62.5% | `62.5` + `not_complete_food_security_measure` | 62.5% |
| Gross import contribution | 50%, not complementary | `50` + `does_not_complement_production_ratio` and the note "62.5% + 50% = 112.5% … exports are not attributed to either ratio" | 50% with the explanation |
| Fictional partners A/B/C 48,000 / 20,000 / 12,000 t | 60 / 25 / 15%; largest 60% | `60`, `25`, `15`; sum of squared shares `0.445` | 60%, Partner A/B/C (fictional) |
| Import value OMR 40 m, export value OMR 12 m | balance −OMR 28 m, not profit | `-28000000` + `not_profit_or_loss`, `nominal_value` | −28,000,000 Omani rial (nominal) |
| Unit values | OMR 500 / 600 per tonne, not retail prices | `500`, `600` + `not_retail_price` | 500 and 600 Omani rial per tonne |

### Other checks executed

| Check | How | Result |
|---|---|---|
| Guards on published data: missing previous value → `missing` (not zero growth); previous value 0 → `undefined` (previous_value_zero); availability 0 → ratios `not_calculated` (non_positive_denominator); known-stock assumption without a published stock change → unavailable; use per subscriber only for the same area and period; annual and monthly series never compared; two sources for one component → withheld (`conflicting_sources`); filters narrow calculations; mode mismatch refused | `tests/test_analysis_integration.py` | 16 passed (fixtures and guards together) |
| Water: leakage not inferred; source composition not estimated; electricity generation never divided by subscribers | same | Passed (explained "unavailable" results) |
| Review rules R01–R04: cards carry observation, rule (code, version, threshold, eligibility, "not an official standard" note), inputs with versions, limitations and a next investigation; thresholds are run parameters; R04 on a missing input; `analysis.run` required | `tests/test_reviews_reports_integration.py` | Passed |
| Analyst review history: appended, latest review is the status, notes protected (401 anonymous, 403 viewer), invalid status or blank reason refused, the card's calculation is unchanged | same | Passed |
| Reports: frozen filters, assumptions, source versions, observations, calculations and cards; database refuses to alter a generated report; a revision published afterwards changes live results (205) but not the report (105); private reports return 404 to others; owner can publish; CSV keeps label, filters, assumption, versions and values (T07, T12) | same | Passed |
| Calculation CSV export keeps mode label, assumption and 160,000 (T12) | same | Passed |
| Whole backend suite, three consecutive runs, plus a reordered subset | `pytest` | 137 passed each run; reordered subset 44 passed |
| Migrations 0001 → 0004 up, down, up on an empty database | `alembic` | Clean |
| Lint | `ruff check` | Passed (line length is waived only for the bilingual text modules) |
| Full stack (browser → API → PostgreSQL) | `playwright test -c playwright.api.config.ts` | 12 passed: every section shows calculations with formula, inputs, versions and limitations; the stock filter changes the calculation and its export link together; the commodity filter narrows calculations, tables and export; an analyst runs rules, reviews a card (history and status update) and freezes a report whose print view shows label, assumption and version; a viewer has no run, review or report controls |
| Mock-mode interface suite (now on its own port, never reusing a developer server) | `playwright test` | 15 passed, 2 phone-only tests skipped on desktop by design |
| Visual check: food, trade (with cards), report screen and print media, Arabic RTL, 390 px | Screenshots | Fixed before this record: calculation cards full width (input tables were cramped); review form stacked; exports placed once per section. No horizontal overflow; no console errors |

Bugs found and fixed: a rule run failed when any published dataset mixed annual
and monthly data for one indicator (the analysis layer now keeps frequencies
apart itself); calculations could have merged series from different sources (now
per dataset version, with conflicts withheld); the mock test suite could silently
reuse a developer's API-mode server.

### Not done in this increment

| Item | Status |
|---|---|
| Water source composition | No source-type dimension exists in the schema or data; shown as unavailable with the reason, never estimated |
| Forecasting (FR07, T10) | Not started (done in the next increment above) |
| Arabic review of new texts | Drafted by the development team; needs a qualified Arabic speaker |
| Scheduled rule runs | Rules run on request by an analyst; cards come from the latest run only |
| PDF export | Reports are print-friendly HTML (browser "Save as PDF") and CSV |

## Data model and import-to-dashboard increment (2026-09-25)

Environment: Windows 11; Python 3.13.5 in `backend/.venv`; PostgreSQL 17.11
(official EDB Windows binaries, SHA-256 `B9424EE7…9AEA28`, run locally by
`backend/scripts/devdb.py` on localhost:55432 with SCRAM authentication);
Node 24.17.0; Microsoft Edge as the Playwright browser.

### Executed

| Check | How | Result |
|---|---|---|
| Migrations 0001 → 0003 through Alembic (first time the migrations ran through Alembic rather than raw psql) | `alembic upgrade head`, `downgrade base`, `upgrade head` on an empty database | Up, down, up all succeed. After `downgrade base`: 0 tables, 0 enum types, 0 functions left |
| Downgrade with data present | `downgrade base` on a database holding seeded observations | Refused by a foreign key and rolled back in full (no data lost). Intended: dropping 0003 would destroy published data |
| Database rules (now 33 checks: provenance incl. catalogue-page and reuse rules, frequency/period rules, mode and partner/commodity separation both ways, duplicate natural key, immutability, one published version, append-only audit and review history, password-hash format) | `db_checks/constraints_check.sql`, run by `tests/test_db_constraints.py` | 33 / 33 passed |
| Import validation rules (missing fields, missing value kept as null, number formats, negative values, incompatible and unknown units, commodity unit without conversion, date formats, period order, frequency spans, year-to-date, area identifiers and validity dates, duplicate keys (all occurrences rejected), commodity required, not applicable, withdrawn, unknown, synthetic-only, provisional, partner fictional/real by mode, partner sum above total (rejected), partial coverage and absent total (warnings), flow rules, column-mapping checks, CSV safety: format, encoding, binary, ragged rows, formula text) | `tests/test_import_validation.py`, no database | 42 passed |
| Import workflow through the HTTP API: upload → map → validate → error preview (row, original value, reason) → error CSV → explicit approval (acknowledgement must match) → publish → public read with provenance; rejected rows kept after publication | `tests/test_import_workflow_integration.py` | Passed |
| Repeated and concurrent publication (4 simultaneous requests) | same file | One set of observations; later requests report `already_published` |
| T05 revision: v2 supersedes v1, current query returns one snapshot, explicit v1 still readable | same file | Passed |
| T11 failure during publication (a database trigger raises on the second observation insert) | same file | 500 `publication_failed` with no internals; v1 still published and served; 0 observations of v2; failure recorded; retry after the cause is removed publishes normally |
| Mode separation in storage, queries and exports; version of one mode unreadable through the other; mixed frequencies refused; drafts not public | same file | Passed |
| Provenance: catalogue page refused for verified sources; incomplete verified provenance refused; publisher refused for synthetic sources | same file | Passed |
| Booklet synthetic fixtures seeded through the workflow (idempotent) and read back: 48,000 / 50,100 GWh; 330 / 343 million m³; fictional Partner A/B/C 48,000 / 20,000 / 12,000 t; no publisher | same file | Passed |
| T06 / SEC01: anonymous, viewer, analyst, data manager (with and without approve), administrator all denied publication; no data change; denials audited without secrets | `tests/test_auth_integration.py` | Passed |
| Sessions: HttpOnly + SameSite=Strict cookies, Secure by default; only SHA-256 token digests stored; Argon2id password hashes; identical answer for unknown account and wrong password; throttling after 5 failures (429) even with the right password; CSRF token required; suspended account loses access through an existing session (and reactivation does not revive it); revoked grant effective on the next request; logout revokes; service accounts cannot sign in | same file | Passed |
| Whole backend suite | `OSRIP_RUN_DB_TESTS=1 pytest` | 110 passed on the final run (109 on each of three consecutive earlier runs, before the startup-settings test was added) |
| Unsafe production settings refused at startup (development client-hash key, non-Secure cookies) | `tests/test_api_foundation.py` | Passed |
| Lint | `ruff check app tests scripts` | All checks passed |
| Full stack: browser → Vite proxy → FastAPI → PostgreSQL | `PW_CHANNEL=msedge npx playwright test -c playwright.api.config.ts` | 5 passed: the published synthetic fixture is fetched from `GET /observations` and displayed (48,000 / 50,100, source dialog shows the synthetic source and no publisher); verified mode shows no data instead of falling back; Arabic shows the same values; a data manager completes register → upload → validate → review → approve → publish in the UI and the value appears on the dashboard; a viewer's hand-made API request (valid session + CSRF) is refused with 403 |
| Frontend mock-mode suite (unchanged behaviour) and type-check/build | `npx playwright test`, `npm run build` | 15 passed, 2 phone-only tests skipped on desktop by design; build OK |
| Visual check of sign-in and Data Management (EN, AR/RTL, 390 px) | Screenshots | Fixed before this record: mapping collapses after validation; error preview stacks on phones; Arabic label font |

Bugs found and fixed during this increment: migrations failed under Alembic
(psycopg read `%` in PL/pgSQL `RAISE` as placeholders; now executed verbatim);
`JSONB` stored Python `None` as JSON `null`, breaking the "rejected ⇔ no
normalized row" rule (`none_as_null=True`); new role rows were not visible to the
same request (no autoflush); row-level append-only triggers did not fire on an
empty `DELETE`/`TRUNCATE` (now statement-level).

### Not done

| Item | Status |
|---|---|
| Endpoints for analysis runs, recommendations and review history, and report generation | Schema, constraints and append-only rules only; no API yet (next increments, booklet Table 3.5) |
| Password change and reset, account self-service | Not implemented; administrators create accounts (`/admin/users` or `python -m app.cli create-user`) |
| Rate limiting of endpoints other than sign-in | Not implemented |
| Validation messages in Arabic | API messages are English only (marked `lang="en"` in the interface) |
| Backup and restore exercise (booklet 3.15) | Not run |
| Performance measurement | Not run; no latency claim is made |
| HTTPS deployment | Not set up; cookies are `Secure` by default, and only local plain-HTTP runs disable that |
| Any verified-source data | None loaded. Only the booklet's synthetic fixtures are seeded |

## Visual identity increment (2026-09-25)

Environment: Windows 11, Node 24.17.0 (bundled with Visual Studio), npm registry
reachable, Microsoft Edge used as the Playwright browser (`PW_CHANNEL=msedge`).
`npm install` ran and created `frontend/package-lock.json`; commit it.

| Check | How | Result |
|---|---|---|
| Strict type-check of the whole frontend (React, React Router 8, TanStack Query, react-i18next types) | `tsc -b` | 0 errors |
| Production build | `npm run build` | Built. Warning: one JS chunk is 601 kB before gzip (no code-splitting yet) |
| Colour-token contrast, light and dark | `npm run check:contrast` | 54 / 54 pairs pass |
| End-to-end: landing credits, verified default, synthetic labelling, T08 language switch (route, mode, **filters** and values kept), empty state and reset, mode-only navigation persistence, energy redirect, overview filter, source dialog (Escape, focus return), skip link, restricted Data Management, `/methodology` redirect, mobile drawer, mobile filter toggle, no horizontal scroll | `PW_CHANNEL=msedge npx playwright test --repeat-each=3` | 45 passed, 0 failed (6 mobile-only tests skipped on the desktop project, by design) |
| Visual inspection: landing, overview, electricity, trade, sources, data management, interface reference; EN and AR; light and dark; 390, 1024, 1280 and 1440 px | Screenshots via Playwright + Edge | No horizontal overflow and no console errors. The layout problems found were fixed before this record. |
| Keyboard focus and reduced motion | Tab-order script with `reducedMotion: 'reduce'` | Skip link is first; focus ring visible on light and green surfaces; transitions off |

Bugs found and fixed during verification: rapid successive filter changes lost
earlier values (React Router functional updater). Fixed with
`state/useUpdateSearch.ts`. StrictMode's double effect run moved focus to `<main>`
on first load. Fixed by tracking the handled location.

Not done: an Arabic language review by a qualified speaker; screen-reader
testing (NVDA/VoiceOver); a Lighthouse or axe audit; backend changes (none were
made).

## Foundation increment (0.1.0)

Date: 2026-09-24. Environment: cloud sandbox, Node 22.22.2, TypeScript 6.0.3,
Python 3.11.15, PostgreSQL 16.13. **The npm and PyPI registries were blocked (HTTP 403)
in this environment**, so no project dependency could be installed. An empty cell is
not a pass (booklet Appendix A).

## Executed here

| Check | How | Result |
|---|---|---|
| Booklet Table 4.2 arithmetic + guards T01, T02, T03, T09, T12 (23 tests) | `backend/tests/test_calculations.py` executed by a stand-in runner that calls each `test_*` function (pytest unavailable) | 23 passed, 0 failed |
| Migrations 0001–0002 apply on PostgreSQL 16 | SQL files executed with `psql -v ON_ERROR_STOP=1` | Applied |
| DB integrity rules (20 checks: mode inheritance, synthetic ⇒ no publisher, T03 unit dimension, T04 duplicate natural key with NULL dimensions, T05 one published version, published immutability, fictional-partner rule, commodity review gate, …) | `backend/db_checks/constraints_check.sql` | 20 / 20 passed |
| Down migrations | 0002 down then 0001 down | Reference rows removed; 0 tables and 0 enum types remain |
| Backend Python syntax; `Settings` and Pydantic schemas load | `compileall`; import with installed pydantic / pydantic-settings | OK |
| Frontend: every `.ts`/`.tsx` parses and transforms (43 files) | esbuild transform | 0 failures |
| Frontend strict type-check of framework-free modules (domain types, sections, adapter interface, mock adapter, synthetic fixtures, formatting, both locales, language helpers) | `tsc` 6.0.3 with the app's strict tsconfig | 0 errors |
| English/Arabic locale key parity is enforced by the compiler | Removed one Arabic key in a copy → `tsc` error TS2741 | Guard works |
| Mock adapter behaviour | Executed with `tsx` | Verified mode → `no_published_data` (no synthetic fallback); synthetic electricity = `48000, 50100`; all synthetic series have `publisher = null` |
| Arabic number formatting | Node ICU: `ar-OM-u-nu-latn` vs `en-GB` | Both render `48,000.13` |

## NOT executed (requires `npm install` / `pip install`)

| Item | Status |
|---|---|
| `npm run build`, `vite` dev server, rendering of the React shell | Not run |
| Type-checking of React components against real React, React Router 8, TanStack Query, react-i18next, zod types | Not run |
| Playwright e2e (`frontend/e2e/shell.spec.ts`, incl. T08 language switch) | Written, not run |
| FastAPI app start, `/api/v1/health`, `/api/v1/indicators` | Written, not run |
| `pytest` itself, `tests/test_api_foundation.py` | Not run |
| Alembic `upgrade head` through SQLAlchemy/psycopg; `alembic check` model–migration parity | Not run (SQL itself was verified directly) |
| Lockfiles (`package-lock.json`, `uv.lock`) | **Not generated** — must be created on first install and committed |
| Authentication, authorization, imports, reports, recommendations, forecasting | Not implemented |
