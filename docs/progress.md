# Progress record

Real implementation progress against the booklet's delivery plan (Table 3.7). Dates
are when the work was done and verified. Evidence for each line is in
[VERIFICATION.md](VERIFICATION.md) (per increment) and [TEST_RESULTS.md](TEST_RESULTS.md)
(latest audit).

## Increments

| Date | Increment | What exists now | Evidence |
|---|---|---|---|
| 2026-09-24 | Foundation (0.1.0) | Calculation layer for booklet Table 4.2, first migrations, interface shell | Calculations and SQL checks run; dependencies could not be installed in that environment |
| 2026-09-25 | Visual identity | Omani-inspired design tokens, landing page, dashboard, navigation, RTL, licensed photos | Build, contrast 54/54, browser tests |
| 2026-09-25 | Data model and import workflow | Users, roles, grants, sessions, CSRF; sources, versions, observations; CSV upload → map → validate → error preview → approve → transactional publication; audit | Integration tests, full-stack upload test |
| 2026-09-25 | Calculations, review cards, reports (0.3.0) | Section calculations with formula, inputs and reasons; rules R01–R04 with append-only reviews; frozen reports; CSV exports | Booklet fixtures asserted at API and interface |
| 2026-09-25 | Geography and forecast eligibility (0.4.0) | Sourced registry (11 governorates, 63 wilayats); coverage by area; orientation basemap; forecast eligibility, experiment engine and "Forecast unavailable" state | Registry literals from sources; hand-worked forecast numbers |
| 2026-09-25 | Release-candidate audit (0.4.1) | ESLint; full journey and quality browser tests on desktop and phone; performance workload; backup/restore exercise; 5 defects fixed (TEST_RESULTS.md D1–D5); requirements register, traceability, API docs, demo script, deployment configuration | All checks pass; performance and backup measured |
| 2026-09-26 | Accounts, assistant, 2022+ statistics (0.5.0) | Self-registration, e-mail confirmation, recovery and magic links; Google and Microsoft sign-in (when configured) with explicit linking; user administration; evidence-grounded bilingual assistant (Claude, server side) with citations, "How calculated", limits and deletion; statistics scope from January 2022 with governorate filter and latest period per series; NCSI conversion tool; landing refresh with a labelled portrait illustration | 219 backend tests, 50 full-stack browser tests; live providers not tested (no credentials) |
| 2026-09-26 | Forecasts, scenarios, services, interface (0.6.0) | Forecasts and Scenarios page: nine targets with "Insufficient data to forecast." states, rolling-origin backtests against a baseline, seasonal and trend candidates, stored future estimates with 80/95% intervals, distinct history/estimate styling, deterministic EN/AR explanations, assistant hand-off (explains, never forecasts); separate scenario explorer; built-in error monitoring and Service health page; readiness check; limited retries for the assistant and OIDC; four-question insights and filter summary on analytical pages; restructured navigation; motion with reduced-motion support; import progress; deployment health check, nightly backup service and pre-publication check | 242 backend tests; full-stack browser suite incl. six-width responsive matrix; nothing deployed (no hosting access) |
| 2026-10-02 | Web research, talking AI Assistant, username accounts, navy/teal identity (0.8.0) | Assistant web research (Brave Search adapter, official-first ranking, SSRF-safe page retrieval, web evidence with source class and dates, failed searches always shown, numbers checked against cited text); review queue for web figures with duplicate/revision/unit/period checks (migration 0011, `research.review`); server speech (Azure AI Speech REST, ar-OM and en-GB voices, audio never stored) with browser fallback; fictional AI-generated face (Canva) labelled "AI Assistant" with loudness-driven speaking animation; username accounts with required password change and idempotent `ensure-user`; account Azzan created locally; navy/teal/ivory/copper tokens with contrast checked from the CSS; period and limitations on every analytical page; launcher finds an MSIX-virtualised data folder and reports unconfigured services; VS Code Edge debugging; hostname osrip.project.com prepared | 335 backend tests (38 new); browser suites; live search, speech and model **not tested (no credentials)**; no public URL |
| 2026-09-27 | Phone registration, visual refresh, 3D navigation (0.7.0) | Registration and sign-in by e-mail or phone, neither required: Oman +968 default, SMS provider interface, request and verify routes with cooldowns, limits, expiry, single use, replay protection and masked numbers; verified linking of phone and e-mail (never merged); migration 0008. Copper-accented palette, shared card surfaces, four original sector illustrations, dimensional hero and gentle card tilt with a 2D fallback, animated tabs | 278 backend tests (36 new); full-stack browser suite incl. 18 phone tests on desktop and phone; **no SMS provider selected: no live delivery** |

## Booklet delivery plan (Table 3.7) — status on 2026-09-25

| Weeks | Deliverable | Review gate | Status |
|---|---|---|---|
| 1–2 | Problem, users and platform choice | Supervisor scope confirmation | Scope implemented as specified; **supervisor confirmation not recorded** (C12) |
| 3–4 | Sources and commodity mapping | Compatible input definitions | **Not done**: no verified source registered; commodity mapping provisional (C14) |
| 5–6 | Schema and interface prototype | Migration and screen review | Done (migrations 0001–0005, reviewed screens) |
| 7–8 | Authentication and first data path | Permission and import tests | Done |
| 9–10 | Domain views and reports | Independent calculation fixtures | Done (with synthetic fixtures) |
| 11–12 | Rules and eligible forecast | Baseline comparison plan | Rules done; forecast **unavailable** (no eligible series), engine tested |
| 13–14 | Integrated tests and corrections | Recorded defect resolution | Done for this release candidate (TEST_RESULTS.md) |
| 15–16 | Usability, report and demonstration | Evidence audit and final review | Demo script ready; **usability study not conducted**; final review pending |

## Next steps, in order

1. Supervisor confirmation of scope and platform (C12).
2. Register and review at least one verified source table per domain (direct file
   or statistical table, access date, reuse conditions), import it and re-run the
   calculations and the forecast eligibility check on real data.
3. Confirm commodity product forms and trade codes (C14).
4. Decide the tile provider (C28) and look for a licensed boundary dataset (C8).
5. Arabic language review by a qualified speaker.
6. Obtain clearance and run the usability sessions (booklet 4.6).
7. Put the code in git, deploy to an HTTPS host after the team decides on hosting,
   and repeat the performance and backup exercises there.
