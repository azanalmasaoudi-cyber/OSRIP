# OSRIP: Al Mulhim programme, technical report (stages 1–8)

Date: 8 October 2026. Scope: the eight staged "OSRIP Al Mulhim implementation prompts".
Requirements reference: the OSRIP academic booklet (8 October edition). The booklet states
requirements; it is not evidence that anything works.

**Status words used throughout.** *Implemented*: the code exists. *Locally tested*: automated
tests pass on this machine against scripted or mocked providers. *Live-provider tested*:
checked against the real external service. *Deployed*: reachable on a public HTTPS address
from another device. **Nothing in this report is live-provider tested or deployed.**

## 1. Summary

| Stage | Outcome |
|---|---|
| 1. Inspection and foundations | Repository inspected; baseline recorded; Al Mulhim profile v1 stored as an immutable, versioned record (migration 0013) |
| 2. Persistent identity | Profile v2 active (migration 0014); greetings, one-time introduction, "who are you" answered from the profile, never charged; memory view and deletion; identity survives restarts and cannot be changed by chat or web text |
| 3. Studies | Ten allowlisted study kinds with typed parameters; one validated result schema (`osrip.study/1`) for cards, tables, charts, exports and the assistant; stored, reproducible runs (migration 0015); Studies page |
| 4. Research workflow | Real progress stages and Stop (migration 0016); method summary per answer; evidence locators, document digests, stale/undated flags; prompt-injection, abstention and forecast-leakage tests |
| 5. Interface | Emerald/ivory/copper tokens (contrast-checked); navigation Overview / Domains / Map / Studies / Scenarios / Sources; first-visit entrance with Explore/Skip and Replay (10 Oct: cinematic scene with an animated 2D character, `docs/ENTRANCE.md`) |
| 6. Talk to Al Mulhim | Full-viewport workspace (push-to-talk, labelled static portrait); LiveKit token endpoint and agent worker wired to the ordinary answer service; avatar provider comparison. **Not run against LiveKit**. 10 Oct: two personas, Al Mulhim and Ilham (profile v3, migration 0017, `docs/assistant-personas.md`): own names, portraits and gender-checked voice ids; shared knowledge, history and allowance; End call deletes the room |
| 7. Accounts and guest limit | Independent e-mail and phone registration kept; one five-answer guest count across text, research, both languages and voice; signup cannot grant roles or a verified state |
| 8. Release | Full test runs, documentation, Arabic beginner guide, this report |

## 2. Architecture changes

Stack unchanged: React 19 / TypeScript / Vite / Tailwind, FastAPI, SQLAlchemy 2, PostgreSQL 17,
Alembic running reviewed SQL files. One new backend dependency, approved by the project
owner: `livekit-agents` 1.8.5 (optional extra `voice`). No new frontend dependency.

**Migrations** (each with an up and a down SQL file; 0014–0016 round-tripped on a throwaway
database by `test_migrations_roundtrip_integration.py`; applied to `osrip_dev` after a
`pg_dump` backup, nothing deleted):

| Migration | Content |
|---|---|
| 0013 `assistant_profile` | Versioned identity; content immutable (trigger); one active version (partial unique index) |
| 0014 `mulhim_identity` | Message statuses `profile` and `cancelled`; profile v2 active |
| 0015 `studies` | `study_run`: kind, schema version, parameters, data mode, dataset versions, result, SHA-256, owner (user or guest), message link |
| 0016 `request_progress` | `assistant_request.progress` (stages) and `cancel_requested_at`; request state `cancelled` |

**API**: 107 paths, 124 operations (`docs/api/openapi.json`, regenerated). New groups:
`/assistant/profile`, memory and deletion, request progress and cancel (user and guest),
real-time voice readiness and session, and `/studies` (catalog, run, list, get, reproduce,
CSV/JSON export, delete). Contract: `docs/API.md`.

**Main new modules**

- `backend/app/services/assistant/profile.py`: profile validation, checksum, intent detection with Arabic normalisation, approved replies.
- `backend/app/domain/study.py`, `backend/app/services/studies.py`: result schema with consistency checks; ten builders using the existing query service and `domain/calculations.py`.
- `backend/app/services/assistant/progress.py`: stage tracker writing in short independent transactions; cancellation checks before every model and tool call.
- `backend/app/voice/bridge.py`, `backend/app/voice/agent.py`: caller identity from the signed room token, speakable text, answers through the ordinary service; LiveKit worker.
- Frontend: `pages/StudiesPage.tsx`, `components/studies/*`, `components/assistant/ResearchProgress.tsx`, `components/layout/Entrance.tsx`, `pages/TalkPage.tsx`.

## 3. Design decisions

1. **Identity is data, not prompt text.** The profile is a validated JSON document stored with
   a checksum; the active version is read for every answer. There is no write route; new
   versions are published by an operator command. Greetings and identity questions are
   answered from it without a model call, so they cost nothing and cannot drift.
2. **One study result for everything.** Builders return a document that is validated before
   it is stored or shown; numeric columns must carry units, charts may only reference table
   columns, and series are labelled observed, calculated, forecast or scenario. Tables,
   charts, downloads, spoken summaries and the assistant all read the same object.
