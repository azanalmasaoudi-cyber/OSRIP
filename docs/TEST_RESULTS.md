# Test results

## 2026-10-16: first source upgrade (branch `review/codex-upgrade-2026-10-15`)

The research brief builder, workspace launchpad, missing-portrait fallback, home-only entrance
and the browser voice correction from the 15 October review archive. Details:
`CODEX_REVIEW_2026-10-15.md`, "Integration into the project". Browsers: installed Edge
(`PW_CHANNEL=msedge`); no Playwright Chromium is downloaded on this laptop.

| Check | Result |
|---|---|
| `npm run build` (`tsc -b`, Vite) | Pass; the existing bundle-size warning remains |
| `MSBuild OSRIP.sln /t:Build` | Pass (exit 0) |
| `npm run lint` | Pass |
| `node --experimental-strip-types --test tests/research-brief.test.mjs` | **5 passed** (32 templates, answer modes, voice gender and selection) |
| Mock browser suite, desktop and Pixel 7 | Final run: **35 passed**. Earlier: 31 passed, 2 failed (two test problems, fixed); and one run with 4 entrance timing failures while the laptop was in Modern Standby (10:25–10:28), passed on the immediate re-run |
| Full-stack suite (`playwright.api.config.ts`), desktop and Pixel 7, including the new `research-brief.spec.ts` | **122 passed**, 1 skipped, 1 failed: `quality.spec.ts:76` stalled for 10 minutes while the laptop was in Modern Standby (Windows power log); re-run alone 3 times: 3 passed |
| Brief builder against the real settings (launcher stack) | Draft and mode set, no request sent, guest allowance unchanged; on Send one request, reply "unavailable" (Anthropic `http_401`), not charged; the test conversation was then deleted |
| Launcher (`start_osrip.py --no-browser --keep-db`) | Ready; PostgreSQL started, migrations at head (0019) |

## 2026-10-14: project at its new location (`C:\Users\Dell\Desktop\OSRIP`)

The project moved out of OneDrive with the Windows Desktop. Before re-testing:

- the backend environment was rebuilt with the same 95 packages;
- about 20,800 files that still carried OneDrive cloud markers were rewritten as ordinary
  files, with the same bytes and timestamps.

Details are in `WINDOWS_STARTUP.md`, under "What was verified".

