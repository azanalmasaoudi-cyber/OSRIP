# Verification report: the integrated experience

**Date:** 11 October 2026.

**Scope:** everything built so far, checked together:

- the entrance;
- the two personas and their voices;
- the guest allowance;
- the governed AI and research service;
- the analytical workspace with live studies;
- startup from VS Code and Visual Studio.

**Status, stated plainly:**

- OSRIP is a **local academic prototype**. It is **not production-ready** and **not deployed**: there is no public URL.
- No live AI model, web search, speech service, SMS or e-mail provider has been verified, because no working credentials exist (see section 5).
- Everything below was run on this machine against the real FastAPI + PostgreSQL stack. Where an external service is needed, the scripted test providers stood in for it, and the screenshots label them.

The machine: Windows 11 Pro, Python 3.13.5 (backend), Node 24.21, PostgreSQL 17 (portable dev cluster), Microsoft Edge for the browser tests.

## 1. The nine demonstrations

The demonstration is a reproducible test suite: `frontend/e2e-demo/integrated.demo.spec.ts`, run with `frontend/playwright.demo.config.ts`.

- It runs the real stack in a throwaway database, with the scripted providers and the curated reference pack published as verified-source data (`OSRIP_E2E_REFERENCE_PACK=1`).
- Every step asserts what it shows and saves the screenshot named below to `docs/evidence/integrated/`.
- **Result: 6 tests, 6 passed** (11 Oct 2026, 1.3 min).

| # | What | How it was shown | Evidence | Result |
|---|---|---|---|---|
| 1 | The Omani character carries OSRIP in and places it in the centre | Fake clock, frame by frame. Asserted: he grips the sign while entering; the sign ends on the floor, centred on the stage within 3 px; the grips are released; the sign reads "OSRIP" | `01-entrance-carrying.png`, `02-entrance-placing.png`, `03-entrance-placed-in-centre.png`; also the 12 entrance tests of the mock suite | **Shown** |
| 2 | Bilingual objectives; Skip and Replay | Both names and the three goals in English and Arabic. Skip closes the entrance at once; the footer's "Replay introduction" plays it again; Skip closes it again | `04-entrance-bilingual-goals.png`, `05-entrance-replayed.png`; the mock suite also covers Replay in Settings, Arabic mirroring, reduced motion and the load-failure fallback | **Shown** |
| 3 | Choosing Al Mulhim or Ilham | The picker switches to Ilham; name, portrait and introduction change; Talk follows the choice | `06-persona-ilham-selected.png` | **Shown** |
| 4 | Male and female voice output | Each persona is configured with its own voice: Al Mulhim `ar-OM-AbdullahNeural` / `en-GB-RyanNeural` (male), Ilham `ar-OM-AyshaNeural` / `en-GB-SoniaNeural` (female). This is asserted through `/assistant/voice`, and Talk shows the voice in use. The browser fallback picks a voice of the persona's gender, or says none is installed (`voice-gender.spec.ts`) | `07-talk-ilham-female-voice.png`, `08-talk-mulhim-male-voice.png` | **Configured and tested; real voices not heard.** Azure AI Speech has no key, so the scripted provider plays a test tone. Live audio in these voices is **pending** |
| 5 | A sourced analysis on approved data, with external research where needed | The workspace in verified-source mode (reference pack): electricity mixes annual, year-to-date and monthly series, so the annual frequency is chosen in the workspace. Gross electricity generation shows the governorate view, which has real coverage. The assistant answers from the approved observations (`approved_official`). A Research-mode question adds labelled, unreviewed web sources from the scripted search | `09-workspace-verified-data.png`, `09b-workspace-governorates.png`, `12-research-sources-labelled.png` | **Shown.** The external search is the scripted test route: the stored Brave key is rejected |
| 6 | Table, chart and spoken explanation match | One validated dataset is drawn as both chart and table. Each spoken sentence highlights exactly one table row and one chart point, and the number in the sentence equals that row's value (asserted for sentences 1 and 2) | `10-narration-sentence-1-highlights-row.png`, `11-narration-sentence-2-highlights-row.png`; also `workspace.spec.ts` and `test_live_study.py` | **Shown** (audio is the test tone) |
| 7 | A provider or the microphone unavailable | Scripted model failure: "not available", Try again, the allowance unchanged. Microphone permission denied: explained, and typing still works. **Live check:** on the launcher-started site, which uses the stored but rejected Anthropic key, a guest question and a Research question both returned "unavailable" with 0 answers used, and the greeting stayed free | `13-provider-unavailable-not-charged.png`, `14-microphone-denied-typing-works.png`; live check in section 3 | **Shown** (scripted and live) |
| 8 | Guest limits after switching persona | Greeting free (5 left). Five answers alternating Al Mulhim and Ilham count 5 → 0. Then the sign-in prompt appears and the input is locked | `15-guest-limit-after-switching-persona.png`; backend: `test_allowance_rules_integration.py`, `test_personas.py` | **Shown** |
| 9 | Startup with the repository's VS Code and Visual Studio instructions | See section 4 | Launcher log and probes | **Shown for the launcher** (the command the VS Code task and Visual Studio's start button run). F5 inside the Visual Studio window was not operated from here |

