# Demonstration script (about 10 minutes)

For the university presentation. Everything shown uses **synthetic** data: the
booklet's worked examples plus a small synthetic upload. Say so at the start and
whenever a number appears.

## Before the session (15 minutes earlier)

1. Start the database, API and interface (README → *Start*). Open
   `http://localhost:5173` in a maximised browser window; zoom 110–125 % for the room.
2. Make sure the database has only the seeded fixtures, so the numbers below match.
   For a clean state: `python scripts\devdb.py createdb osrip_demo`, then
   `alembic upgrade head` and `python -m app.cli seed-synthetic` with
   `OSRIP_DATABASE_URL` pointing at `osrip_demo`, and start the API with
   `$env:OSRIP_DATABASE_URL=(python scripts\devdb.py url osrip_demo); python scripts\serve_dev.py`.
3. Create two accounts (README → *Install* step 2): a data manager with
   `import.approve` and `import.publish`, and an analyst. Keep the passwords out of
   view of the audience.
4. Have `docs/demo/demo-upload.csv` ready (three synthetic rows, one deliberately in
   the wrong unit).
5. Fallback if the API fails: `$env:VITE_DATA_ADAPTER="mock"; npm run dev` shows the
   interface with in-browser fixtures (no calculations, reports or sign-in). Say
   that it is the fallback.

## Script

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Home | Scroll once | "OSRIP helps an analyst check electricity, water, food and trade figures and see where each number comes from. It is an academic prototype, not an official statistics service. The photos are licensed and credited." |
| 0:45 | Overview, verified mode (default) | Point at the "No verified data yet" panels | "By default only verified-source data is shown, and we have not loaded any. The app shows that honestly instead of filling the gap with demonstration values." |
| 1:15 | Data mode → *Synthetic demonstration data* | Point at the amber banner and badges | "These are the booklet's worked examples, labelled as synthetic everywhere, including exports." |
| 1:45 | Energy → Electricity | Open the growth card; open *Source details* | "48,000 to 50,100 GWh: +2,100 GWh, 4.38 %. The exact value 4.375 is stored; rounding is only on screen. Every result shows its formula, inputs, dataset version and limits: generation is not consumption, so we do not divide it by subscribers." |
| 3:00 | Food Security | Change *Stock-change assumption* to *Unknown* | "Apparent availability is 160,000 tonnes only under a declared zero stock change. Change the assumption and the calculation and its export change with it." |
| 3:45 | Trade | Point at partner shares and trade balance | "Partners A, B and C are fictional. The balance is −28 million rial, which is not a profit; the unit values 500 and 600 are not retail prices." |
| 4:30 | Language → العربية | Point at the same numbers | "Arabic changes the labels and direction, not the data or filters." Switch back to English. |
| 5:00 | Sign in as the data manager → Data Management | Register a synthetic source; upload `demo-upload.csv`; *Validate* | "Validation keeps every rejected row with its row number, original value and reason: one row uses MW for an energy quantity, so it is rejected, never silently dropped." |
| 6:15 | Same screen | Tick the acknowledgement; *Approve*; *Publish* | "Approval must acknowledge the rejected rows. Publication is one transaction; repeating it cannot duplicate data." |
| 6:45 | Sign out; sign in as the analyst → Electricity | Show the new consumption growth (5 %); *Run review rules*; add a review to a card | "The new file is live. Review cards ask questions; they do not state causes. Reviews are appended, never overwritten." |
| 8:00 | *Save as report* → open it | Show the label, filters, versions; *Print* | "A report freezes its inputs. If a corrected file is published later, this report still shows what it was based on." |
| 8:45 | Geography | Point at 11 / 63, then a wilayat with "No data" | "The area registry is sourced from Ministry of Finance, Ministry of Interior and Oman News Agency publications. 'No data' is not zero, and national totals are never split across wilayats. The map is for orientation only; we found no licensed, current boundaries." |
| 9:30 | Forecast experiment | Point at *Forecast unavailable* | "The forecasting experiment needs at least 12 complete annual values. No series qualifies, so no forecast is shown. That is a result, not a missing feature." |
| 9:50 | (Slide) Evidence | Show `docs/TEST_RESULTS.md` | "168 backend tests and 31 browser tests pass; a backup was restored into a separate database. Measured performance is in the report; the two-second target is not claimed for concurrent use." |

## Likely questions

| Question | Answer |
|---|---|
| Is this real Omani data? | No. All values are synthetic demonstration inputs; the verified mode is empty until a source table is registered, reviewed and published. |
| Why no map colours by wilayat? | No wilayat-level statistics are published in the app, and no licensed current boundary file matching the 63 wilayats was found. Colouring would imply data that does not exist. |
| Why is the forecast unavailable? | The booklet requires a baseline comparison on held-out periods; with one or two periods per series that is impossible. The engine is built and tested on synthetic series. |
| Could someone publish without permission? | No. Every action is checked on the server; tests send direct API requests as a viewer and are refused. |
| How fast is it? | Measured on a laptop: single-client reads under 0.6 s (p95); with 10 simultaneous clients on one server process, p95 4.7 s. The booklet's two-second target is therefore not met under concurrency. |
