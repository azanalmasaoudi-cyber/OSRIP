# Implementation status: OSRIP and Al Mulhim

Register for the staged Al Mulhim programme (prompts 1–8).
Last update: **Stage 8, 8 October 2026** (all eight stages worked through). Later changes:
10 October 2026, Al Mulhim speaks only with a man's voice (server and browser), the
cinematic first-visit entrance (`docs/ENTRANCE.md`), two selectable personas, Al Mulhim
and Ilham (migration 0017, profile version 3, `docs/assistant-personas.md`), and the governed
AI and research service: OpenAI and Gemini adapters, routing policy, data status, limits and
provider readiness (migration 0018, `docs/AI_PROVIDERS.md`), and the analytical workspace with
live study events (migration 0019, `docs/WORKSPACE.md`). 11 October 2026: integrated
verification of all of these together, with nine demonstrations, an allowance-rules test,
a frequency filter in the workspace and startup evidence (`docs/VERIFICATION_REPORT.md`).

**Requirements reference.** `docs/OSRIP_Academic_Booklet_English_60_Pages.docx`, *Revised
English edition, 8 October 2026*. The file attached to the Stage 1 request,
`OSRIP_Academic_Booklet_English_60_Pages-2.docx`, is the earlier *4 October* edition and
contains none of the Al Mulhim, study, LiveKit or entrance requirements, so the 8 October
edition is used. The booklet specifies requirements; it is not evidence that anything works.

**Status words.** *Implemented*: the code exists. *Locally tested*: automated tests pass on
this machine against scripted or mocked providers. *Live-provider tested*: checked against the
real external service. *Deployed*: reachable on a public HTTPS address from another device.
**Nothing is live-provider tested or deployed.**

## 1. Repository facts

