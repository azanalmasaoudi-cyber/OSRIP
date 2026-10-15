# Requirements register

**Origin.** The audit brief referred to `docs/requirements.md`, which did not exist in
the repository. This register was therefore compiled on 2026-09-25 from the project
booklet (*OSRIP Academic Booklet (English)*, design-stage edition): §3.9 and Table 3.2
(functional requirements), §3.12 and Table 3.5 (API contract), §3.13 and Table 3.6
(rules), §3.14 (interface), §3.15 (security), §4.5–4.7 and Table 4.3 (acceptance
tests), Appendix A (traceability) and Appendix B (import validation). Items marked
**Brief** come from the build briefs given to the development team, not the booklet.
Test evidence for each item is in [TRACEABILITY.md](TRACEABILITY.md).

Status: **Met** = implemented and passing its tests; **Partly met** = implemented
with a stated gap; **Not met** = not implemented or not evidenced; **Conditional** =
the booklet makes it depend on data that does not exist yet.

## Functional requirements (booklet Table 3.2)

| ID | Requirement | Acceptance evidence (booklet) | Status |
|---|---|---|---|
| FR01 | Import and validate a dataset | Invalid rows recorded; no silent deletion | Met |
| FR02 | Publish a version | Approved snapshot visible; previous version preserved | Met |
| FR03 | Explore indicators | Filters, units, period and source match | Met |
| FR04 | Compare compatible records | Invalid comparison rejected | Met (comparison views across dataset versions beyond per-series changes are not built) |
| FR05 | Generate a report | Input versions and data mode retained | Met |
| FR06 | Explain a recommendation | Rule, values and next steps visible | Met |
| FR07 | Evaluate a forecast | Baseline and candidate share test dates | Conditional: engine built and tested; no eligible series exists, so the state is "Forecast unavailable" |
| SEC01 | Authorize protected actions | Denied requests leave data unchanged | Met |
| UX01 | Switch language | Filters and numeric values preserved | Met |

## Non-functional requirements (booklet §3.9, §3.14, §3.15, §4.7)

| ID | Requirement | Status |
|---|---|---|
| NFR01 | No unauthorized write succeeds in the permission tests | Met |
| NFR02 | Missing data keeps its status through display and export | Met |
| NFR03 | English and Arabic show the same underlying values | Met |
| NFR04 | Proposed cached-read target of 2 s, tested in a documented environment | Partly met: measured and documented; single-client warm reads p95 < 0.6 s, but 10 concurrent clients on one worker p95 4.7 s. Target not demonstrated in general (see TEST_RESULTS.md) |
| NFR05 | Passwords hashed with a password-hashing library | Met (Argon2id) |
| NFR06 | Secrets outside source code | Met (environment variables; `.env` ignored; examples contain placeholders only) |
| NFR07 | Every protected request authorized on the server | Met |
| NFR08 | Request limits on login | Met (5 failures per 15 min). Other endpoints: not rate limited |
| NFR09 | Parameterized queries through the data layer | Met (SQLAlchemy; raw SQL only in reviewed migrations and test/ops scripts on catalogue names) |
| NFR10 | Uploads limited in size and format, schema checked, never executed | Met (5 MB, CSV only, formula text neutralised in exports) |
| NFR11 | Report downloads permission checked | Met |
| NFR12 | Logs exclude passwords, tokens and unnecessary personal data | Met (audit metadata filter; client addresses stored only as keyed hashes) |
| NFR13 | A backup exercise restores a known dataset version into a separate environment before recovery is called verified | Met on one machine (see TEST_RESULTS.md); scheduled and off-site backups not set up |
| NFR14 | External source failures do not make the dashboard unusable; published snapshots stay readable | Met for the interface (failed-request tests). No automatic external refresh exists, so refresh-failure jobs are not applicable |
| NFR15 | Tables as accessible alternatives to charts; specific messages for missing data, loading, validation failure and empty selections | Met |
| NFR16 | Numbers and units formatted deliberately; status colours have text alternatives | Met (Latin digits in both languages, SPEC_CONFLICTS C9) |
| NFR17 | Keyboard access and visible focus | Met (automated checks). Screen-reader testing not done |
| NFR18 | Responsive layout without horizontal scrolling | Met (12 pages × 2 languages × 2 viewports) |