Phone layout: `16-phone-study-tab.png` (Pixel 7: Data, Study and Assistant tabs).

## 2. Guest allowance rules

| Rule | Where it is enforced | Test |
|---|---|---|
| Five successful answers per guest session, shared across personas, languages, typed text, research and compare modes, and voice | Server: a conditional increment on the locked guest row, plus a table CHECK (`answers_used + answers_reserved <= answer_limit`) | `test_allowance_rules_integration.py` (all channels and both personas in one session); `test_guest_channels_integration.py`; `test_personas.py` |
| The fixed greeting never consumes an answer | Approved profile replies are not charged | Same; `test_mulhim_identity.py` |
| A completed answer counts once, even if playback is interrupted | Charged with the stored reply. Playback (whole reply or one narration segment), Stop after completion and reopening the study never charge | `test_allowance_rules_integration.py` (replay, three speech requests, Stop after completion, reopened study: still 1) |
| Failed generation and duplicate retries consume nothing extra | Failed replies are released, not charged. A repeated request id replays the stored reply | `test_allowance_rules_integration.py`, `test_guest_allowance_integration.py::test_failures_and_withheld_replies_do_not_consume`, `::test_retry_and_replay_are_not_charged_twice` |
| Atomic enforcement | Row lock plus conditional update plus CHECK constraint | `test_guest_allowance_integration.py::test_two_requests_race_for_the_last_slot`, `::test_the_database_refuses_more_than_the_limit` |
| After five, every channel is refused before any model call; the database holds exactly five charged requests and no reservation | Server | `test_allowance_rules_integration.py` |

Preserved and re-tested:

- **Independent e-mail and phone registration:** `test_identity_integration.py`, `test_phone_integration.py`, `phone.spec.ts`, `accounts.spec.ts`.
- **Server-side permissions and secrets:**
  - signup cannot grant roles or a verified state: `test_guest_channels_integration.py`;
  - provider readiness is for administrators, and the live provider test needs `user.manage`: `test_ai_providers_integration.py`;
  - keys are never sent to browsers.
- **Official/synthetic separation:**
  - `workflow.spec.ts` (verified mode never falls back to synthetic data);
  - data-status labels on every source;
  - production refuses scripted providers (`test_api_foundation.py`).

## 3. Tests actually executed (11 October 2026)