| Check | Result |
|---|---|
| All 589 files named by the solution present at the new path, none empty | Pass |
| `pip freeze` of the rebuilt environment against the moved one | 0 differences; `app` imports from the new path |
| Backend `OSRIP_RUN_DB_TESTS=1 pytest` | **551 passed** (69.7 s) |
| `ruff check` (app, tests, scripts, tools) | Pass |
| `npm ls --depth=0` | All dependencies present |
| `MSBuild OSRIP.sln` Clean, Build | 0 warnings, 0 errors |
| `npm run lint` | Pass |
| Mock browser suite | **27 passed**, 2 skipped. Before the markers were removed: "No tests found" |
| Launcher with Python 3.14.7 (as Visual Studio's F5) | Ready in about 10 s; 4 routes 200; clean stop |
| Backup | `Documents\OSRIP-backups\OSRIP-project-2026-10-14.zip` (592 files, archive test passed) and `osrip_dev-database-2026-10-14.dump` (56 tables with data) |

## 2026-10-11 (evening): files made suitable for this laptop and Visual Studio

No behaviour change and no new package.

Changes:

- `tools/make_vs_projects.py` now writes `OSRIP.sln` as well, with solution folders for the
  repository files and every project set to build.
- The frontend project replaces the failing `npm run clean` step.
- New `.editorconfig` and `.vsconfig` files.
- 14 CRLF files converted to LF, and six generators now write LF.

| Check | Command | Result |
|---|---|---|
| Solution Explorer coverage | scan of project files against `OSRIP.sln` and the three projects | 587 shown. Not shown, on purpose: the project files themselves, `backend\.env` and `deploy\.env` (secrets), `docs\.vscode` (another editor's state) and `Web.config` (old copy, owner's decision pending) |
| Visual Studio build | `MSBuild OSRIP.sln /t:Clean`, `/t:Build`, `/t:Rebuild` (VS Community 18.10.3) | **Pass**: 1 s, 12 s and 15 s; 0 warnings, 0 errors. Before: Clean and Rebuild failed (`npm run clean`: missing script); Build skipped every project |
| Line endings | byte scan of 484 project text files | No mixed files. CRLF only where Windows needs it: `.cmd`, `.sln` and the projects (plus the untouched `deploy\.env`, `Web.config` and `docs\.vscode`) |
| Backend | `OSRIP_RUN_DB_TESTS=1 pytest`; `ruff check`, `ruff format --check` (app, tests, scripts, tools) | **Pass: 551 passed** (67 s); lint pass |
| Frontend | `npm run lint`; `npx playwright test` (mock); type check and build via MSBuild | **Pass**; 27 passed, 2 skipped |

## 2026-10-11 (later): integrated verification

Same machine and toolchain; no new package; no migration. The assistant, search and speech
were the scripted test providers. **No live provider was used**: the stored Anthropic and
Brave keys are still rejected, and there are no OpenAI, Gemini or Azure keys. The
demonstrations and their screenshots are in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 551 passed**. The first run had 1 failure in a new test: it expected four history sentences, but other modules add years to the shared database. The assertion was fixed to `min(4, rows)` |
| of which: allowance rules | `test_allowance_rules_integration.py` (new) | Pass: 1. One guest session covers every rule:<br>• Greetings are free in both personas and languages.<br>• A failed answer, and its retry with the same request id: 0 used.<br>• A completed answer, then a replay, three speech requests (one narration segment, the whole reply, the segment again), Stop after completion and the reopened study: still 1.<br>• Answers 2–5 through Ilham in Arabic, the voice bridge, Research and Compare: 5.<br>• A sixth answer is refused for both personas and by voice; the greeting is still free.<br>• The database holds exactly 5 charged requests and no reservation |
| of which: live studies | `test_live_study.py` | Pass: 17 (new: in a series answer, each sentence points at its own row, with the same value and period) |
| Allowance, persona, voice and registration modules | targeted run | Pass: 102 |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Frontend | `tsc -b`, `npm run lint`, `npm run build` | **Pass** |
| Contrast | `npm run check:contrast` | 0 failing pairs |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **114 passed, 3 failed, 1 skipped** (37.1 min). The failures were `phone.spec.ts:99`, `workspace.spec.ts:101` and `workspace.spec.ts:132` (desktop). Each overlapped Modern Standby, logged by Kernel-Power events 506/507: the laptop was on battery at 12 % and went idle. Each failure was a 30-second test timeout with frozen page timers (a countdown stuck at "3 s"). **Re-run alone: 3 passed** (36.8 s) |
| Visual Studio projects | `make_vs_projects.py`, `MSBuild OSRIP.sln` | **Build succeeded**, 0 warnings, 0 errors |
| Demonstration suite (new) | `playwright test -c playwright.demo.config.ts` (verified reference pack loaded) | **Pass: 6 passed**, 17 screenshots in `docs/evidence/integrated/` |
| Provider keys | free checks, outcomes only | Anthropic 401, Brave 422; OpenAI, Gemini and Azure not configured |
| Live provider failure | guest requests on the launcher-started site | Greeting free; question and Research `unavailable`, 0 used |
| Startup | `tools\start_osrip.py --check`, then a full start (ports 8020/5190) | Ready in 13 s; 6 routes answered 200; stopping ended what it started |

Defects found and fixed:

1. Verified electricity and water mix annual, year-to-date and monthly series, but the
   workspace had no frequency choice: it could only say "choose one frequency", and its
   links left the page. It now has a Frequency filter, and the notice's buttons set it in
   place.
2. Two verified series from different sources had the same React key, so one card could be
   dropped. The key now includes the source.

Environment note: the first full-stack run did not start. Its API server timed out because the
development PostgreSQL had stopped uncleanly (stale `postmaster.pid`), probably when the
session that started it ended. `devdb.py start` started it, and the suite was run again.

## 2026-10-11: analytical workspace and live studies (migration 0019)

Same machine and toolchain. No new package (charts: OSRIP's own; transitions: the installed
`motion`). `osrip_dev` upgraded 0018 → 0019 (additive: the `study_event` table) after a
`pg_dump` backup (`osrip_dev-before-0019-20261010-204350.dump`). The assistant, search and
speech were the scripted test providers; **no live speech service was used**.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 549 passed** (532 before this increment) |
| of which: live studies | `test_live_study.py` | Pass: 16. Covers:<br>• Findings split at sentences, never inside a decimal, and a citation covers its paragraph.<br>• Observation tables: one per unit and series; missing stays missing; each row is tied to its source.<br>• Tables that break the shared rules are never sent; a warning is sent instead.<br>• Narration comes from the findings and points at the rows it cites.<br>• Withheld or cancelled studies confirm no table; study tables are sent unchanged.<br>• Completion that points at an unknown table is refused.<br>• Through the API: events contiguous and in order; the source arrives before its table; table, reply and narration state the same number.<br>• Server-sent events replay, resume after `Last-Event-ID`, then end.<br>• Study and governorate tables.<br>• Cancellation ends with `study.cancelled` and nothing after; a failed search becomes a warning.<br>• Another visitor sees nothing.<br>• Narration segments are spoken one at a time.<br>• Events are deleted with the conversation; the preview is not stored |
| Migration round trip | `test_migrations_roundtrip_integration.py` | Pass: 4. New for 0019: an unknown event type, a repeated sequence number and a non-object payload are refused; events are deleted with their conversation; down to 0018 keeps requests; up again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **Pass: 117 passed** (16.4 min; 1 skipped: the phone test in the desktop project). An earlier run had 4 failures, all fixed (two listed below, plus two test assumptions: the page title and a sort button named after one series) |
| of which: workspace | `workspace.spec.ts`, `workspace-phone.spec.ts` | Pass: 6 + 1. Covers:<br>• Filters, and cards with unit, source and stale flag.<br>• Chart points = table rows; sorting changes order, never values.<br>• No geographic view without coverage; verified mode empty state.<br>• Live study: Study tab comes forward; stages; source; final table; finding = table value.<br>• Narration reads N1 and highlights its row, finding and source, with the avatar speaking; stop keeps the highlight.<br>• Failed search shown as a partial failure; source dialog by keyboard with focus return; tabs by arrow keys.<br>• Return to an earlier study (replayed); Arabic labels with unchanged values.<br>• Crafted streams: after a stop, late and superseded events are ignored and nothing becomes final; a table failing browser validation is reported, never drawn.<br>• Phone: three tabs, study brought forward, follow-up, no sideways scroll |
| Changed tests | `assistant.spec.ts`, `upgrade.spec.ts`, `zz-mixed-frequency.spec.ts` | The floating assistant is hidden on the workspace, so these open it from the Electricity page; the mixed-frequency link is checked on the workspace with the Water section chosen |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass** (React Compiler and hook-rule findings fixed first) |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Visual review | full-size screenshots, `docs/evidence/workspace/*.png` | Desktop light and dark, Arabic, phone. Fixed after review: cramped data-mode control and domain tiles, wrapping narration controls, highlight bar touching the cell text, raw provider code, duplicated recommendations heading, a long badge that made phones scroll sideways |

Defects found and fixed during the runs:

1. A badge that cannot wrap ("No licensed boundary map…") made the workspace 27–79 px wider than a phone screen. It is now a wrapping note.
2. The workspace page title did not contain "Overview", the navigation's name for it. It is now "Overview: analytical workspace".

## 2026-10-10 (evening): governed AI and research service (migration 0018)

Same machine and toolchain. No new package. `osrip_dev` upgraded 0017 → 0018 (additive: the
`provider_call` table) after a `pg_dump` backup (`osrip_dev-before-0018-20261010-155306.dump`).
Every external provider ran through scripted routes or mocked HTTP: **no live OpenAI, Gemini,
Anthropic or Brave call was made** (no working key; `docs/AI_PROVIDERS.md`).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 532 passed** (500 with personas) |
| of which: providers | `test_ai_providers.py` | Pass: 21. Covers:<br>• OpenAI Responses requests: function tools only, `store: false`, its own output items replayed.<br>• Gemini Interactions requests: steps sent back exactly; function results named.<br>• Usage counting, including thought tokens.<br>• A timeout is retried once, then reported; a 401 is not retried.<br>• The daily limit and the budget stop a call before anything is sent.<br>• Citations: OpenAI `url_citation` kept with its URL; Gemini byte offsets in Arabic; Search Suggestions kept.<br>• Grounded results never reach the model.<br>• The fallback route is used only after a failure; a cross-check only when asked, with the non-independence note.<br>• A planted instruction in a provider summary stays untrusted and never reaches the review queue.<br>• Routing and data-first search; `data_status` on every item.<br>• Readiness without secrets; grounded expiry |
| of which: through the API | `test_ai_providers_integration.py` | Pass: 9. Covers:<br>• Numbers look up data before the web; recent events may search first.<br>• The answering fallback runs after two OpenAI timeouts, and both are recorded in `provider_call` without tokens or text.<br>• At the daily limit nothing is sent and the guest is not charged.<br>• Google results are shown apart and not used in the answer.<br>• A cross-check runs only on request.<br>• Conflicting sources across routes are both reported and labelled; the agreeing provider summary is not cited.<br>• An invented figure is withheld.<br>• Readiness: viewer 403; `audit.read` alone can view but not test (403); an administrator can test.<br>• Expired grounded results are purged |
| Production settings | `test_api_foundation.py` | Pass: scripted routes (`fake`, `fake-gemini`) as fallback or primary make production refuse to start |
| Migration round trip | `test_migrations_roundtrip_integration.py` | Pass: 3. New for 0018: a capability outside the list and a free-text status (a question) are refused by the database; down to 0017 removes only the log; up again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **Pass: 110 passed** (18.5 min, no failures) |
| of which: governed AI | `governed-ai.spec.ts` | Pass: 4. Covers:<br>• Synthetic records labelled "Synthetic demonstration data", never approved official.<br>• Web sources labelled "Unreviewed external evidence".<br>• Numbers checked against data first; one route only.<br>• After a failed first route, the Google-style fallback is shown below the answer, with a clickable citation and the suggestions in a script-free sandboxed frame; the answer does not use it.<br>• Research-mode cross-check: off by default, labelled "not independent evidence".<br>• Provider readiness for an administrator: all four providers unavailable, missing setting names shown, no Test buttons, routing line, subscription note |
| Changed test | `upgrade.spec.ts` | Pass. With a fallback route configured, a failing search now fails on both routes; both failures are listed (the second as `fallback`), and the guest is not charged |
| Mock browser suite | `npx playwright test` | 25 passed, 2 failed, 2 skipped while the backend suite ran at the same time. The 2 failures were entrance timing tests; **re-run alone, all 11 desktop entrance tests passed**. The entrance was not changed |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass** (one accessibility finding on the new cross-check checkbox fixed first) |
| Backend lint | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Evidence | `docs/evidence/ai-providers/*.png` | Provider readiness, the Google results panel (English desktop; Arabic phone header), method summary, search log and a labelled web source, captured from the full-stack run |
| Live verification | Service health → Test; `scripts/set_provider_keys.py` | **Pending**: needs real API keys and model ids for OpenAI and Gemini, and working Anthropic and Brave keys |

Defect found and fixed during the run: the new integration tests left a queued web figure
behind, so in the full suite `test_upgrade_integration.py` found no candidate of its own
(candidates are de-duplicated by source). They now delete what they queued, as other
modules do.

## 2026-10-10 (later): two personas, Al Mulhim and Ilham (migration 0017, profile v3)

Same machine and toolchain. No new package. `osrip_dev` upgraded 0016 → 0017 after a `pg_dump`
backup (`osrip_dev-before-0017-20261010-115044.dump`). Every provider ran through its scripted
test double: **no live speech, LiveKit or avatar service was used** (`docs/assistant-personas.md`).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 500 passed** (474 at Stage 8) |
| of which: personas | `test_personas.py` | Pass: 23. Profile v3 personas with Microsoft-listed voices of the matching gender; seven invalid profiles refused (Ilham with a man's voice, Al Mulhim with a woman's, an invented voice, a wrong-language voice, two defaults, duplicate codes, a default that differs from the identity fields); portraits on disk and in `sources.json` with SHA-256; Ilham's Arabic greeting and feminine introduction; the about reply lists the three domains; prompts differ only in the identity block; SSML names the persona's voice and escapes text; End call deletes only the caller's room; the live voice check refuses without a service |
| of which: through the API | `test_personas.py` (integration) | Pass: profile and voice status publish both personas; a guest switches persona inside one conversation, the allowance goes 0 → 1 → 2 and status, content, evidence, calculations and citations are identical for both personas; replies keep their persona; unknown persona 422; read-aloud uses Aysha/Sonia for Ilham and Abdullah/Ryan for Al Mulhim (`X-Voice`); a signed-in choice is saved and seen by another session; the realtime token carries the persona; another visitor cannot end someone's call |
| Migration round trips | `test_migrations_roundtrip_integration.py` | Pass: 0014–0016 and 0017 down and up; replies kept; profile v3 removed and published again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **103 passed, 3 failed** in one run that took 2.5 h instead of about 11 min (the machine was heavily loaded or asleep). All three were phone-sized page-load timeouts (`quality.spec.ts` ×2, `phone.spec.ts` linking); **re-run alone, all 15 phone tests passed** |
| of which: personas and voices | `personas.spec.ts`, `voice-gender.spec.ts` | Pass: 3 + 4. Choosing Ilham changes name, portrait and introduction; facts and allowance unchanged across a switch; the choice survives a reload; a signed-in choice follows to another browser; Talk shows Ilham large, states "Fallback mode: push-to-talk, still portrait", has every control, requests the microphone only on Speak (audio only, never video), reads with `en-GB-SoniaNeural`, keeps the transcript when switching persona and releases the microphone on End call; browser fallback reads Ilham with Aysha/Sonia and says so when no woman's voice exists |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped (phone-only tests in the desktop project) |
| Frontend | `tsc -b`, `eslint .` | **Pass** (one accessibility finding in the persona picker fixed first) |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Live verification | `scripts/voice_acceptance.py` | **Pending**: needs Azure AI Speech; real-time and avatar need LiveKit, chosen voices and avatars, and approval of `livekit-client` |

## 2026-10-10: man's voice only, and the cinematic first-visit entrance

Same machine and toolchain as Stage 8. No new package; no migration. Details of the
entrance in `docs/ENTRANCE.md`.

| Area | Command | Result |
|---|---|---|
| Man's voice: server defaults | `pytest tests/test_voice_gender.py` | **Pass: 2 passed** (Abdullah, Omani Arabic; Ryan, British English; reported by the voice-status route) |
| Man's voice: browser fallback | `playwright test -c playwright.api.config.ts voice-gender` | **Pass: 2 passed**. With a realistic mix of Windows/Edge voices, answers are read with Microsoft Abdullah (Arabic) and Ryan (English). With only female voices installed, nothing is read aloud and the panel says why |
| Entrance | `playwright test entrance` (Edge; desktop and Pixel 7) | **Pass: 12 passed**: the full sequence frame by frame on the fake clock (carry, place in the centre, release, step aside, order and 4–6 s length), data loads behind it, immediate Skip, direct links kept, focus return, Replay from Settings and the footer, Arabic mirrored scene with unmirrored lettering, reduced motion, low-power device, scene that fails to load, phone fit |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped (phone-only tests in the desktop project) |
| Full-stack: navigation and voice | `playwright test -c playwright.api.config.ts interface voice-gender --project=chromium` | **Pass: 9 passed** (navigation label now "Account and settings") |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass**. The scene is its own chunk: `EntranceScene-*.js` 19.00 kB (6.35 kB gzip) |
| Backend lint | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Entrance performance | production build, Edge, CDP CPU throttling | 60 fps on desktop and with the CPU 4× or 6× slower (phone size); at 20× slower the watchdog shows the final frame; layout shift 0.0001; the first overview data card in a median 439 ms with the entrance open against 435 ms without |

Not re-run for this change: the whole backend suite (the backend change is comments and one
new test) and the whole full-stack suite (only `interface` and `voice-gender`).

## Stage 8, 2026-10-08: Al Mulhim programme (migrations 0013–0016)

Same machine (Windows 11, Python 3.13.5, Node 24, PostgreSQL 17.11, Edge). Every provider ran
through its scripted test double: **no live provider was tested** (the model and search keys
in `backend/.env` are rejected masked previews; no LiveKit project, speech key or avatar).
New backend package: `livekit-agents` 1.8.5 (approved). No new frontend package.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 474 passed** (365 at the start of the programme) |
| of which: identity | `test_assistant_profile.py`, `test_mulhim_identity.py` | Pass: 15 + 26 |
| of which: studies | `test_study_schema.py`, `test_studies_integration.py` | Pass: schema refuses 14 kinds of inconsistent documents and parameters outside the allowlist (injection-like strings, unknown keys, ranges); builders checked against hand-calculated values (10 % change; no change across a missing or unpublished year; CAGR 6.560 %; ranked governorates with "missing in the source" apart from "no published value"; monthly heatmap or "not available" for annual-only series; availability 100 + 300 − 20 = 380 t with 78.9 % / 26.3 % contributions; partner shares 50 / 33.3 / 16.7 % and sum of squares 0.389; scenario 121 × 1.1² = 146.41 labelled hypothetical; short series withheld from forecasting; programme gap 29 with no impact claim); CSV equals the table; reproduce identical; owner-only list and delete; CSRF for signed-in runs; assistant `run_study` stored with its message in English and Arabic |
| of which: research workflow | `test_research_workflow.py`, `test_research_progress_integration.py` | Pass: stale/undated flags; PDF page locator and document SHA-256; planted instructions in a page cannot redirect the reader (only search-result addresses, private addresses refused); method summary counts; real stages recorded for guests and users; Stop before a tool runs gives `cancelled`, not charged; other visitors and users get 404; **no leakage**: a held-out forecast does not change when its own or later values change |
| of which: migrations | `test_migrations_roundtrip_integration.py` | Pass: 0016 → 0013 → 0016 on a throwaway database; messages and requests kept (statuses mapped), tables and columns removed and recreated |
| of which: voice and guest limit | `test_voice_bridge.py`, `test_guest_channels_integration.py` | Pass: only signed `user:`/`guest:` identities; speech text without citation markers; spoken refusals; worker answers the latest utterance; one five-answer count across typed English and Arabic, research, compare and voice; greetings free after the limit; registration ignores requested roles and verified flags |
| Backend lint and format | `ruff check`, `ruff format` (app, tests) | **Pass** |
| Frontend | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass** (bundle-size warning pre-existing; 0 failing contrast pairs, light and dark) |
| Mock browser suite | `npx playwright test` (Edge) | **Pass: 19 passed, 2 skipped** (phone-only tests in the desktop project). Includes the entrance: both names and goals, Explore remembered, Skip/Escape, Replay with focus return, Arabic buttons, reduced motion |
| Full-stack browser suite | `npx playwright test -c playwright.api.config.ts` (Edge desktop and Pixel 7) | **Pass: 99 passed** (10.9 min). New: `studies.spec.ts` (4), `talk.spec.ts` (5); updated: `interface.spec.ts` (new navigation) |
| Talk workspace, repeated | `talk.spec.ts --repeat-each=3` | **Pass: 15 of 15** (text fallback, denied microphone, fake-microphone push-to-talk with review, Arabic transcription, failing speech service, interruption, microphone released after End call) |
| Development database | `alembic upgrade head` on `osrip_dev` after `pg_dump` backups | 0013 → 0016, nothing deleted |

Defects found and fixed in this stage are listed in `docs/TECHNICAL_REPORT.md` §6.

### Stage 8 Visual Studio run

`devenv OSRIP.sln /Run` (Visual Studio 2026 Community) started the launcher after the
preview servers were stopped. `GET /api/v1/health/ready`: ready, database ok, migration
`0016_request_progress`; `http://localhost:5173/` returned 200. Through the interface's proxy:
10 study kinds, Al Mulhim profile v2, real-time voice `configured: false` with 6 missing
settings (SDK installed). The model and web search are reported as configured because keys are
present, but those keys are rejected by the providers, so answers fall back to "unavailable".

## Increment 2026-10-05: research and decision-support assistant (migration 0012)

Same machine and toolchain as the 2026-10-02 increment. Migration 0012 (answer mode and
validated structured parts on assistant messages, `research` source class, saved research,
watchlist, alert rules and alert events). New optional extra `pdf`: **pypdf 6.19.0**
installed in the backend venv with the user's approval (pure Python, 395 kB wheel). **No live
provider was tested: there are still no keys for the language model or Brave Search**, and
no SMTP relay. Every provider ran through its scripted test double.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 365 passed** (30 new; the 335 existing tests pass unchanged with the stricter inline-citation check) |
| of which: credential isolation | `tests/test_settings_isolation.py` | **Pass: 1.** The suite removes `OSRIP_*` values from the shell and never reads `backend/.env` (`OSRIP_ENV_FILE=none`; the browser-test server does the same). Checked with a dummy `.env` and a dummy shell key: a normal process loaded both, the test suite neither |
| of which: PDF reading (with pypdf) | `tests/test_research_assistant_units.py` | **Pass: 2.** A generated one-page PDF gives its text with `[page 1]`, its title and its creation date (2024-05-02) as the publication date; a damaged file raises. Through `read_web_page`: the excerpt becomes `pdf_excerpt` evidence (`official`, `document_metadata`), and a reply citing 41,234 GWh from it passes the grounding check. A PDF with no extractable text returns `pdf_no_text` and adds no evidence |
| of which: research assistant units | `tests/test_research_assistant_units.py` | **Pass: 16.** Inline citations (a number needs an `[E#]` in its sentence or paragraph and must match that evidence; Arabic punctuation and digits); recommendation cards withheld for an invented "25% of fuel costs", a missing field, no citation or an unknown citation, and only allowed in Analyze/Research; drivers need one of the ten names, `evidence` needs citations, an assumption may use only the user's numbers; hypotheses cannot carry invented numbers; a conflict needs two values each written in its own source (swapped values dropped); HTML tables read as `Table:` and `cell \| cell` rows, scripts dropped; PDF without `pypdf` → `PdfUnavailable`; source classes official / international / research / secondary and their ranking; compound annual growth (booklet 4.375 %, 4-year case, order, zero start, missing ≠ zero, unit mismatch) and share of total (25 %, part > total, other year, missing) |
| of which: research assistant integration | `tests/test_zy_research_assistant_integration.py` | **Pass: 11.** Growth calculated by the backend in English and Arabic (4.375 %, shown 4.38 with its citation); an incorrect premise ("doubled") corrected first in both languages; missing verified data → "not enough published data", nothing invented; governorate comparison (published / missing in the source / no published value; national total shown and not divided; no wilayat inferred; unknown indicator 422) through the API and through Compare mode; Analyze cards with the invented saving and the uncited driver withheld and counted, none in Ask mode; conflicting official and news figures both reported with a bilingual search (`queries` in English and Arabic); unavailable services (Research without a search provider records `not_configured`; a failing search is reported; no model → labelled lookup); saved research snapshot, Markdown and HTML briefs (escaped title, `default-src 'none'`), rename, ownership 404s, guest 401, delete; source library hides unreviewed web sources from the public and shows pending counts to reviewers; watchlist alerts on publication (new data + above threshold, disabled rule silent, e-mail refused when delivery is disabled or the address unconfirmed, e-mail sent through the outbox after commit, unchanged republication silent, revised value reported as revised, mark read, other users 404) |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Migration 0012 | applied to the existing `osrip_dev` (additive, no reset); up → down to 0011 → up on a throwaway database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Secrets in the production bundle | search of `dist/` for provider hosts, header names and key names | **None found** |
| Mock-mode browser suite | `PW_CHANNEL=msedge playwright test` | **Pass: 15 passed**, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `PW_CHANNEL=msedge playwright test -c playwright.api.config.ts` | **Final run: 87 passed** (84 existing + 3 new in `research.spec.ts`: Analyze mode with a checked card, withheld count, a citation chip that moves focus to its evidence, save and HTML brief download; watch a series → alert bell → add, switch off and remove an alert rule; public source library, sign-in prompt for saved research, governorate comparison statuses and no sideways scroll). Earlier runs in this increment: 85 passed / 2 failed and 86 passed / 1 failed, all in the new spec (D25, D26); after the fixes the new spec passed 9 of 9 over three repeats |
| Screens (in-app browser, scripted assistant, `osrip_dev`) | Analyze answer at 375 px in English and Arabic; library and Geography in Arabic | Card, drivers (Hypothesis badge), withheld count and inline citation chips shown; Arabic labels and RTL mirroring; no horizontal overflow; 0 console errors. Geography compares the reference-pack governorates (2025 gross generation for five governorates; six "no published value"; national total and the combined Batinah/Dhahirah figure shown separately) |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D22 | With web research on by default, every reply would have listed "web search not configured" when no search key exists | The `not_configured` search record is added only in Research mode, where search was explicitly requested |
| D23 | On a phone the new answer-mode selector left the message list 24 px tall (it was already only about 190 px) | Below 640 px the chat scrolls as one column with the composer pinned at the bottom; messages get their full height |
| D24 | A reply citing a documented reference-pack note would have failed validation in the browser (bilingual `title`) | Evidence `title` accepts a string or EN/AR text |
| D25 | Alert on/off switch did not move until the server answered (found by the new browser test, intermittently) | The requested state is shown inside the click handler, and the saved rule replaces the cached one when the server answers |
| D26 | Comparison view lost its container when no governorate had data | The "no data" message is inside the same labelled region |

## Increment 2026-10-02: web research, talking AI Assistant, username accounts, navy/teal identity (API release 0.8.0)

Same machine (Windows 11 Pro; Visual Studio Community 2026 18.10 and 2022 17.14 with the
Python and Node.js workloads; Python 3.13.5 venv; Node 24.21; PostgreSQL 17 portable
cluster; Microsoft Edge). Migration 0011 (usernames, required password change, research
review queue). No new dependencies. **No live provider was tested: there were no keys for
the language model, Brave Search or Azure AI Speech.** Every provider was exercised through
its scripted test double or mocked HTTP.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 335 passed** (38 new) |
| of which: web research building blocks | `tests/test_research.py` | **Pass: 31.** Blocks file/ftp schemes, loopback, `localhost`, `.local`, private, link-local and metadata (169.254.169.254), IPv6 loopback, IPv4-mapped IPv6, a host resolving to a mix of public and loopback addresses (DNS rebinding), credentials in the URL and non-default ports. Pins the connection to the checked address with the original Host/SNI. Re-checks redirects to private addresses, refuses https→http, stops redirect loops after 3, enforces size and content-type limits. Strips scripts and forms, reads dates from metadata, classifies the source by host only (lookalikes such as `gov.om.evil.com` are secondary), and grounds web numbers in the cited text. Checks WAV format and duration, and drops evidence markers before speech |
| of which: release 0.8 integration | `tests/test_upgrade_integration.py` | **Pass: 7.** Username account: idempotent, viewer only, no contact details, hash not plaintext; a second run with another password changes nothing. A temporary password allows sign-in (case-insensitive username) but every permission is empty and endpoints answer 403 `password_change_required` until it is changed; weak or wrong-current passwords are refused; the old password stops working. The 12-character policy still applies to ordinary accounts. Web answer cites the NCSI fixture as `official` with dates; the candidate is queued with every provenance field and nothing is added to `observation`. A failed search is reported and **not charged**, and the web can be switched off per question. The review queue needs `research.review` (viewer 403); accepting needs a note; a second review gets 409; CSV export. Voice: transcription by a guest with CSRF (403 without), invalid audio 422; speech only for one's own message (another guest gets 404) |
| Guest allowance (unchanged rules, re-run) | `tests/test_guest_allowance_integration.py` | **Pass: 11** (five answers across languages, sixth refused before any provider call, failures not charged, replay not charged, race for the last slot) |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, scripts), launcher with `tools/ruff.toml` | **Pass** |
| Migration 0011 | applied to the existing `osrip_dev` (additive, no reset) and every throwaway test database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass**. Contrast now reads the tokens from `index.css`: 35 pairs × 2 themes, 0 failing |
| Secrets in the production bundle | search of `dist/` for provider hosts, header names and key names | **None found** |
| Mock-mode browser suite | `playwright test` | **Pass: 15 passed**, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `playwright test -c playwright.api.config.ts` | **84 passed** (80 existing + 4 new in `upgrade.spec.ts`: labelled AI Assistant face in English and Arabic; web citation labelled *Official data* with link, search-engine date and retrieval date, a failed search shown and not charged; data-manager review with required note; username account forced through the password change). Two later partial re-runs, made while the machine was heavily loaded (one took 50 minutes for 37 tests), each timed out once in the 42-page sideways-scroll test; run alone it passed in 80 s |
| Voice in a real browser | Edge with a fake microphone, scripted speech provider | The microphone is requested 0 times before **Speak** and once after. The recording uploads as `audio/wav`, the transcript fills the box and is **not sent**, and the answer is charged once. The reply audio plays: the avatar shows *processing* while it is fetched, then *speaking*. The loudness variable follows the audio (0 → 1.0 → 0.5) and the level bars scale with it; under reduced motion the bars stay still. **Stop speaking** returns to idle with level 0. A typed question plays nothing by itself |
| Screens | Edge screenshots at 1440 px (English and Arabic) and 390 px (reduced motion) | Navy/teal/ivory identity; Arabic panel mirrored (RTL); no horizontal overflow on the phone; 0 console errors |
| Launcher (VS Code task form) | `backend\.venv\Scripts\python.exe tools\start_osrip.py --no-browser` | **Pass**: found the existing data folder automatically, ready in 13 s at `http://localhost:5173/`; direct route and API proxy 200; hard kill ended only its own API and frontend |
| Pre-publication check | `python deploy\predeploy_check.py` | **25 passed, 2 warnings** (no search key, no speech key), 0 failed |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D14 | Recording captured silence in Chromium: the AudioContext was created after the permission prompt, outside the click, and stayed suspended | Created synchronously in the click and resumed (`lib/recorder.ts`) |
| D15 | The voice hook's unmount cleanup depended on the whole assistant UI object, which changes with every state; each state change therefore aborted the recording, the transcription request or browser speech recognition (also true before this release for browser recognition) | Effects depend only on the stable `setActivity`/`reportError` callbacks |
| D16 | Synthesised speech could have been silent if the AudioContext was suspended, because the audio element was routed through it | The element plays by itself; the level meter listens to `captureStream()`, so only the animation can fail |
| D17 | The avatar said "Speaking" while the audio was still being fetched | *Processing* until sound plays |
| D18 | `.vscode/launch.json` contained a broken entry (`http://Prj.SPRIP.com${cwd}`) | Replaced by a working Edge debug configuration with a no-browser start task |
| D19 | From Visual Studio, VS Code or a terminal the launcher could not find the existing database, which a packaged app had created in its virtualised AppData | `devdb.py` and the launcher discover it, and the launcher logs the folder used |
| D20 | `serve_public.py serve` never migrated, and the app role would lack rights on new tables | `serve` applies forward-only migrations and re-grants row access |
| D21 | Insights grid: an open question stretched its closed neighbour | `items-start` |