| Area | Finding |
|---|---|
| Frontend | React 19.2, TypeScript 6.0, Vite 8.3, Tailwind 4.3, react-router 8, TanStack Query 5, zod 4, i18next 26, `motion` 13.4.4, MapLibre 6. **No chart library**: custom SVG/HTML charts (decision C56). No new frontend dependency in this programme |
| Backend | Python 3.13.5 venv, FastAPI 0.141, SQLAlchemy 2.0, Alembic with reviewed SQL files, psycopg 3. Optional extras: `pdf` (`pypdf` 6.19, installed) and `voice` (`livekit-agents` 1.8.5, installed; approved 8 October 2026) |
| Database | PostgreSQL 17 portable cluster (`backend/scripts/devdb.py`, port 55432). Migrations 0001–**0019**. `osrip_dev` upgraded 0013 → 0016 (8 Oct), then 0016 → 0017, 0017 → 0018 and 0018 → 0019 (10 Oct) after `pg_dump` backups (in the dev home's `backups` folder, latest `osrip_dev-before-0019-20261010-204350.dump`); nothing reset or deleted |
| API | **116 paths, 134 operations** under `/api/v1` (`docs/api/openapi.json` regenerated 10 Oct after migration 0019; contract in `docs/API.md`) |
| Tests | Backend pytest (throwaway database per run); Playwright mock-mode (`frontend/e2e`) and full-stack (`frontend/e2e-api`, Edge desktop and Pixel 7) |
| Environment | Not a Git repository; Git is not on `PATH`. Since 14 October 2026 the project is at `C:\Users\Dell\Desktop\OSRIP`, outside OneDrive: Windows' Desktop was moved back from OneDrive to this PC. Until then it was in OneDrive, so earlier versions of `backend/.env` may remain in OneDrive's version history and recycle bin. While it was in OneDrive, the Vite file watcher sometimes missed edits |

## 2. Feature register

| Feature | Implemented | Locally tested | Live / deployed |
|---|---|---|---|
| **Al Mulhim identity** (names, meaning, linguistic note as interpretation, reference, introductions, greeting replies, purpose, domains, capabilities, limitations, memory policy) | Versioned, immutable profile (migrations 0013–0014, v2 active); loaded into every system prompt as trusted instructions; no write route; CLI publish/activate | `test_assistant_profile.py` (15), `test_mulhim_identity.py` (26), `mulhim.spec.ts` | Not live (model key rejected) |
| Greetings and introduction | «السلام عليكم» → «وعليكم السلام ورحمة الله وبركاته» + how to help; English equivalents; introduction once per conversation; never charged, works after the guest allowance is used | Same tests; `test_guest_channels_integration.py` | — |
| Memory separation and history control | Retention "until deleted" (owner's choice); memory view; delete one or all conversations (guests: their own) | `test_mulhim_identity.py`, `mulhim.spec.ts` | — |
| **Studies** (trend, growth, governorate comparison, seasonal profile, import dependence, partner concentration, data quality, scenario, forecast eligibility, programme record) | Typed allowlisted parameters; `osrip.study/1` validated result; stored runs with checksum, reproduce, CSV/JSON export (migration 0015); Studies page; assistant tool `run_study`, cited studies stored with the message | `test_study_schema.py` (unit), `test_studies_integration.py` (hand-calculated values: 10 % change, CAGR 6.560 %, availability 380 t, shares 50/33.3/16.7 %, gap 29, gaps never bridged), `studies.spec.ts` | Synthetic and reference data only |
| Programme assessment without causality | Records objective, baseline, latest, stated target and gap; limitations and next questions say what would be needed to judge impact | `test_studies_integration.py` | — |
| **Research progress and Stop** | Real stages written as they happen (migration 0016); Stop ends at the next step, reply `cancelled`, never charged; polled by the interface | `test_research_progress_integration.py`, `test_research_workflow.py` | — |
| Method summary, evidence locators, stale evidence | "How this answer was prepared" counted from the ledger; PDF page locators; SHA-256 of retrieved documents; "may be out of date" (> 3 years) and "undated" flags | `test_research_workflow.py` | Web search not live (token rejected) |
| Untrusted text and abstention | Page text labelled untrusted; only search-result addresses can be read; private addresses refused; host-based source class; unsupported numbers withheld | `test_research_workflow.py`, `test_research.py`, `test_research_assistant_units.py`, `test_zy_…` | — |
| Forecasts without leakage | Rolling-origin evaluation, baseline MAE/RMSE; a held-out prediction never changes when its own or later values change | `test_forecasting.py`, `test_forecasting_v2.py`, `test_research_workflow.py` | No reference series eligible: forecasts withheld with reasons |
| **Visual identity** | Deep emerald, ivory, restrained copper; light and dark | `check:contrast`: 0 failing pairs in both themes | — |
| Navigation | Overview; Domains; Analyse: Map, Studies, Scenarios, Sources; Assistant and outputs (decision C57) | `interface.spec.ts`, `shell.spec.ts` | — |
| **First-visit entrance** (10 Oct: cinematic scene, `docs/ENTRANCE.md`) | Code-driven 2D vector rig: an illustrated Omani man carries the OSRIP sign in, sets it down in the centre, lets go and steps aside (about 5 s; mirrored in Arabic); then both names, three bilingual goals, Explore / Skip from the first frame; remembered locally; Replay introduction in Settings (Account and settings page) and the footer; direct links kept; focus return; reduced-motion, low-power and load-failure still frames; no sound. **No 3D rig or produced video exists**: the missing asset is documented | `entrance.spec.ts` (12 tests, fake clock), real-time performance runs | — |
| **Two personas: Al Mulhim and Ilham** (10 Oct, `docs/assistant-personas.md`) | Profile v3 (migration 0017): names, introductions, portraits (owner-supplied generated images), Azure voice ids checked by gender (Abdullah/Ryan male; Aysha/Sonia female); choice on the account or in the browser; persona stored per reply; shared knowledge, tools, permissions, sources, history and guest allowance; Talk shows the chosen persona and states the fallback mode; End call deletes the LiveKit room; pronunciation check script | `test_personas.py` (23), `personas.spec.ts` (3), `voice-gender.spec.ts` (4) | **Live pending**: no Azure key, LiveKit project, real-time voices or avatar |
| **Governed AI and research service** (10 Oct, `docs/AI_PROVIDERS.md`) | OpenAI Responses API and Gemini Interactions API adapters (answering with function tools; OpenAI web search; Grounding with Google Search as a display-only route), beside the existing Anthropic and Brave adapters. Model ids configurable with no assumed default. Rule-based routing: numbers start with approved data, one provider per task, fallback only after a failure, cross-check only on request (not independent evidence). `data_status` on every evidence item. Provider summaries labelled and never queued. Grounded results shown verbatim with Search Suggestions, never given to a model, 2-year retention purge. Daily call limit and price-based budget per provider, `provider_call` log without prompts (migration 0018). Readiness view (unavailable / configured / tested / failed) with administrator-only live test. Production refuses scripted routes | `test_ai_providers.py` (21), `test_ai_providers_integration.py` (9), `test_api_foundation.py`, migration round trip, `governed-ai.spec.ts` (4), `upgrade.spec.ts` | **Live pending**: no working OpenAI, Gemini, Anthropic or Brave key |
| **Analytical workspace and live studies** (10 Oct, `docs/WORKSPACE.md`) | Overview redesigned as the workspace: domain, section, indicator, period, governorate and data-mode filters; cards with unit, period, source and stale flag; one validated dataset drawn as chart and sortable/filterable table; governorate view only with valid coverage (no boundary map exists); study panel (selection study via `POST /studies/preview`, assistant study); assistant column beside the analysis, tabs on phones. Live study events (migration 0019): validated stage, source, search, dataset, warning and completion events streamed as server-sent events, replayable; datasets provisional until completion; stale events ignored; narration generated from the validated findings and played sentence by sentence with row highlighting. 11 Oct: a frequency filter, so that mixed-frequency sections (verified electricity and water) can be analysed in place | `test_live_study.py` (17), migration round trip (0019), `workspace.spec.ts` (6), `workspace-phone.spec.ts` (1), `zz-mixed-frequency.spec.ts`, demo tests 5–6 on verified data | Server speech live pending (Azure); tested with the test speech provider |
| **Talk to Al Mulhim** | Full-viewport workspace (portrait and state, transcript, language, microphone, mute, stop speaking, End call, Close; results beside or as a sheet on phones); honest push-to-talk mode; static labelled portrait | `talk.spec.ts`: text fallback, denied microphone, fake-microphone push-to-talk with review, Arabic, failing speech service, interruption, microphone released on End call (5 tests, 3 repeats) | Not real-time |
| Real-time voice (LiveKit) | Token endpoint (one room, microphone only, 10 min), readiness with missing setting names, agent worker bridging to the ordinary answer service and guest allowance | `test_mulhim_identity.py` (tokens), `test_voice_bridge.py` (identity, speech text, refusals, worker answer step, allowance and permissions) | **Not configured, not run** (no LiveKit project; `livekit-client` not approved) |
| Avatar | Comparison and acceptance test (`docs/avatar-providers.md`) | — | **None selected**; no lip-sync claim |
| **Guest allowance** | Five successful answers per guest session across text, research mode, compare mode, both languages, both personas and voice; greetings, failures, withheld and cancelled replies never charged; replays and playback (whole reply or one narration segment) never charged | `test_guest_allowance_integration.py` (11), `test_guest_channels_integration.py` (3), `test_allowance_rules_integration.py` (11 Oct: every rule in one session, including the database check of exactly five charged requests), `test_voice_bridge.py`, demo test 8 | — |
| Registration | Independent e-mail and phone routes kept; extra fields (roles, permissions, verified flags) ignored; Viewer role only; unverified e-mail cannot sign in | `test_identity_integration.py`, `test_phone_integration.py`, `test_guest_channels_integration.py` | No live e-mail or SMS |
| Existing platform (imports, calculations, rules, scenarios, library, alerts, comparisons, monitoring) | Unchanged in behaviour | Full suites below | Local only |
| Windows startup | Launcher applies forward-only migrations, so 0014–0016 are applied on first start | Visual Studio run, §6 | Local only |
| Publication | `deploy/` files exist | — | **Not deployed; no public URL** |

## 3. Constraints and decisions

1. The stack is unchanged. Every migration has up and down SQL files; 0014–0016 are
   round-tripped by `test_migrations_roundtrip_integration.py` (down keeps messages and
   requests, mapping later statuses to earlier ones).
2. No chart library (C56), no `livekit-client` (C60): neither was approved.
3. Providers are optional: each missing provider leaves statistics browsing and text answers
   working and reports its state without secrets.
4. Tests never read credentials (`OSRIP_ENV_FILE=none`, `OSRIP_*` removed).
5. Open decisions are listed in `docs/SPEC_CONFLICTS.md` (C56–C61 added in this programme).

## 4. Provider register (no secret values recorded)

| Provider | Setting names | State, 8 October 2026 (re-checked 11 October: unchanged) |
|---|---|---|
| Anthropic (model) | `OSRIP_ANTHROPIC_API_KEY`, `OSRIP_ASSISTANT_MODEL` | Key present but **rejected** (HTTP 401): a 21-character masked preview, not the full key. Re-checked on 11 Oct: still 401 |
| Brave Search | `OSRIP_RESEARCH_API_KEY` | **Rejected** (HTTP 422 `SUBSCRIPTION_TOKEN_INVALID`): same masked value. Re-checked on 11 Oct: still 422 |
| OpenAI (answering, web search) | `OSRIP_OPENAI_API_KEY`, `OSRIP_OPENAI_MODEL`, `OSRIP_OPENAI_SEARCH_MODEL` | Not configured (10 Oct). A ChatGPT subscription is not API access |
| Google Gemini (answering, Google Search grounding) | `OSRIP_GEMINI_API_KEY`, `OSRIP_GEMINI_MODEL`, `OSRIP_GEMINI_SEARCH_MODEL` | Not configured (10 Oct). A Gemini app subscription is not API access |
| Azure AI Speech (push-to-talk) | `OSRIP_SPEECH_KEY`, `OSRIP_SPEECH_REGION` or `OSRIP_SPEECH_ENDPOINT` | Not configured (browser speech used where available) |
| LiveKit (real-time voice) | `OSRIP_VOICE_REALTIME_ENABLED`, `OSRIP_LIVEKIT_URL`, `OSRIP_LIVEKIT_API_KEY`, `OSRIP_LIVEKIT_API_SECRET`, `OSRIP_VOICE_STT_MODEL`, `OSRIP_VOICE_TTS_MODEL_AR`, `OSRIP_VOICE_TTS_MODEL_EN` | Not configured; SDK installed |
| Avatar | `OSRIP_VOICE_AVATAR_PROVIDER`, `OSRIP_VOICE_AVATAR_ID` | None selected |
| E-mail (SMTP) | `OSRIP_EMAIL_BACKEND=smtp`, `OSRIP_SMTP_*` | Development outbox only |
| SMS | `OSRIP_SMS_*` | No provider selected; scripted test provider |
| Google / Microsoft sign-in | `OSRIP_GOOGLE_*`, `OSRIP_MICROSOFT_*` | Not configured |
| NCSI data portal | (manual download) | File import only |
| OpenFreeMap | `VITE_MAP_STYLE_URL` | Used without a key |

Enter keys without displaying them: `backend\.venv\Scripts\python.exe backend\scripts\set_provider_keys.py`.

## 5. Verification results

| Check | Stage 1 baseline | Stage 8 |
|---|---|---|
| Backend tests | 365 passed | **474 passed** (no failures); 10 Oct with personas: **500 passed**; with governed AI (0018): **532 passed**; 11 Oct with the workspace (0019): **549 passed**; 11 Oct integrated verification: **551 passed** |
| Backend `ruff check` / `ruff format` (app, tests) | Pass | Pass. Pre-existing outside scope: `alembic/env.py` import order |
| Frontend `tsc -b`, `eslint .`, `vite build` | Pass | Pass (bundle-size warning pre-existing). ESLint takes about 2 minutes on OneDrive |
| Contrast (both themes) | 0 failing | 0 failing (new palette) |
| Mock browser suite | — | **19 passed**, 2 skipped (phone-only tests in the desktop project). 10 Oct, with the cinematic entrance: **27 passed**, 2 skipped |
| Full-stack browser suite | 87 passed | **99 passed** (10.9 min); 10 Oct: 103 passed and 3 phone page-load timeouts in a 2.5 h run on a loaded machine, all passing when re-run alone (106 tests); 10 Oct with governed AI: **110 passed** (18.5 min); 11 Oct with the workspace: **117 passed** (16.4 min); 11 Oct integrated verification: 114 passed and 3 failed during laptop standby (on battery), all 3 passing when re-run alone (118 tests). Demonstration suite: **6 passed** |
| Migrations | 0013 round trip | 0014–0016 down to 0013 and up again (automated) |

## 6. Visual Studio run

8 October 2026: `devenv OSRIP.sln /Run` started the launcher; API ready (database ok,
migration `0016_request_progress`), website 200, studies catalog (10 kinds), profile v2 and
real-time readiness (not configured, 6 settings missing) answered through the proxy. Details:
`docs/TEST_RESULTS.md`, "Stage 8 Visual Studio run".

11 October 2026:

- The launcher, run as the VS Code task runs it, was ready in 13 s at migration 0019.
- The owner's own starts (10 Oct 19:28, 11 Oct 07:52) reached "OSRIP is ready" under Visual
  Studio's Python 3.14.7.
- F5 inside the Visual Studio window was not operated from here (`docs/WINDOWS_STARTUP.md`).

## 7. Files changed in stages 2–8 (main)

| Area | Files |
|---|---|
| Identity | `backend/app/knowledge/assistant_profile_v2.json`, `alembic/versions/0014_*`, `alembic/sql/0014_*`, `services/assistant/{profile,service,guest}.py`, `api/routes/assistant.py`, `frontend/src/components/assistant/MulhimPanels.tsx` |
| Studies | `app/domain/study.py`, `app/services/studies.py`, `app/api/routes/studies.py`, `alembic/*0015_studies*`, `models/research.py`, `services/assistant/{tools,grounding,provider}.py`, `frontend/src/api/studies.ts`, `frontend/src/components/studies/*`, `frontend/src/pages/StudiesPage.tsx` |
| Research workflow | `alembic/*0016_request_progress*`, `services/assistant/progress.py`, `services/research/{service,pages,sources}.py`, `frontend/src/components/assistant/ResearchProgress.tsx` |
| Interface | `frontend/src/index.css`, `components/layout/{SidebarNav,AppShell,Entrance}.tsx`, `scripts/check-contrast.mjs`, i18n `en.ts`/`ar.ts` |
| Voice | `app/voice/{bridge,agent}.py`, `services/voice_realtime.py`, `services/assistant/guest.py` (`verified_guest_id`), `frontend/src/pages/TalkPage.tsx`, `AssistantPanel.tsx` (recorder timing fixes) |
| Tests | `test_study_schema.py`, `test_studies_integration.py`, `test_research_workflow.py`, `test_research_progress_integration.py`, `test_migrations_roundtrip_integration.py`, `test_voice_bridge.py`, `test_guest_channels_integration.py`, `e2e/entrance.spec.ts`, `e2e-api/{studies,talk}.spec.ts` |
| Docs | `README.md`, `backend/.env.example`, `docs/{API,SPEC_CONFLICTS,TEST_RESULTS,implementation-status,TECHNICAL_REPORT,avatar-providers,دليل_البدء}.md`, `docs/api/openapi.json` |