3. **Comparisons never bridge gaps.** A trend compares a period only with the period
   immediately before it (previous year, same months for year-to-date, previous month or
   quarter); a missing or unpublished neighbour gives "no change shown", never a jump across
   years.
4. **Progress is evidence of work, not decoration.** A stage is written only when that kind
   of tool actually runs; there are no timers. The method summary is counted from the
   evidence ledger.
5. **Untrusted text stays data.** Web and PDF text is passed to the model labelled untrusted;
   only addresses from search results can be read (by evidence id), the fetcher refuses
   private and link-local addresses, and the source class comes from the host name, never
   from the page.
6. **Voice uses the same door as text.** The voice agent answers through the same service and
   guest reservation path; the guest identity comes from the server-signed room token
   (`verified_guest_id`), never from what is said.
7. **No chart library.** ECharts was proposed but not approved, so the existing custom SVG /
   HTML charts were extended (line with gaps for missing values, ranked bars that mirror in
   Arabic, heatmap as an accessible table). Every chart has the same values in a table.
8. **Entrance remembered locally only.** A `localStorage` flag; nothing is sent to the server.
   If storage is blocked the entrance is not shown, so nobody is trapped behind it.

## 4. Security and privacy measures added

- CSRF: a signed-in caller of `POST /studies` must send the token (`optional_session`).
- Progress and cancel routes return 404 for anyone else's request (user id or guest session).
- LiveKit tokens: one room, microphone only, no create/admin/list/record rights, 10-minute
  life, agent dispatched by name; credentials only on the server.
- The voice agent refuses participants without an `user:`/`guest:` identity, checks the
  account status, the forced password change and `assistant.use`.
- Registration ignores any extra fields (roles, permissions, verified flags); tested.
- Tests never read real credentials (`OSRIP_ENV_FILE=none`, `OSRIP_*` removed).

## 5. Verification (8 October 2026, this machine)

| Check | Result |
|---|---|
| Backend `pytest` (unit + integration, throwaway database) | **474 passed** (365 at the start of the programme) |
| Backend `ruff check` / `ruff format` (app, tests) | Pass |
| Frontend `tsc -b`, `eslint .`, `vite build`, `check:contrast` | Pass (bundle-size warning pre-existing; 0 failing contrast pairs in both themes) |
| Mock-mode browser suite (`frontend/e2e`, Edge) | **19 passed**, 2 skipped (phone-only tests in the desktop project) |
| Full-stack browser suite (`frontend/e2e-api`, Edge desktop and Pixel 7) | **99 passed** (10.9 min; 87 at the start of the programme) |
| Visual Studio `devenv OSRIP.sln /Run` | API ready at migration 0016; website 200; new endpoints answer through the proxy |
| Talk workspace tests repeated three times | 15 of 15 passed |
| Visual checks (built-in browser) | Studies (English and Arabic, line, ranked bar, heatmap), method summary in Arabic, entrance, emerald theme light and dark, Talk workspace at 1366 px and 375 px |

## 6. Defects found and fixed during the work

| Defect | Fix |
|---|---|
| Programme assessment: the gap to target was always empty (the target was given the latest year's period, so the overlap guard refused it) | The target uses its own year; a passed target year is explained instead |
| Progress stages were stored as JSON strings inside the array (double encoding) | Bind the entry as a JSONB parameter |
| Pressing Stop before the microphone finished opening was ignored, leaving it on | A pending stop is applied as soon as the recorder opens |
| Ending a call while the microphone was opening could leave it live | Every cancel bumps an attempt counter; a late-opening recorder is closed at once |
| The Talk workspace was trapped inside the page (the route transition's transform contains fixed layers) | Rendered in a portal; the app behind is made inert |
| A new test queued the same research candidate as a later module (de-duplicated by source) | The test removes the candidate it created |
| Test data: an assumed CSV column header, an out-of-range year, a wrong message count | Corrected in the tests |

## 7. What is not done or not verified

| Item | State |
|---|---|
| Live AI answers and live web search | The keys in `backend/.env` are rejected (HTTP 401 and 422): they are masked previews, not full keys. Only scripted providers have been used |
| Real-time voice | Worker and token endpoint implemented; no LiveKit project, speech models or keys; the browser LiveKit client (`livekit-client`) is not approved, so push-to-talk is used |
| Talking avatar | None selected or tested (`docs/avatar-providers.md`); the portrait is static and says so |
| Forecasts | No reference series meets the history requirement, so forecasts are withheld with reasons |
| SMS, SMTP, Google, Microsoft | Not configured |
| Deployment | **No public URL.** Nothing has been deployed |
| Visual Studio F5 | Started with `devenv OSRIP.sln /Run` from this environment; pressing F5 inside the IDE window could not be operated from here |

## 8. Recommended next steps

1. Enter the full Anthropic and Brave keys with `backend/scripts/set_provider_keys.py` and run
   the live checks (one answer, one web search) before any demonstration that claims them.
2. Decide on real-time voice: a LiveKit project (cloud or self-hosted), Arabic and English
   speech models, approval of `livekit-client`, then the acceptance test in
   `docs/avatar-providers.md` before any lip-sync claim.
3. Choose hosting and DNS; run the pre-deployment check; only then publish a URL.
4. Review the open decisions in `docs/SPEC_CONFLICTS.md` (navigation labels, chart library,
   retention policy).
