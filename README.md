# OSRIP — Oman Smart Resource Intelligence Platform

Bilingual (English / Arabic) academic prototype for inspecting electricity, water,
food-availability and trade indicators, comparing compatible observations, and
identifying questions that need investigation. It does **not** operate utilities or
make government, investment or business decisions. Specification: the OSRIP academic
booklet (design-stage edition).

> **Status (11 Oct 2026, migration 0019): a local academic prototype. It is not
> production-ready and not deployed.** Built so far:
>
> - the entrance (the Omani character carries OSRIP in and places it in the centre; bilingual
>   goals; Skip and Replay);
> - two assistant personas, **Al Mulhim** (male voice) and **Ilham** (female voice);
> - five free guest answers, counted on the server;
> - governed AI and research providers;
> - the **analytical workspace** on Overview, whose live study keeps the table, the chart and
>   the spoken explanation on one validated dataset.
>
> What was demonstrated and tested, and what was not:
> [`docs/VERIFICATION_REPORT.md`](docs/VERIFICATION_REPORT.md).
>
> Other references:
>
> - register: [`docs/implementation-status.md`](docs/implementation-status.md);
> - automated results: [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md);
> - Arabic guide: [`docs/دليل_البدء.md`](docs/دليل_البدء.md);
> - technical report: [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md).
>
> The prototype is **not complete**:
>
> - the AI models (Anthropic, OpenAI, Gemini), web search (Brave, or Gemini/OpenAI search)
>   and server speech (Azure AI Speech) are implemented and tested only with scripted
>   providers;
> - the Anthropic key and Brave token in `backend/.env` are **rejected** by those services
>   (checked 11 Oct 2026: HTTP 401 and 422), and there are no OpenAI, Gemini or Azure keys.
>   So **no provider has been tested live**, the personas' real voices have not been heard,
>   and without valid keys the interface says each service is unavailable;
> - real-time voice (LiveKit Agents) is wired but **not configured or run**: no LiveKit
>   project, speech models or avatar provider exist, and the browser's LiveKit client is not
>   installed. Talk to Al Mulhim therefore uses push-to-talk with a labelled **static**
>   portrait; nothing claims lip synchronisation ([`docs/avatar-providers.md`](docs/avatar-providers.md));
> - official statistics: a curated reference pack (346 records, checked to 2026-09-27) is
>   loaded; the full NCSI files still need a signed-in download by the team;
> - Google/Microsoft sign-in and e-mail are built but not configured; **no SMS provider
>   has been selected**, so phone registration is shown as unavailable;
> - images: the two persona portraits are generated images supplied by the owner (fictional
>   and labelled). The rights to Ilham's image are **still to be confirmed**. The entrance is
>   a code-drawn 2D scene, not a 3D or video asset. The landscape set is still the booklet
>   illustrations, **none is native 4K**, and the Canva exports need the account owner's
>   approval ([`docs/assets.md`](docs/assets.md));
> - **nothing has been deployed and there is no public URL**. The requested hostname
>   `osrip.project.com` needs a DNS record from whoever manages `project.com`
>   ([`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)).

## Scope

Three primary domains, one shared commodity registry:

1. **Energy and Essential Services**: Electricity and Water (separate views, units, charts)
2. **Food Security**: apparent availability of mapped commodities
3. **Trade**: quantities, nominal values and partners of the same commodities

Plus a sourced **Geography** registry (11 governorates, 63 wilayats) and
**Forecasts and Scenarios**:

- per domain: A. historical observations, B. statistical forecasts backtested against
  a last-value baseline (the page shows "Insufficient comparable historical data for a
  reliable forecast." wherever the evidence is too short), development conditions
  (measured only where a published series exists, otherwise scenario assumptions) and
  C. user-defined what-if scenarios, each with an explanation of what may change,
  contributing factors, uncertainty, evidence needed and a follow-up.

The assistant is **Al Mulhim / المُلْهِم** ("one who inspires"; a fictional AI-generated
face, labelled as an AI assistant on every page). Its identity, introductions and greeting
replies («السلام عليكم» → «وعليكم السلام ورحمة الله وبركاته») come from a versioned,
server-owned profile that chat and web pages cannot change; greetings are never charged.
It explains stored results with
citations and labels each figure observed, calculated, forecast or hypothetical; it never
produces forecasts. It can also **search the web** (official Omani sources first), and
labels every web finding as official data or secondary reporting with its link,
publication date and retrieval date. Web figures never enter the dataset: they go to a
review queue for data managers. Questions can be spoken and answers read aloud (server
speech with Omani Arabic and British English voices; the face moves with the audio's
loudness, not lip-synchronised). Visitors without an account get five successful answers,
text and voice together, counted on the server; without a configured model the assistant
shows a labelled non-AI lookup of published records. Wheat, rice and tomatoes are
*provisional* demonstration commodities.

The same assistant answers in five modes: **Ask**, **Analyze** (growth rates, shares and
changes calculated by OSRIP, with recommendation cards: finding, evidence, suggested
action, expected benefit, prerequisites, uncertainty, sources), **Research** (Arabic and
English search; official Omani sources first, then international organisations and
research papers; pages and tables read), **Compare** (governorates or periods, like with
like) and **Scenario** (kept apart from validated forecasts). The server checks every
number against the evidence cited next to it, and drops any card, driver or conflict that
the evidence does not support. Drivers are labelled evidence, hypothesis or assumption. The
**Research library** holds the source library, saved research with downloadable briefs
(HTML or Markdown), and indicator watchlists with data-update and threshold alerts that
each reader can switch off, change or delete. Geography compares each governorate's own
published values; missing values are never shown as zero, and totals are never divided.

**Studies** run fixed, allowlisted analyses on the server (trend, compound growth,
governorate comparison, seasonal profile, import dependence, partner concentration, data
quality, what-if scenario, forecast eligibility, programme record). One validated result
(`osrip.study/1`) feeds the cards, sortable table, chart (line, ranked bar or heatmap),
CSV/JSON downloads and Al Mulhim's answer; a stored study can be reproduced to check it.
While Al Mulhim works, the real stages are shown and the question can be stopped (not
counted); each answer says how it was prepared.

Navigation:

- Home, Overview;
- Domains: Energy and Essential Services (Electricity, Water), Food Security, Trade;
- Analyse: Map, Studies, Scenarios, Sources;
- Assistant and outputs: Al Mulhim (and Talk to Al Mulhim), Reports, Research library;
- Account;
- Data Management, Users and roles, and Service health (authorized users only).

A first visit opens a short bilingual entrance (OSRIP, «منصة عُمان الذكية لمعلومات
الموارد», its three goals, Explore / Skip); it is remembered in that browser and can be
replayed from the footer.

Each analytical page answers four questions from its loaded evidence: what the
indicator measures, what changed, what evidence supports it, and what to investigate
next.

Accounts:

- create an account with an e-mail address **or** a mobile number (Oman +968 by
  default), with neither required;
- operators can create a standard account identified by a **username** only
  (`python -m app.cli ensure-user --username NAME`), with a temporary password that must
  be changed at first sign-in; nothing else works until it is;
- sign in with a username or e-mail address and password, an e-mail link, an SMS code, or
  Google/Microsoft when configured; change the password on the Account page;
- recover a password by e-mail;
- add a verified phone or e-mail address to an existing account (never merged).

Roles (booklet 3.9): public viewer (no account), `viewer`, `analyst`, `data_manager`,
`administrator`. Approving and publishing need explicit per-user grants
(`import.approve`, `import.publish`) that no role implies. Every permission is
checked by the server.

The visual identity is a **proposal** for an academic prototype, not official
government branding.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/VERIFICATION_REPORT.md](docs/VERIFICATION_REPORT.md) | The integrated experience, verified together (11 Oct 2026): the nine demonstrations with screenshots, guest-allowance rules mapped to tests, tests actually run, services not live-tested, missing credentials and assets, files changed |
| [docs/implementation-status.md](docs/implementation-status.md) | Al Mulhim programme register: implemented, locally tested, live-tested and deployed, per feature; provider readiness |
| [docs/TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md) | English technical report for stages 1–8 |
| [docs/TECHNICAL_REPORT_AR.md](docs/TECHNICAL_REPORT_AR.md) | Arabic technical report with an English summary (20 Oct 2026): purpose, architecture, languages and libraries, folders, database and API, AI, search, shortage and surplus analysis and speech, local startup, implemented versus unconfigured features, Azure Speech setup |
| [docs/دليل_البدء.md](docs/دليل_البدء.md) | Arabic beginner instructions (تشغيل المنصة خطوة بخطوة) |
| [docs/avatar-providers.md](docs/avatar-providers.md) | Talking-avatar providers: comparison and acceptance test (none selected) |
| [docs/requirements.md](docs/requirements.md) | Requirements register compiled from the booklet, with status |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Requirement → test → result |
| [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) | Actual results of the audit run, performance and backup exercise |
| [docs/API.md](docs/API.md), [docs/api/openapi.json](docs/api/openapi.json) | API reference |
| [docs/WINDOWS_STARTUP.md](docs/WINDOWS_STARTUP.md) | One-time Windows setup; Visual Studio (F5), VS Code and one-click startup; what was verified |
| [docs/WORKSPACE.md](docs/WORKSPACE.md) | The analytical workspace (Overview): filters, cards with stale flags, one validated dataset per chart and table, governorate view only with valid coverage, study panel; live study events (protocol, consistency rules), narration and highlighting, phone tabs |
| [docs/AI_PROVIDERS.md](docs/AI_PROVIDERS.md) | Governed AI and research providers (Anthropic, OpenAI, Gemini with Google Search grounding, Brave): official APIs only, routing policy, data status labels, citations and attribution, limits and spending, provider readiness, setup and verification status |
| [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) | Evaluation of every connected service; settings for e-mail, Google, Microsoft, assistant (Claude), web research (Brave Search API, source classes, safe retrieval, review queue), guest allowance, voice (Azure AI Speech, Omani Arabic voices), Canva, map and NCSI data |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Ten-minute demonstration for the university presentation |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide and unresolved limitations |
| [docs/progress.md](docs/progress.md), [docs/implementation-notes.md](docs/implementation-notes.md) | Progress record and evidence for updating the booklet |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SPEC_CONFLICTS.md](docs/SPEC_CONFLICTS.md), [docs/VERIFICATION.md](docs/VERIFICATION.md) | Design, open decisions, increment-by-increment verification |
| [docs/assets.md](docs/assets.md), [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | Attribution register (photos, fonts, icons, maps), design tokens |

## Install

Tested with Windows 11, Python 3.13.5, Node 24.17.0 and PostgreSQL 17.11. Minimum:
Python 3.11, Node 22.22, PostgreSQL 15. Commands are for **Windows PowerShell**
from the repository root; on macOS/Linux use `source .venv/bin/activate` and `/`
paths.

### 1. PostgreSQL

Either use an existing PostgreSQL 15+ server, or the project's local portable
cluster, which listens on localhost only:

1. Download the PostgreSQL 17 **Windows x86-64 binaries (zip)** from EDB
   (<https://www.enterprisedb.com/download-postgresql-binaries>) and unpack them so that
   `%LOCALAPPDATA%\OSRIP-dev\pgsql\bin\postgres.exe` exists (or set `OSRIP_PG_BIN` to
   another `bin` folder).
2. Then:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock
pip install --no-deps -e .
python scripts\devdb.py init          # once: creates the cluster and a random superuser password
python scripts\devdb.py start
python scripts\devdb.py createdb osrip_dev
```

### 2. Database schema and synthetic seed

```powershell
# still in backend\ with the virtual environment active
$env:OSRIP_DATABASE_URL = (python scripts\devdb.py url osrip_dev)
alembic upgrade head                  # migrations 0001-0019 (schema, reference rows, area registry, accounts, assistant, forecasts, monitoring, phone verification, reference pack, guest allowance, usernames, research review queue, answer modes, saved research and watchlists, assistant profile and identity, studies, request progress, personas, provider calls, live study events)
python -m app.cli seed-synthetic      # the booklet's SYNTHETIC fixtures, through the import workflow (idempotent)
python -m app.cli import-reference-pack --publish   # the curated 346-record reference pack (checked to 2026-09-27), verified-source mode (idempotent)
```

Create the first administrator (the password is prompted, never passed as an argument).
Other people can then register themselves at /register (Viewer access) and the
administrator grants roles on the **Users and roles** page:

```powershell
python -m app.cli create-user --email manager@example.org --name "Data manager" --role data_manager --grant import.approve --grant import.publish
python -m app.cli create-user --email analyst@example.org --name "Analyst" --role analyst
python -m app.cli create-user --email admin@example.org --name "Administrator" --role administrator
# a standard (viewer) account identified by a username; temporary password prompted, changed at first sign-in
python -m app.cli ensure-user --username Azzan --name Azzan
```

The account **Azzan** exists in the local development database (created 2026-10-02 with
the temporary password that was supplied in the request; viewer role only, no e-mail or
phone). Its password is not recorded anywhere in this repository. Because that password was
shared in a conversation, it is a development credential only: sign in once and choose a
new password (the site requires it), and never reuse it in production.

With your own PostgreSQL server instead, set `OSRIP_DATABASE_URL` to
`postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` (copy `backend/.env.example` to
`backend/.env`) and run the same `alembic` and `app.cli` commands.

### 3. Frontend

```powershell
cd frontend
npm ci                                 # exact versions from package-lock.json
copy .env.example .env                 # VITE_DATA_ADAPTER=http; optional VITE_MAP_STYLE_URL
```

## Start OSRIP on Windows (step by step)

For someone who has never run the project. Every command goes in **Windows PowerShell**
(Start menu > type *PowerShell* > Enter). Replace `C:\path\to\OSRIP` with the folder that
holds this README, for example `C:\Users\Dell\Desktop\OSRIP`. A folder outside OneDrive is
best: OneDrive would otherwise keep syncing `node_modules` and `.venv` (tens of thousands of
files).

**A. Install the tools (once per computer)**

1. **Python 3.13** from <https://www.python.org/downloads/windows/>. In the installer, tick
   *Add python.exe to PATH*.
2. **Node.js 24 LTS** from <https://nodejs.org/> (the default options are fine).
3. **The PostgreSQL 17 binaries:** the *Windows x86-64* zip, **not** the installer, from
   <https://www.enterprisedb.com/download-postgresql-binaries>.
   - Open the zip and copy its `pgsql` folder to `%LOCALAPPDATA%\OSRIP-dev\` (paste
     `%LOCALAPPDATA%` into the File Explorer address bar).
   - Afterwards `%LOCALAPPDATA%\OSRIP-dev\pgsql\bin\postgres.exe` must exist.
4. Optional: **Visual Studio 2022 or 2026** with the *Python development* workload, or
   **VS Code** with the Python extension.

**B. Prepare the project (once per copy of the project)**

```powershell
cd "C:\path\to\OSRIP\backend"
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
cd ..\frontend
npm ci
```

These commands take a few minutes and need internet access. Nothing else needs to be
configured: on its first start the launcher creates the local database (localhost only), and
loads the labelled synthetic demo data and the curated reference pack.

**C. Start OSRIP.** Choose one of three ways:

- **Visual Studio:**
  1. **File > Open > Project/Solution**, and choose `OSRIP.sln`.
  2. Check that **OSRIP.Launcher** is bold in Solution Explorer. If it is not, right-click
     it > *Set as Startup Project*.
  3. Press **F5**.
- **VS Code:**
  1. **File > Open Folder**, and choose the OSRIP folder.
  2. Press **Ctrl+Shift+B**. This runs the task *OSRIP: start everything*.
- **No program needed:** double-click **`start-osrip.cmd`** in the OSRIP folder.

A window with the log opens (`[ db]`, `[api]`, `[web]` lines). After about 15 seconds it
prints **`OSRIP is ready: http://localhost:5173/`** and your browser opens the site. The first
start takes longer, because it creates the database.

The launcher then lists the optional services that are not configured (AI model, web search,
voice, Google/Microsoft sign-in). This is expected: the site works without them and says
where each one is unavailable.

**D. Use it**

- Use the site as a guest: you get 5 assistant answers; greetings are free.
- Or create an account at **Register** (e-mail or mobile number). In development, e-mails
  and SMS codes are not sent: read them at <http://localhost:5173/dev/mail>.
- Choose the assistant (**Al Mulhim** or **Ilham**) with the picker in the assistant panel.
- The analytical workspace is **Overview**.

**E. Stop it**

- Visual Studio: **Shift+F5**.
- VS Code: the trash-can icon on the task's terminal.
- `start-osrip.cmd`: close its window.

Your data is kept. The next start reuses it.

**F. Optional: AI model, web search and voices.** You need real API keys from each provider's
developer console. A ChatGPT, Gemini or Claude app subscription does not include API access.

1. Stop OSRIP.
2. Store the AI and search keys. Each key is typed at a hidden prompt and tested once:

   ```powershell
   cd "C:\path\to\OSRIP\backend"
   .\.venv\Scripts\python.exe scripts\set_provider_keys.py
   ```

3. For the personas' male and female voices (Azure AI Speech), open `backend\.env` in a text
   editor and add `OSRIP_SPEECH_KEY=` and `OSRIP_SPEECH_REGION=`, each followed by your value.
   Never paste keys into chat, e-mail or the repository.
4. Start OSRIP again.

**If something goes wrong**

- **The window names a missing tool or package:** run the command it prints, and start
  again.
- **OSRIP is already running** (for example, started from Visual Studio and then from VS Code):
  the second start opens the running site and starts nothing new. Stop the first one if you
  want a fresh start.
- **The browser did not open:** go to <http://localhost:5173/> yourself.
- **The laptop slept during startup:** start again.
- Full details: [docs/WINDOWS_STARTUP.md](docs/WINDOWS_STARTUP.md). Arabic guide:
  [docs/دليل_البدء.md](docs/دليل_البدء.md).

## Start (summary and manual start)

**One click (Windows):** after the install steps, use any of:

- **VS Code:** Terminal > Run Task > **OSRIP: start everything** (Ctrl+Shift+B), or Run and
  Debug > **OSRIP: debug the interface in Edge**;
- **Visual Studio 2022/2026** (Python workload): open `OSRIP.sln`, keep **OSRIP.Launcher**
  as the startup project and press F5 or Ctrl+F5 (configured, but F5 inside the Visual Studio
  window has not been tested from this environment);
- **No IDE:** double-click `start-osrip.cmd`.

All three run the same launcher (`tools/start_osrip.py`). It checks prerequisites and
reports missing configuration, then starts PostgreSQL, the API and the frontend. It waits
for their readiness checks and opens **<http://localhost:5173/>**. Stopping it stops only
what it started, and it never resets data. Details, options and what was verified:
[docs/WINDOWS_STARTUP.md](docs/WINDOWS_STARTUP.md).

Or by hand, in two terminals:

```powershell
# terminal 1 - API on http://127.0.0.1:8010 (docs at /docs), against osrip_dev
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\devdb.py start          # if not already running
python scripts\serve_dev.py
```

Optional, before `serve_dev.py` in the same terminal (see [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)):

```powershell
$env:OSRIP_ANTHROPIC_API_KEY = "..."   # enables the assistant; without it the panel says "not configured"
$env:OSRIP_RESEARCH_API_KEY = "..."    # Brave Search API: web research (needs the assistant key too)
# OpenAI or Gemini instead (API keys, not app subscriptions; model ids from each provider's list):
#   OSRIP_ASSISTANT_PROVIDER=openai|gemini, OSRIP_OPENAI_API_KEY / OSRIP_GEMINI_API_KEY,
#   OSRIP_OPENAI_MODEL / OSRIP_GEMINI_MODEL; search: OSRIP_RESEARCH_PROVIDER=openai|gemini with
#   OSRIP_OPENAI_SEARCH_MODEL / OSRIP_GEMINI_SEARCH_MODEL. See docs/AI_PROVIDERS.md.
$env:OSRIP_SPEECH_KEY = "..."; $env:OSRIP_SPEECH_REGION = "uaenorth"   # Azure AI Speech: voice in and out
$env:OSRIP_PUBLIC_BASE_URL = "http://localhost:5173"   # address used in e-mail links
```

Or put the same settings in `backend\.env` (copy `backend\.env.example`; `.env` files are
git-ignored). Keys are read only by the API and are never sent to browsers.

In development, e-mails (confirmation, reset, sign-in links) and SMS codes are not
sent. `serve_dev.py` uses the development mail outbox and the scripted SMS test
provider, and the interface labels both as test mode. Open <http://localhost:5173/dev/mail>
to read the messages, click the links and see the SMS codes. To see how the site looks
without SMS, run `$env:OSRIP_SMS_ENABLED = "false"` before `serve_dev.py`.
Real SMS delivery needs a provider adapter first: see
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#sms-verification-registration-and-sign-in-by-phone).

```powershell
# terminal 2 - interface on http://localhost:5173 (/api is proxied to 127.0.0.1:8010)
cd frontend
npm run dev
```

`serve_dev.py` switches off the Secure cookie flag because it serves plain HTTP on
localhost; never do that elsewhere. If port 5173 is busy: `$env:PORT=5180; npm run dev`.

Offline interface work without a backend: `$env:VITE_DATA_ADAPTER="mock"; npm run dev`
(synthetic fixtures in the browser only; no calculations, reports or sign-in).

## Services, studies and recorded introductions

Set these in `backend/.env` (never in the frontend) and restart OSRIP. Settings › Services shows
what is set up, the latest outcome of the answer service, and what to fix, without values.

- **AI answers:** `OSRIP_ASSISTANT_PROVIDER` and its key (for Claude, the full
  `OSRIP_ANTHROPIC_API_KEY` and `OSRIP_ASSISTANT_MODEL`). If the key is wrong or truncated the
  service replies 401; OSRIP then answers with a **data-based report without AI
  interpretation** (published records and OSRIP calculations), logs the failure with its request
  id and category (never the key), does not charge a guest, and lets the person retry.
- **Web search:** `OSRIP_RESEARCH_PROVIDER` with its own key (`OSRIP_RESEARCH_API_KEY` for
  Brave); it is a different key from the AI key.
- **Page retrieval for studies (optional):** `OSRIP_FIRECRAWL_API_KEY`. Without it, studies with
  web sources read official pages directly through the SSRF-safe fetcher. Limits:
  `OSRIP_CRAWL_MAX_PAGES`, `_MAX_DEPTH`, `_MAX_RUNTIME_SECONDS`, `_MAX_CREDITS`, `_MAX_PDF_PAGES`,
  `_HOST_INTERVAL_SECONDS`, `_ALLOWED_DOMAINS` (see `backend/.env.example`).
- **Scheduled reports:** off unless `OSRIP_SCHEDULED_REPORTS_ENABLED=true`; each schedule is
  created disabled, and one that uses web sources also needs "allow paid runs".
- **Voices:** `OSRIP_SPEECH_KEY` and `OSRIP_SPEECH_REGION` (Azure AI Speech). Al Mulhim speaks with
  ar-OM-AbdullahNeural / en-GB-RyanNeural and Ilham with ar-OM-AyshaNeural / en-GB-SoniaNeural.
- **Recorded introductions (Canva):** put each exported clip in `frontend/public/audio/intro/`
  and set its file name and exact words in `manifest.json` there (`mulhim.ar`, `ilham.ar`).
  Until a clip is named the introduction is not offered; a clip is always labelled as a
  recording, never as live speech.

"Create study" (Studies page, signed in) runs a study in the background: discover sources,
retrieve documents, extract evidence, validate data, calculate, build tables and charts, write
conclusions, recommend next steps. The page follows its progress; it can be stopped and retried.

## Stop

1. Press `Ctrl+C` in both terminals.
2. `python scripts\devdb.py stop` (in `backend\`) stops the local PostgreSQL cluster.
   Data stays in `%LOCALAPPDATA%\OSRIP-dev\pgdata`.

## Tests

```powershell
# backend (from backend\, virtual environment active)
pytest                                                   # unit tests only
$env:OSRIP_RUN_DB_TESTS="1"; $env:OSRIP_TEST_ADMIN_URL=(python scripts\devdb.py url); pytest   # + integration (fresh DB per run)
ruff check app tests scripts; ruff format --check app tests scripts

# frontend (from frontend\)
npm run lint; npm run typecheck; npm run build; npm run check:contrast
$env:PW_CHANNEL="msedge"; npx playwright test                                   # mock mode
$env:OSRIP_TEST_ADMIN_URL=(..\backend\.venv\Scripts\python.exe ..\backend\scripts\devdb.py url); npx playwright test -c playwright.api.config.ts   # full stack, desktop + phone
npx playwright test -c playwright.demo.config.ts   # the nine demonstrations (same OSRIP_TEST_ADMIN_URL); screenshots to docs\evidence\integrated\
```

`PW_CHANNEL=msedge` uses the installed Edge; alternatively run
`npx playwright install chromium` once and omit it.

Live SMS acceptance (only once a real provider is configured, with an authorized number):
`python backend\scripts\sms_acceptance.py --url <API origin>`.

Before any deployment (from the repository root): `python deploy\predeploy_check.py`
(see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#pre-publication-check)).

Operational exercises (from `backend\`, cluster running):

```powershell
$env:OSRIP_TEST_ADMIN_URL=(python scripts\devdb.py url); python scripts\perf_workload.py   # writes docs\perf\
python scripts\backup_restore_drill.py osrip_dev                                          # writes docs\backup\
```

## Repository layout

```text
frontend/   React 19 + TypeScript + Vite 8 + Tailwind 4, React Router 8, TanStack Query 5,
            react-i18next, zod, MapLibre GL JS (lazy); e2e/ (mock), e2e-api/ (full stack) and
            e2e-demo/ (the integrated demonstrations)
backend/    FastAPI + Pydantic 2 + SQLAlchemy 2.0 + Alembic + psycopg 3 + argon2-cffi
  app/domain/        pure calculations, forecasting and explanations (no I/O)
  app/services/      accounts, imports, observations, analysis, reports, geography, forecasting
  alembic/sql/       reviewed SQL executed verbatim by the Alembic revisions
  db_checks/         SQL checks of database integrity rules (run by pytest)
  fixtures/          the booklet's SYNTHETIC fixtures
  scripts/           devdb (local PostgreSQL), serve_dev, serve_e2e, perf_workload, backup_restore_drill
  requirements.lock  exact Python versions of the tested environment
deploy/     Dockerfiles, Caddyfile, docker-compose.yml (db, migrate, api, web, backup), backup.sh,
            .env.example, predeploy_check.py (prepared, not yet run on a server)
docs/       see the table above
```

## Data rules (enforced in code)

- Verified-source and synthetic data are separate modes at every layer; never mixed,
  never substituted for each other. Synthetic sources cannot have a publisher.
- Missing values stay `NULL`/missing through calculation and display, never zero.
- Comparisons require the same unit dimension, coverage and comparable periods; a
  read that mixes frequencies asks the reader to choose one.
- Stored values are unrounded; rounding is display-only.
- No official statistics, boundaries, coordinates, sources or research results are invented.
