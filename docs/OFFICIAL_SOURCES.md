# Official statistics: sources, access and synchronisation

This page records what was checked by hand against the publisher, what OSRIP reads
automatically, and what it cannot read. Every finding below was verified on **2026-10-23**.

## 1. What was verified

| Source | What was tested | Result | Used for |
|---|---|---|---|
| NCSI data portal API, `POST https://data.gov.om/api/1.1/data/details` (documented at <https://data.gov.om/lnjypfd/get-raw-data?lang=en>) | The documentation's own example request (dataset `OMINF2016`), from the server over HTTPS and from an anonymous browser session on the portal itself; also `GET /api/1.0/meta/dataset` and `/meta/dataset/OMINF2016` | **HTTP 403** every time, empty body. The documentation page is the only one published; it names no key, sign-in or quota | Nothing automatic. Registry entry `ncsi-data-portal`, status "needs access" |
| NCSI data portal downloads (dataset pages such as `OMWTR2016`) | Download links | Need a signed-in portal account | Manual CSV download, then `backend/scripts/ncsi_import.py` and Data Management |
| NCSI publications list, <https://www.ncsi.gov.om/en/publications> | HTTPS GET | **200**, valid certificate. The page carries the list of releases as JSON in its `__NEXT_DATA__` script: id, English and Arabic titles, `created_at`, `updated_at`, PDF and (for some releases) Excel file addresses on `api.ncsi.gov.om` | Release checks (registry entry `ncsi-monthly-bulletin`) |
| Monthly Statistical Bulletin, October 2026 (list id 1968, created 2026-10-20T09:28:38Z) | Official workbook `https://api.ncsi.gov.om/uploads/xls/monthly_statistical_bulletin__october_2026_1792565580.xlsx` | **200**, 2,048,496 bytes, Excel 2007+, 33 tables | Tables 21 and 22 are read |

The PDF-only releases in the same list (for example the Statistical Year Book 2026) have no
workbook; they are recorded as "no workbook" and their figures are added by hand, as the
September 2026 bulletin and the Year Book were (the reference pack, sources S01 and S02).

`updated_at` in the publications list changes during the day (for example when a release is
viewed or rated), so it is recorded but never used to decide that a release changed. A release
is identified by its list id and its file address, and a file by its SHA-256 digest.

## 2. The registry

`backend/app/services/sync/registry.py` holds what the code needs; the `source_feed` table
(migration `0022_source_sync`) holds each feed's schedule and switches.

### `ncsi-monthly-bulletin` — public list of releases

| Table (sheet) | OSRIP indicator | Unit | Areas | Periods in each bulletin |
|---|---|---|---|---|
| 21 Electricity, "Gross Production" | `ELEC_GROSS_GENERATION` | GWh | Muscat `OM-MA`, Dhofar `OM-ZU`, Musandam `OM-MU`, Ad Dakhliyah `OM-DA`, Al Batinah & Adh Dhahira `OM-GRP-BATINAH-DHAHIRAH`, Ash Sharqiya `OM-GRP-SHARQIYAH`, Al Wusta `OM-WU`, Others `OM-GRP-OTHER-ELEC`, Total `OM` | the three latest months; the previous full year; year-to-date of the current and previous year |
| 21 Electricity, "Net Production" | `ELEC_NET_GENERATION` | GWh | as above | as above |
| 22 Water, "Production" | `WATER_PRODUCTION` | thousand m³ (`thousand_m3`, shown in million m³) | Muscat `OM-MA`, Dhofar `OM-ZU`, Other governorates `OM-GRP-OTHER-WATER`, Total `OM` | as above |

* **Status marks.** Years carry footnote marks defined under each table: ⁽¹⁾ provisional,
  ⁽²⁾ preliminary. They become the observation's revision status.
* **Scale and precision.** No scale factor: values keep the unit printed in the table. Each
  cell is read as the publisher displays it: the cells are formatted `#,##0.0`, so a stored
  571.32553376831106 is the published 571.3. The extra digits in the file are spreadsheet
  arithmetic, not published precision. This matches the figures typed earlier from the PDF
  edition, so an unchanged figure is never imported twice.
* **Not imported:** the percentage-change columns (the publisher's derived figures) and every
  other table of the bulletin (not mapped yet).
* **Layout checks.** The table title, the header rows (months, years, the "Total (End - Sep)"
  year-to-date columns), the unit and the footnote marks are found by their text, and every
  region label must be in the map above. Anything unexpected stops the conversion; nothing is
  guessed. The regional rows are added up and compared with the table's total; a difference
  above 0.5 % is written into the release's log message.

### `ncsi-data-portal` — needs access

Cannot be switched on (the database refuses it). To use it, NCSI would have to grant API
access; the registry entry and the adapter would then be extended with the dataset
identifiers, dimensions and members that the granted access shows. No dataset identifier is
assumed from the documentation example.

## 3. How a check works

1. **Where it runs.** In the sync worker, a process of its own: `python -m app.worker`
   (production), `python scripts/sync_worker_dev.py` (development), or the launcher with
   `--with-sync-worker` (or `OSRIP_SYNC_WORKER=1`). Never in the web server and never in the
   browser. Several workers may run: each feed is checked under a PostgreSQL advisory lock.
2. **When.** Only after an administrator switches the feed on in Data Management. The
   starting point is a daily check (24 h; 48, 72 or 168 h can be chosen; at most one check
   every 6 h is allowed). A manual "Check now" runs at once.
3. **Reading the list.** One HTTPS request, at most 3 MB, to `www.ncsi.gov.om` only. Up to
   three attempts with exponential backoff (2 s, then 4 s) on network errors, 429 and 5xx; a
   `Retry-After` is respected up to 60 s. Redirects are followed only to the allowed hosts.
4. **A new release.** At most three new releases per check. The workbook is downloaded (at
   most 30 MB, `api.ncsi.gov.om` only) and read with a standard-library reader (limits on
   entries and size, no XML document types or entities, nothing executed).
5. **Comparison.** Each figure is compared with the published verified-source figures for the
   same indicator, area, period, completeness and unit, at the precision both publications
   give. Same figure: skipped. No figure yet: new. Different figure: revised.
6. **Staging.** New and revised figures become one ordinary import (a source per release, with
   the file address, the publisher's date and the open government licence), validated by the
   import workflow. It waits for a data manager's approval in Data Management, unless an
   administrator switched on automatic publication for the feed (off by default; even then only
   a validated import without rejected rows is published).
7. **Revisions.** Earlier releases stay published. Where two releases give the same period,
   the table shows the newer figure and lists the other with the row ("revised").

### What a check can never do

* Replace or remove published figures. A failed request, an unreadable list or workbook, or a
  validation error changes nothing that is published; it is written to the log.
* Duplicate observations. A known release is not downloaded again; the same file is processed
  once; a figure already published is not imported again (also through a hand upload).

## 4. Three different moments

Data Management and the Sources page show, for each feed:

* **Last successful check** — when OSRIP last read the list without error;
* **Latest release found** — the publisher's own date for the newest release;
* **Latest observation period** — the end of the latest period with a *published* figure.

A successful check does not mean anything new was published: on 2026-10-23 the check
succeeded, the latest release was the October 2026 bulletin (published 20 October 2026), and
the latest published observation still ended on 31 August 2026, because the September figures
were staged, not yet approved.

## 5. The live check of 2026-10-23

A manual check of `ncsi-monthly-bulletin` against the real site, into the development
database:

* list: HTTP 200, 1 bulletin in the first page (id 1968);
* workbook: HTTP 200, 132 figures read from tables 21 and 22, regional rows adding up to the
  totals;
* 104 new figures (September 2026, regional months, January–September year-to-date), 22 already
  published (for example Dhofar 2025: 5,622.4 GWh), and **6 revisions** by NCSI of its own
  preliminary July and August 2026 national figures:

| Indicator | Month | Published (September bulletin) | October bulletin |
|---|---|---|---|
| Gross generation, GWh | Aug 2026 | 5,743.9 | 5,745.6 |
| Gross generation, GWh | Jul 2026 | 5,676.9 | 5,663.9 |
| Net generation, GWh | Aug 2026 | 5,591.9 | 5,593.8 |
| Net generation, GWh | Jul 2026 | 5,531.5 | 5,533.8 |
| Water production, thousand m³ | Aug 2026 | 43,165.1 | 43,355.1 |
| Water production, thousand m³ | Jul 2026 | 42,533.8 | 43,341.6 |

The 110 figures were staged as an import awaiting approval; nothing was published by the check.

## 6. Manual import of official files

* **A bulletin workbook downloaded by hand:** Data Management → Official statistics updates →
  "Import a workbook downloaded by hand" (the official file address is required as
  provenance). It goes through exactly the same checks and comparison.
* **A data portal CSV:** `backend/scripts/ncsi_import.py` (inventory, then convert with a
  reviewed mapping), then upload in Data Management.

## 7. Tests

* `backend/tests/test_source_sync.py` — reader limits and refusals, number formats, the
  bulletin layout (records, periods, marks, locators, refusals on unknown regions or units,
  totals check), the publications list, retries with backoff and `Retry-After`, allowed hosts.
* `backend/tests/test_zzz_source_sync_integration.py` — with the publisher replaced by a local
  stand-in: new figures staged once; a repeated check and a re-sent file add nothing; a later
  release stages only its revised figures and the timeline shows the newer value with the
  earlier one kept; a failed check changes no published data and backs off; the portal is
  reported as not accessible; only administrators change the schedule or start a check.
* `frontend/e2e-api/source-feeds.spec.ts` — the public status and the administrator's
  controls through the real API (no request to the publisher).