## Increment 0.8.0: reference pack, Windows startup, orb and guest allowance, forecast conditions, editorial images (2026-10-01)

Windows 11 Pro, Visual Studio Community 18.10.2 (Python and Node.js workloads), Python
3.13.5 (backend venv) and 3.14.7 (launcher), Node 24.21, PostgreSQL 17 portable cluster,
Microsoft Edge for browser tests. New dependencies: `motion` 13.4.4 (frontend) and
Pillow 12.3.0 (development tool for image derivatives only). Migrations 0009 (reference
pack) and 0010 (guest allowance).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 297 passed |
| of which: guest allowance (T26–T29) | `tests/test_guest_allowance_integration.py` | **Pass**: 11 — five answers across languages; sixth refused before any provider call (provider call count unchanged); failures and withheld replies not charged; failed-then-retried request id charged once; replay of a delivered reply not charged; request id reused for another question → 422; race of two requests for the last slot → exactly one 201 and one 403; database constraint refuses over-allocation; abandoned reservation released while the completed one stays charged; CSRF and cookie required; per-session abuse limit; lookup not charged; explicit link after sign-in (another account cannot claim it); signed-in replay and daily fair use |
| of which: reference pack and forecast conditions | `tests/test_zz_reference_pack_integration.py` | **Pass**: 8 — includes forecasts withheld for the 2022–2025 annual series (≤ 4 points against a 12-point minimum) and measured vs assumption conditions |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, tools) | **Pass** |
| Migration 0010 up, down, up | throwaway database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Secrets in the production bundle | search of `dist/` for key and secret patterns | **None found** |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 (first run) | `playwright test -c playwright.api.config.ts` | 76 passed, 4 failed — D9 (focus), one test interrupted by a hot reload, and one expectation still naming `frequency=` (now `period_kind=`); the failing specs then passed (assistant 14/14 on both projects; mixed frequency 6/6 with its prerequisite spec) |
| Full-stack browser suite (second run, final code) | same | **78 passed, 2 failed.** The laptop was suspended during the run (1.5 h instead of ~14 min; the trace shows a 1.2 s browser action inside a 609 s step); both failures are the two desktop assistant tests in that window. Re-run on desktop with the machine awake: **7/7 passed**. The phone project passed every assistant test in both runs |
| Launcher, command line | `tools/start_osrip.py` | **Pass**: start from stopped services (~9 s to ready); hard kill (job object ends API and frontend, watchdog stops PostgreSQL cleanly); occupied port 8010 → API on 8011 with the frontend proxying to it; second launcher detects the first; frontend killed → rest stopped gracefully, exit 1 |
| Visual Studio solution | `MSBuild OSRIP.sln` | **Pass**. Pressing F5 in the Visual Studio window was **not verified** (no access to the IDE interface; `devenv /Build` cannot load Python projects headlessly, even Visual Studio's own template) |
| Editorial images | `tools/build_editorial_images.py`, browser network log | Masters extracted unchanged (hashes match the booklet); 45 derivatives, none wider than its master; a 1366 px desktop requested 360 px (portrait) and 480 px (headers) AVIF files, a 390 px phone at 2× the 640 px portrait; no master requested |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D9 | Closing the assistant panel with Escape left focus nowhere: the panel was unmounted while the native dialog was open, so the browser could not restore focus (also true of the previous header button) | The panel mounts on first open and then stays mounted; closing goes through `dialog.close()` and focus returns to the orb explicitly. Covered by `assistant.spec.ts` (orb test) |
| D10 | Series cards overflowed a 375 px screen by 4 px (grid track `min-width: auto`) | `grid-cols-[minmax(0,1fr)]` on the series grid |
| D11 | The English locale file had been re-encoded (26 lines of mojibake, e.g. "Loadingâ€¦") by a tool step, and `docs/API.md` had 7 such lines | Repaired byte-exactly; a check for mojibake patterns finds none |
| D12 | README "Start" had lost an environment variable name; SPEC_CONFLICTS had two table rows joined on one line | Fixed |
| D13 | A guest per-minute limit of 4 could stop a fast reader before the five answers | Default raised to 10 (configurable; C48) |

One failure in the first run (the five-answer test on desktop) was caused by a code change
being hot-reloaded while the test ran; it passed on re-run. `zz-mixed-frequency.spec.ts`
depends on `workflow.spec.ts` running first (a pre-existing order dependency).

Not tested, and why: live Anthropic answers (no key; the scripted provider was used);
Arabic and English speech recognition quality (browser speech service, needs people and
target browsers); microphone permission prompts in a real browser (automated browsers
have no microphone; the code requests it only from the Speak button); Visual Studio F5;
Canva exports (need the owner's approval); any public deployment (none exists).

## Increment 0.6.0: forecasts, scenarios, connected services, interface (2026-09-26)

Same environment as below (Windows 11, Python 3.13.5, Node 24.17.0, PostgreSQL 17.11,
Microsoft Edge). No new dependencies. Migration 0007 (forecast outputs, error records).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (unit and integration, fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 242 passed |
| Backend lint and format | `ruff check`, `ruff format --check` | **Pass** |
| Migration 0007 up, down, up (dev database), and from empty in every test run | `alembic` | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, Pixel 7 and desktop | `playwright test -c playwright.api.config.ts` | **Pass**: 59 passed |
| Pre-publication check against `deploy/.env.example` | `python deploy/predeploy_check.py --env deploy/.env.example` | Repository checks **pass**. Configuration checks **fail as expected** on placeholders. No live check was run: there is no deployment |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D6 | The interface could not read a forecast run that included the seasonal model: its prediction schema allowed only the two older model names | Schema widened; covered by `zzz-forecast-run.spec.ts` |
| D7 | A history with no variation (a perfectly regular series) produced zero-width 80/95% intervals, which claims certainty | No interval is given in that case, and the explanation says why; unit tests added |
| D8 | At 360 px, the Trade calculations overflowed the screen by 30 px (grid track `min-width: auto`) | Grid track `minmax(0, 1fr)`; covered by the responsive matrix |

### Forecast evaluation evidence

**No official series is eligible.** No verified-source data is loaded, and annual
series since January 2022 can never reach the 12-value minimum. Every target shows
"Insufficient data to forecast." in verified mode (`geography-forecast.spec.ts`). The
evidence below exercises the method on a **declared synthetic monthly series** (the
one the browser test publishes, 2022-01 to 2024-12: a seasonal pattern + 4 GWh a month
+ a fixed irregular term). It is **not Omani data and says nothing about forecast
accuracy for Oman**. Reproduce it with `evaluate()` and `forecast_future()` in
`app/domain/forecasting.py`.

Rolling-origin backtest with an expanding window. First training window: 24 months.
Held-out periods: 2024-01 to 2024-12 (12 one-step forecasts per model, each using only
earlier data).

| Model | n | MAE (GWh) | RMSE (GWh) |
|---|---|---|---|
| Last-value baseline | 12 | 184.00 | 207.88 |
| Linear trend | 12 | 376.83 | 417.55 |
| Seasonal naive | 12 | **47.33** | 58.40 |

Selected: seasonal naive, because its MAE is strictly lower than the baseline's. The
horizon is 9 months (min(12, 12, 36/4)). First estimates, with the 95% and 80% bounds:

| Period | 95% low | 80% low | Estimate | 80% high | 95% high |
|---|---|---|---|---|---|
| 2025-01 | 1809.5 | 1834.9 | 1883.0 | 1931.1 | 1956.5 |
| 2025-02 | 1760.5 | 1785.9 | 1834.0 | 1882.1 | 1907.5 |
| 2025-03 | 1903.5 | 1928.9 | 1977.0 | 2025.1 | 2050.5 |

Formula checks in `tests/test_forecasting_v2.py` (12 tests) compare the baseline,
seasonal and OLS intervals with Python's `statistics` module.

### Device and browser coverage (actual)

| Covered | Not covered |
|---|---|
| Microsoft Edge (Chromium) desktop viewport; Pixel 7 emulation (412 px, touch). Responsive matrix at 360, 390, 768, 1024, 1366 and 1920 px, in English and Arabic, on 7 routes (no sideways scrolling). All 19 routes checked at the desktop and Pixel 7 sizes. Reduced motion (`emulateMedia`). Keyboard focus and skip link | Firefox and Safari/WebKit: engines not installed, and downloading them needs your approval. Real phones and tablets. Screen readers. Right-to-left review by a qualified Arabic speaker |

## Increment 0.5.0: accounts, assistant, 2022+ statistics, landing refresh (2026-09-26)

Same environment as below. New dependency: PyJWT 2.15 with cryptography 50.0 (ID-token validation).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (unit and integration, fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 219 passed |
| Backend lint and format | `ruff check`, `ruff format --check` | **Pass** |
| Migration 0006 up, down, up (dev database), and from empty in every test run | `alembic` | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 errors, 0 problems, built, 54/54) |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `playwright test -c playwright.api.config.ts` | **Pass**: 50 passed |

What the new tests verify:

| Requirement | Evidence | Result |
|---|---|---|
| Registration gives ordinary (Viewer) access only; password sign-in refused until the e-mail is confirmed | `test_identity_integration.py`, `e2e-api/accounts.spec.ts` | Pass |
| Verification, recovery and magic-link tokens expire, are single-use and cannot be revived (database trigger); wrong-purpose tokens fail | same | Pass |
| No account enumeration (identical replies); per-client and per-account request limits; e-mail features labelled when delivery is off | `test_identity_integration.py` | Pass |
| Password reset revokes existing sessions | same | Pass |
| Administrators grant roles explicitly; a new account cannot grant itself one | `test_identity_integration.py`, `accounts.spec.ts` | Pass |
| Google/Microsoft callbacks: PKCE, single-use state bound to the browser, signature, issuer (including the Microsoft tenant), audience, expiry, nonce, provider-confirmed e-mail; no merge on matching e-mail; linking needs a session; an identity cannot be taken over; last sign-in method protected; unconfigured providers reported, not shown as buttons | `test_oidc_integration.py` (14, scripted provider with real RSA keys), `accounts.spec.ts` | Pass |
| Assistant: cited answers carry value, period, source URL and dataset version; an invented number is withheld and the evidence shown; missing data leads to "no evidence", never zero; ambiguity leads to a clarifying question; Arabic in, Arabic out | `test_grounding.py` (7), `test_assistant_integration.py` (16), `assistant.spec.ts` | Pass |
| Assistant numerical accuracy: 2022→2023 change computed by OSRIP (205.25 ÷ 4,100.25 = 5.00579 %), inputs shown under "How calculated" | `test_anthropic_tool_loop_and_request_contract` | Pass |
| Assistant failures: HTTP 500, timeout, malformed response, not configured → a retryable "unavailable" reply | `test_assistant_integration.py`, `assistant.spec.ts` | Pass |
| Assistant permissions and limits: sign-in needed, own conversations only (404 otherwise), deletion removes messages, per-user limits (429), length limit, tools run in a READ ONLY transaction | same | Pass |
| Statistics from January 2022: earlier verified rows rejected; governorate, year and indicator filters; latest period shown per series; "Data unavailable" | `test_import_validation.py::test_verified_statistics_start_in_january_2022`, quality and section browser tests | Pass |
| NCSI conversion: 2022+ only, no unfinished years, exact region names only (all 75 registry areas covered), no guessing | `test_ncsi.py` (sample in an assumed layout, not NCSI data) | Pass |
| Arabic layout and phone usability of the new pages and the assistant panel | `quality.spec.ts` (17 routes × 2 languages × 2 viewports), `assistant.spec.ts` on Pixel 7 | Pass |

**Not run (and why):**

- The live Anthropic API, Google and Microsoft: no keys or client IDs exist.
- A real SMTP server: none is configured.
- A real NCSI export: downloading needs a data.gov.om account.
- Screen reader, Firefox/Safari, usability study: as in the earlier audit.

The NCSI converter's column names are an assumption until checked against a real file.

Defects found and fixed in this increment:

- A dynamic translation key made type-checking take more than 5 minutes; it now takes 10 s.
- The admin role checkbox did not respond until the server answered.
- The scripted test model read merged earlier questions.
- The shared e2e account hit the assistant limit.
- Several lint findings.

---

# Release audit (2026-09-25)

Every number below was produced by a command run on the date shown, in the
environment described. Nothing is carried over from earlier records without being
re-run. **Pass** = executed and met its expectation; **Fail** = executed and did not;
**Not run** = not executed (the reason is given). An empty cell is not a pass.

Code version: working tree of 2026-09-25 (API 0.4.1). The folder is not a git
repository (git is not installed here), so no commit hash can be recorded; see
[DEPLOYMENT.md](DEPLOYMENT.md#before-a-release).

## Environment

| Item | Value |
|---|---|
| Machine | Laptop, 13th Gen Intel Core i7-1355U (12 logical CPUs), 15.7 GB RAM |
| OS | Windows 11 Pro 10.0.26200 |
| Database | PostgreSQL 17.11 (official portable binaries, `backend/scripts/devdb.py`, localhost:55432) |
| Backend | Python 3.13.5, FastAPI 0.141.1, SQLAlchemy 2.0.54, psycopg 3.3.6 (full list: `backend/requirements.lock`) |
| Frontend | Node 24.17.0, React 19, TypeScript 6.0, Vite 8 (full list: `frontend/package-lock.json`) |
| Browser for automated tests | Microsoft Edge (Chromium) via Playwright, desktop 1280 px and Pixel 7 (412 px) profiles |

## Summary

| Area | Command | Result |
|---|---|---|
| Frontend types | `npx tsc -b` | **Pass**: 0 errors |
| Frontend lint (new: ESLint 9, typescript-eslint type-checked, React Hooks, jsx-a11y) | `npm run lint` | **Pass**: 0 problems, after fixing 4 findings (below) |
| Frontend production build | `npm run build` | **Pass**. Warning: main chunk 756 kB (221 kB gzip); map library in a separate lazily loaded chunk (1.06 MB, 286 kB gzip) |
| Colour contrast, light and dark | `npm run check:contrast` | **Pass**: 54 / 54 token pairs |
| Migrations on an empty database | `alembic upgrade head` → `downgrade base` → `upgrade head` | **Pass**: after `downgrade base` 0 tables, 0 enum types, 0 functions remain; re-upgrade reaches `0005_geography_forecasts` with 75 areas |
| Backend unit + integration tests | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 168 passed, 0 failed, 0 skipped (fresh database per run) |
| Backend lint and format | `ruff check app tests scripts`, `ruff format --check` | **Pass** |
| Interface, mock mode (no backend) | `npx playwright test` | **Pass**: 15 passed; 2 phone-only tests skipped on the desktop project by design |
| Full stack (browser → Vite proxy → FastAPI → PostgreSQL) | `npx playwright test -c playwright.api.config.ts` | **Pass**: 31 passed (25 desktop, 6 phone) |
| Complete journey upload → publication → report → revision | `e2e-api/journey.spec.ts` | **Pass** (part of the 31) |
| Performance workload | `python scripts/perf_workload.py` | Measured (see below). First run exposed 3 defects; results below are from the run after the fixes |
| Backup and restore | `python scripts/backup_restore_drill.py` | **Pass** |
| Deployment configuration (Docker) | — | **Not run**: Docker is not installed here |
| Screen-reader test (NVDA / VoiceOver), automated axe audit | — | **Not run** |
| Firefox and Safari | — | **Not run**: Chromium (Edge) only |
| Usability study with participants | — | **Not run**: needs college clearance (booklet 3.15, 4.6) |

## Checks requested for this audit

| Check | Evidence | Result |
|---|---|---|
| Backend calculation tests (booklet Table 4.2, T01–T03, T09) | `tests/test_calculations.py` (23), `tests/test_analysis_integration.py` (16) | Pass |
| Import validation (Appendix B.1) | `tests/test_import_validation.py` (35 functions, parametrised) | Pass |
| Server-side authorization (SEC01, T06), sessions, CSRF, throttling, suspension | `tests/test_auth_integration.py` (16), `e2e-api/workflow.spec.ts` "viewer is refused… directly" | Pass |
| Import rollback (T11) and duplicate publication | `test_failed_publication_rolls_back_and_keeps_previous_snapshot`, `test_repeated_publication_does_not_duplicate_observations`, `test_concurrent_publication_requests_insert_once` | Pass |
| Report consistency and data-mode preservation (FR05, T07) | `test_report_freezes_inputs_and_survives_a_later_publication`, `test_report_keeps_its_snapshot_after_a_revision_is_published`, `test_report_export_keeps_label_filters_assumptions_and_versions`, `e2e-api/journey.spec.ts` | Pass |
| English and Arabic (UX01, T08) | `e2e/shell.spec.ts` (T08 ×2), `e2e-api/workflow.spec.ts` "Arabic shows the same API values", `quality.spec.ts` (every page in both languages) | Pass |
| Mobile and desktop | `quality.spec.ts` on desktop and Pixel 7; `shell.spec.ts` @mobile tests | Pass after fixing D1 |
| Keyboard access and focus | `quality.spec.ts` (skip link, visible focus ring on navigation, keyboard-only selection moves focus to the result), `shell.spec.ts` (dialog focus trap, Escape, focus return) | Pass |
| Long Arabic labels | `quality.spec.ts`: 12 pages × 2 languages × 2 viewports, no horizontal overflow | Pass after fixing D1 |
| Units and negative numbers | `quality.spec.ts`: trade balance shows `−28,000,000 Omani rial (nominal)` in English and the same number with a leading minus, laid out left-to-right, in Arabic; generation change `2,100 gigawatt-hour` | Pass |
| Empty states | `quality.spec.ts` (no verified data, empty filter, "No data" areas), `shell.spec.ts` | Pass |
| Broken images | `quality.spec.ts`: every `<img>` on the landing page and the credits page has loaded (naturalWidth > 0) | Pass |
| Failed requests | `quality.spec.ts`: API 503 on calculations → explained error with "Try again" while observations still show; network failure on observations → error state | Pass |

## Defects found in this audit

| ID | Defect | Found by | Fix | Re-test |
|---|---|---|---|---|
| D1 | Geography page scrolled sideways by 229 px on a 412 px phone. Screen-reader-only labels (absolutely positioned) inside a horizontally scrolling table escaped their scroll container | `quality.spec.ts` (mobile) | Every `overflow-x-auto` container is now positioned (`relative`) | Pass on both viewports |
| D2 | Data Management mapping step copied server state into local state inside an effect (cascading renders) | ESLint `react-hooks/set-state-in-effect` | The step is keyed by the saved mapping; effect removed | Lint pass; `workflow.spec.ts` upload journey pass |
| D3 | `CardTitle` could render an empty heading; dialog backdrop click had no keyboard equivalent flagged | ESLint `jsx-a11y` | Heading children explicit; the backdrop handler is documented (Escape closes the dialog natively) | Lint pass |
| D4 | A section holding monthly and annual values of one indicator could not be viewed, and **report creation failed** (10 / 10 in the workload). The API correctly refused the mixed read, but the interface offered no way to choose a frequency | Performance workload | Frequency filter on every section (passed to observations, calculations, exports and reports); an explained "Choose one frequency" notice with one button per frequency (sections, overview, area details) | `test_mixed_frequencies_are_refused_with_a_reason_until_one_is_chosen`, `e2e-api/zz-mixed-frequency.spec.ts` pass; workload 0 errors |
| D5 | Change calculations were produced for every consecutive pair of periods: the electricity calculations response for 63 monthly series was 29 MB (median 1.16 s) | Performance workload | Changes cover the latest pair within the selected years, with a note; the year filters select an earlier pair | `test_changes_cover_the_latest_pair_and_an_earlier_one_by_filter` pass; response 286 kB, median 0.40 s |
| T-1 | Three end-to-end tests assumed which series is listed first; they broke once the journey test added data | Full-stack run | Tests now select series by name | Pass |

## Performance (booklet 4.7)

Workload, fully scripted in `backend/scripts/perf_workload.py`; raw record
`docs/perf/perf-2026-09-25.json`:

* Throwaway database with the booklet fixtures plus one generated **synthetic**
  import of 7,560 rows (63 wilayats × 120 months of electricity generation);
  7,572 observations, 2 published versions, 75 areas.
* API served by uvicorn over HTTP on 127.0.0.1, **one worker**, no reload; the
  client (httpx, keep-alive) and PostgreSQL run on the same laptop.
* OSRIP has no application cache. "Warm" means 5 warm-up requests per endpoint
  before measuring (database buffers warm).

Import, one run, each step timed separately:

| Step | Duration |
|---|---|
| Upload (491 kB CSV) | 42.5 ms |
| Validate 7,560 rows | 593 ms |
| Approve | 12.1 ms |
| Publish (one transaction) | 1,739 ms |

Sequential warm reads, 100 requests each:

| Endpoint | Median | p95 | Max | Errors | Response size |
|---|---|---|---|---|---|
| `GET /health` | 0.6 ms | 1.8 ms | 2.4 ms | 0 | 15 B |
| `GET /indicators` | 2.0 ms | 4.0 ms | 5.0 ms | 0 | 7.4 kB |
| `GET /observations` electricity, monthly (63 series) | 397 ms | 542 ms | 658 ms | 0 | 1.28 MB |
| `GET /observations` one wilayat | 10.0 ms | 13.3 ms | 13.5 ms | 0 | 20 kB |
| `GET /analysis/electricity` | 400 ms | 512 ms | 544 ms | 0 | 286 kB |
| `GET /analysis/food_security` | 18.6 ms | 21.1 ms | 22.3 ms | 0 | 10.6 kB |
| `GET /areas` | 7.2 ms | 9.7 ms | 11.2 ms | 0 | 32.8 kB |
| `GET /areas/coverage` | 14.1 ms | 15.6 ms | 16.4 ms | 0 | 19.5 kB |
| `GET /forecast/eligibility` (63 eligible monthly series) | 418 ms | 527 ms | 548 ms | 0 | 77.7 kB |

Concurrent mixed reads, 10 clients × 50 requests over the same endpoints: 500
requests, 0 errors, median 320 ms, **p95 4,687 ms**, max 8,040 ms, 7.4 requests/s
(67 s wall time).

Report generation (electricity, monthly), 10 reports: median 935 ms, p95 1,003 ms,
0 errors.

**What this shows and does not show.** In this environment every endpoint's p95
for a single client with warm database buffers was under 0.6 s. Under 10 concurrent
clients with one worker the p95 was 4.7 s, above the booklet's proposed two-second
target. The target is therefore **not demonstrated** in general: it held only for
single-client warm reads on this laptop. It has not been measured on server hardware,
with several workers, over a network, or with a real (non-synthetic) dataset.

The **first** run of the workload (before fixes D4 and D5) recorded: 100 % errors on
the mixed-frequency observations read, 10 / 10 report failures, a 29 MB calculations
response (median 1.16 s) and a concurrent p95 of 8.0 s with 56 errors. Those numbers
are superseded by the run above; they are kept here because they are how the defects
were found.

## Backup and restore (booklet 3.15)

`backend/scripts/backup_restore_drill.py`; raw record `docs/backup/backup-drill-20260925.json`.

| Step | Result |
|---|---|
| Source | `osrip_dev` at migration `0005_geography_forecasts`: 30 tables, 351 rows, 1 published version (the booklet fixtures) |
| Backup | `pg_dump -Fc`, 108,669 bytes, SHA-256 `06f0f2af…7b34390`, 0.36 s; stored outside the repository (`%LOCALAPPDATA%\OSRIP-dev\backups`) |
| Restore | `pg_restore --exit-on-error` into a newly created, separate database, 0.66 s |
| Fingerprint comparison (migration version, row count of every table, MD5 of every published version's observations, file checksums) | Identical |
| Known dataset version read through the application's own query service | 48,000 / 50,100 GWh, as expected |
| Integrity rules after restore | The trigger still refuses changes to published observations |
| Overall | **Pass**. The restored database was dropped afterwards |

Limits: a single-machine exercise with a small database. Point-in-time recovery,
off-site copies and a scheduled backup job were not set up or tested.