| Suite | Command | Result |
|---|---|---|
| Backend, all tests, fresh database | `OSRIP_RUN_DB_TESTS=1 pytest` (from `backend\`) | **551 passed**. A first run had 1 failure, a data-dependent count in a new test, which was fixed |
| Backend lint | `ruff check app tests scripts`, `ruff format --check app tests scripts` | **Pass** |
| Frontend typecheck | `npx tsc -b` | **Pass** |
| Frontend lint | `npm run lint` | **Pass** |
| Production build | `npm run build` | **Pass** (the bundle-size warning existed before) |
| Contrast | `npm run check:contrast` | **0 failing pairs** |
| Mock browser suite | `npx playwright test` | **27 passed**, 2 skipped (phone-only tests in the desktop project) |
| Full-stack browser suite | `npx playwright test -c playwright.api.config.ts` (desktop and Pixel 7) | **114 passed, 3 failed, 1 skipped** (37.1 min). The 3 failures were `phone.spec.ts:99`, `workspace.spec.ts:101` and `workspace.spec.ts:132`, all desktop. Each ran while the laptop, on battery at 12 %, was in Modern Standby (System log: 08:58–09:04, 09:08–09:13 and 09:13–09:18): the page timers froze, and the 30-second test timeouts expired. **Re-run alone: 3 passed** (36.8 s). The first attempt had not started at all: PostgreSQL was down (see section 4) |
| Demonstration suite | `npx playwright test -c playwright.demo.config.ts` | **6 passed** |
| Stored provider keys | free checks (model list, one-result search), outcomes only | Anthropic **rejected (HTTP 401)**; Brave **rejected (HTTP 422)**; OpenAI, Gemini, Azure Speech **no key** |
| Live provider-failure behaviour | guest questions against the launcher-started site | Greeting `profile`, 0 used; question `unavailable`, 0 used; Research `unavailable`, 0 used |
| Startup | `backend\.venv\Scripts\python.exe tools\start_osrip.py --check`, then `--no-browser` | **Ready in 13 s** (section 4) |
| Visual Studio projects | `tools\make_vs_projects.py` (now includes `e2e-demo`), then `MSBuild OSRIP.sln` (Visual Studio Community 18) | **Build succeeded, 0 warnings, 0 errors** |

Defects found and fixed during this verification:

1. The workspace had no frequency choice. Verified electricity and water mix annual, year-to-date and monthly series, so the workspace could only show "Choose one frequency", and its links left the page. It now has a Frequency filter, and the notice sets it in place.
2. Two verified series from different sources shared a React key, so a card could be dropped. The key now includes the source.
3. The demonstration needed a multi-year answer from the scripted model, so "Show the history of …" was added, along with the verified indicator "gross generation". This test-only provider is refused in production.

## 4. Startup (VS Code and Visual Studio)

All entry points run the same launcher, `tools/start_osrip.py`:

- **VS Code:** Terminal > Run Task > **OSRIP: start everything**, or Ctrl+Shift+B. It runs `backend\.venv\Scripts\python.exe tools\start_osrip.py`.
- **Visual Studio:** **OSRIP.Launcher** is the startup project. F5 runs `tools\start_osrip.py` with Visual Studio's Python.
- **No IDE:** `start-osrip.cmd`.

**Verified on 11 Oct 2026, from this session**, exactly as the VS Code task runs it (on ports 8020 and 5190, so as not to disturb anything else):

- `--check`: prerequisites OK, PostgreSQL running.
- Start:
  - reused the running PostgreSQL;
  - migrations at head (`0019_study_events`);
  - API ready;
  - listed the unconfigured services (voice, Google, Microsoft);
  - the frontend was ready and serving.
  - **"OSRIP is ready"** after 13 seconds.
- `/`, `/overview`, `/energy/water`, `/api/v1/health/ready`, `/api/v1/assistant/status` and `/api/v1/assistant/voice` all answered **200** through the frontend.
- **Stop** (the launcher process ended, as Stop Debugging does): the API and frontend it started stopped; PostgreSQL, which it had not started, kept running.

**Starts made by you, outside this session**, recorded in the launcher logs in the dev data folder:

- 10 Oct 19:28, and 11 Oct 07:52. The 07:52 start reported **"OSRIP is ready: http://localhost:5173/"** with migration `0019_study_events` and served assistant requests.
- Both ran the launcher with **Python 3.14.7**. The VS Code task and `start-osrip.cmd` use the backend's Python 3.13.5, and only Visual Studio's launcher uses its own interpreter. So this is consistent with a Visual Studio start, but the log does not name the IDE.

**Not verified from here:** pressing F5 inside the Visual Studio window, or running the task inside the VS Code window. Neither user interface can be operated from this environment.

**Seen afterwards:** the development PostgreSQL had stopped without a clean shutdown (stale `postmaster.pid`), probably when the session that started it ended. `backend\scripts\devdb.py start` brought it back with its data intact, and the launcher does the same on every start. Nothing was reset.

## 5. Services configured but not live-tested, and missing credentials or assets

| Service | State | What is needed |
|---|---|---|
| AI model: Anthropic Claude | Key present in `backend\.env` but **rejected (HTTP 401)**; the site says the assistant is unavailable | A valid API key from console.anthropic.com (`backend\scripts\set_provider_keys.py`, hidden prompt) |
| AI model or search: OpenAI | Implemented, **no key** | API key and model ids (an app subscription is not API access) |
| AI model or search: Google Gemini with Google Search grounding | Implemented, **no key** | API key and model ids |
| Web search: Brave Search API | Token present but **rejected (HTTP 422)** | A valid subscription token |
| Server speech: Azure AI Speech (the personas' male and female voices) | Implemented and tested with the scripted provider; **no key** | `OSRIP_SPEECH_KEY` and `OSRIP_SPEECH_REGION`; then run `backend\scripts\voice_acceptance.py` to hear each voice |
| Real-time voice and avatar (LiveKit) | Server side wired; **not configured, not run**. The browser client package is not approved | A LiveKit project, real-time voices and avatar choice, and approval of `livekit-client` |
| SMS (phone registration) | Scripted test provider only; no provider selected | A provider account and adapter settings |
| E-mail (SMTP) | Development outbox only | SMTP settings |
| Google and Microsoft sign-in | Not configured | OAuth client ids and secrets |
| Official statistics (NCSI) | Curated reference pack (346 records, checked to 27 Sep 2026) loaded; full files need a signed-in download | The team's NCSI download |
| Assets | The persona portraits are generated images supplied by the owner (the rights to Ilham's image are **still to be confirmed**). There is no produced 3D or video entrance asset (the scene is a code-drawn 2D rig), no licensed governorate boundaries (so no choropleth map), and no native 4K landscape images | The owner's confirmation; licensed boundaries, if a map is wanted |
| Deployment | `deploy/` prepared, **never run on a server; no public URL** | A server, a domain and the owner's authorisation |

No subscription was created and nothing was published.

## 6. Files changed

These are the files added or changed in the last three increments, all dated 10–11 Oct 2026. Earlier stages are listed in `docs/implementation-status.md` §7 and `docs/TEST_RESULTS.md`.

**Governed AI and research service** (migration 0018):

- **Backend:**
  - `alembic/sql/0018_provider_calls_{up,down}.sql`, `alembic/versions/0018_provider_calls.py`
  - `app/services/providers.py`, `app/services/assistant/{routing,provider,service,guest,tools}.py`
  - `app/services/research/{search,service}.py`
  - `app/core/config.py`, `app/models/{assistant,__init__}.py`
  - `app/api/routes/{assistant,monitoring}.py`, `app/services/monitoring.py`
  - `app/cli.py`, `app/main.py`
  - `scripts/{serve_e2e,set_provider_keys}.py`, `.env.example`, `pyproject.toml`
  - `tests/test_ai_providers{,_integration}.py`, `tests/test_research_workflow.py`, `tests/test_api_foundation.py`
- **Frontend:**
  - `src/api/{monitoring,assistant}.ts`
  - `src/components/common/ProviderReadiness.tsx`, `src/pages/HealthPage.tsx`
  - `src/components/assistant/{AssistantPanel,ResearchProgress}.tsx`
  - `src/i18n/locales/{en,ar}.ts`
  - `e2e-api/{governed-ai,upgrade}.spec.ts`
- **Docs and deployment:**
  - `docs/AI_PROVIDERS.md`, `docs/INTEGRATIONS.md`, `docs/API.md`, `docs/api/openapi.json`
  - `deploy/.env.example`
  - `docs/evidence/ai-providers/*`

**Analytical workspace and live studies** (migration 0019):

- **Backend:**
  - `alembic/sql/0019_study_events_{up,down}.sql`, `alembic/versions/0019_study_events.py`
  - `app/domain/study.py`
  - `app/services/assistant/{study_events,progress,tools,service,guest}.py`
  - `app/api/routes/{assistant,studies}.py`, `app/models/{assistant,__init__}.py`
  - `tests/test_live_study.py`, `tests/test_migrations_roundtrip_integration.py`
- **Frontend:**
  - `src/api/{studyEvents,studies,assistant}.ts`, `src/state/liveStudy.ts`
  - `src/components/workspace/{AssistantColumn,datasets,DatasetView,LiveStudyPanel,SelectionStudy,StudyParts,Tabs,useNarration}.*`
  - `src/pages/OverviewPage.tsx`
  - `src/components/common/{IndicatorCard,DataStatusBadge}.tsx`
  - `src/components/studies/{StudyCharts,StudyView}.tsx`
  - `src/components/assistant/{AssistantPanel,AssistantContext,AssistantOrb}.tsx`
  - `src/components/analysis/ReviewCards.tsx`
  - `src/lib/useMediaQuery.ts`, i18n
  - `e2e-api/{workspace,workspace-phone,assistant,upgrade,zz-mixed-frequency}.spec.ts`
  - `playwright.api.config.ts`
- **Docs:** `docs/WORKSPACE.md`, `docs/evidence/workspace/*`.

**This verification:**

- **Backend:**
  - `tests/test_allowance_rules_integration.py` (new)
  - `tests/test_live_study.py` (a series answer: one sentence, one row)
  - `app/services/assistant/provider.py` (scripted "history" path and the verified indicator keyword; test-only provider)
  - `scripts/serve_e2e.py` (opt-in reference pack for demonstrations)
- **Frontend:**
  - `playwright.demo.config.ts`, `e2e-demo/integrated.demo.spec.ts` (new)
  - `src/pages/OverviewPage.tsx` (frequency filter)
  - `src/domain/filters.ts` (series key includes the source)
  - `e2e-api/zz-mixed-frequency.spec.ts`
  - `tsconfig.node.json`, `eslint.config.js`, i18n
- **Tools:** `tools/make_vs_projects.py` (includes `e2e-demo`); `backend/OSRIP.Backend.pyproj` and `frontend/OSRIP.Frontend.njsproj` regenerated.
- **Docs:** this report, `README.md`, `docs/WINDOWS_STARTUP.md`, `docs/TEST_RESULTS.md`, `docs/evidence/integrated/*`.

Across these increments, the shared registers were also updated: `docs/SPEC_CONFLICTS.md` (C66–C77), `docs/implementation-status.md`, `docs/TRACEABILITY.md`. Local development configuration: `.claude/launch.json` (the `osrip-api-verify` and `osrip-frontend-verify` pair).

## 7. Windows startup, step by step

See the README section **"Start OSRIP on Windows (step by step)"**. It covers the one-time setup, starting from Visual Studio, VS Code or a double-click, stopping, adding provider keys and common problems.