## Data and calculation rules (booklet §3.3–3.8, Table 3.1, Appendix B)

| ID | Rule | Status |
|---|---|---|
| DR01 | Verified-source and synthetic data are separate modes; never mixed or substituted | Met |
| DR02 | A catalogue page does not verify an observation (Brief) | Met |
| DR03 | No official statistics, boundaries, sources or results invented (Brief) | Met |
| DR04 | Stored values unrounded; rounding only on display | Met |
| DR05 | Comparisons only for the same unit dimension, compatible periods and coverage | Met |
| DR06 | Natural key includes every relevant dimension; duplicates rejected | Met |
| DR07 | One designated published snapshot per source; revisions supersede | Met |
| DR08 | Table 3.1 calculations with their guards (growth, availability, contributions, partner share, trade balance, unit value) | Met |
| DR09 | Appendix B import validation rules | Met |

## Rules and reviews (booklet §3.13, Table 3.6)

| ID | Rule | Status |
|---|---|---|
| RR01 | R01 demand growth, R02 supplier concentration, R03 value/quantity divergence, R04 data quality | Met |
| RR02 | Thresholds are recorded project assumptions, not official standards | Met |
| RR03 | Reviews appended; calculation immutable; latest review is the status | Met |

## Geography and forecasting (booklet §2.4, §3.14, §4.6; Brief)

| ID | Requirement | Status |
|---|---|---|
| GEO01 | Sourced registry of governorates and wilayats with EN/AR names, stable identifiers, parents, verification dates, references; completeness verified (Brief) | Met (11 + 63) |
| GEO02 | Maintained mapping library, licensed boundaries, suitable tile provider, attribution (Brief) | Partly met: MapLibre + OpenFreeMap with attribution; **no licensed current boundary geometry exists**, so no boundaries or map selection |
| GEO03 | Registry coverage distinguished from statistical coverage; "No data", never zero; no allocation of national totals (booklet §3.14; Brief) | Met |
| GEO04 | Accessible table alternative; graceful map failure (Brief) | Met |
| FC01 | Target, horizon, chronological splits and baseline defined before fitting; training-only transforms; identical held-out dates; predictions and errors kept; MAE/RMSE interpreted; interval method documented (booklet §2.4, §4.6; Brief) | Met in the engine (tests on synthetic series); no real series eligible |
| FC02 | "Forecast unavailable" state with reasons when no series is eligible (T10; Brief) | Met |

## Acceptance tests (booklet Table 4.3)

| ID | Input or action | Expected outcome | Status |
|---|---|---|---|
| T01 | Previous value is zero | Undefined percentage explained | Pass |
| T02 | Value absent in source | Missing retained in chart and export | Pass |
| T03 | Mix GWh with MW | Comparison rejected | Pass |
| T04 | Upload duplicate natural key | Duplicate reported; no double count | Pass |
| T05 | Select overlapping source versions | One explicit snapshot used | Pass |
| T06 | Public user requests publish | Denied; no data change | Pass |
| T07 | Synthetic mode report | Visible synthetic label and metadata | Pass |
| T08 | Switch Arabic to English | Same filters and numbers | Pass |
| T09 | Trade partner subtotal | Partial coverage clearly labeled | Pass |
| T10 | Generate forecast with inadequate history | Forecast withheld with reason | Pass |
| T11 | New import fails during publication | Previous published snapshot preserved | Pass |
| T12 | Export the commodity fixture | 160,000 tonnes and stock assumption retained | Pass |

## Out of scope (booklet §1.4, §3.14)

Physical sensors, live utility control, a mobile application, a national tourism
directory, investment-return predictions, navigation features and tourism
photography in the analytical workflow.
