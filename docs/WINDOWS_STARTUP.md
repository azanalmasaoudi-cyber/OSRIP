# Windows startup: Visual Studio, VS Code and one-click

OSRIP stays React/TypeScript + FastAPI + PostgreSQL. A small launcher,
`tools/start_osrip.py` (Python standard library only), starts everything in order and
opens the website only when the checks pass:

1. checks the backend virtual environment and packages, Node.js (22.22+), the frontend
   packages and the PostgreSQL binaries, and prints the exact commands for anything missing;
2. starts the portable PostgreSQL dev cluster unless it is already running, waits until it
   accepts connections, creates `osrip_dev` if it does not exist and applies
   forward-only migrations (`alembic upgrade head`); on the very first run it also loads
   the labelled synthetic demo data and the curated reference pack (both idempotent);
3. starts the FastAPI backend and waits for `/api/v1/health/ready` to report `ready`
   (database reachable and migrations at head; a live process alone is not enough);
4. starts the Vite frontend and waits until it serves OSRIP **and** proxies to that API;
5. opens `http://localhost:5173/` (or the port it had to move to).

It never deletes or resets data, never asks for administrator rights and never stops a
program it did not start.

## One-time setup

Requirements: Windows 10/11, Python 3.13 (3.11+ works), Node.js 22.22 or later (Node 24 LTS
or the copy Visual Studio's *Node.js development* workload installs), and the PostgreSQL 17
Windows binaries zip (no installer or service).

```powershell
cd "C:\path\to\OSRIP\backend"
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .

cd ..\frontend
npm ci
```

PostgreSQL: download the *Windows x86-64 binaries* zip for PostgreSQL 17 from
<https://www.enterprisedb.com/download-postgresql-binaries> and extract its `pgsql` folder
to `%LOCALAPPDATA%\OSRIP-dev\pgsql` (or set `OSRIP_PG_BIN` to any PostgreSQL `bin` folder).
The launcher creates the cluster in `%LOCALAPPDATA%\OSRIP-dev\pgdata` on first start
(localhost only, random superuser password stored in that folder, never in the repository).

**Data folder created by a packaged app.** If the cluster was first created from a packaged
(MSIX) application, Windows keeps it in that app's private copy of AppData, for example
`%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Local\OSRIP-dev`, where ordinary programs (Visual
Studio, VS Code, a terminal) do not see it. The launcher and `backend\scripts\devdb.py` now
look there when `%LOCALAPPDATA%\OSRIP-dev\pgdata` does not exist and use it if exactly one is
found, so existing data is reused instead of a second, empty cluster being created. The first
log line names the folder in use (`Development data folder: …`). Set `OSRIP_DEV_HOME` to
choose explicitly.

Optional provider settings (assistant, web search, speech, e-mail, SMS, Google/Microsoft
sign-in) go in `backend\.env` (copy `backend\.env.example`) and are described in
`docs/INTEGRATIONS.md`. Everything starts without them; once the API is ready the launcher
lists which ones are not configured, and the interface says so wherever they would be used.

### Creating a standard account by username

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli ensure-user --username Azzan --name Azzan
```

The temporary password is typed at the prompt (not echoed, asked twice) or taken from
`OSRIP_NEW_USER_PASSWORD` set in that terminal only; it is never an argument or stored in a
file. The account gets the viewer role only, no e-mail address or phone number, and must
choose a new password (12+ characters) at first sign-in; until then it can do nothing else.
Running the command again changes nothing. In VS Code the task **OSRIP: create a username
account (password prompted)** does the same.

## Visual Studio (2022/2026 with the *Python development* workload)

1. **File > Open > Project/Solution** and choose `OSRIP.sln` in the repository root (open the
   solution, not the folder: see "Open Folder mode" below).
2. Solution Explorer shows every OSRIP file:
   * **OSRIP.Launcher** (`tools\`): the startup project (bold). F5 starts everything.
   * **OSRIP.Backend** (`backend\`): the FastAPI code, tests, scripts and SQL migrations, plus
     the maintenance scripts from `tools\` (linked, because they need this environment's
     Pillow). Its Python environment is `backend\.venv`, so imports resolve and **Test > Test
     Explorer** lists the pytest tests (database tests are skipped unless
     `OSRIP_RUN_DB_TESTS=1` and `OSRIP_TEST_ADMIN_URL` are set).
   * **OSRIP.Frontend** (`frontend\`): the React/TypeScript interface, its Playwright tests and
     the image sources (`assets\`). Visual Studio checks TypeScript against `tsconfig.json`
     (run `npm ci` once).
   * Solution folders hold the remaining files:
     - **Solution Items:** README, `start-osrip.cmd`, `.editorconfig`, `.vsconfig`, `.env.example`
       and the ignore files.
     - **.vscode**.
     - **deploy**.
     - **docs**, including the evidence screenshots.

     Never shown: secret `.env` files, generated folders, other editors' local state, and
     folders that are not part of OSRIP (`docs\Downloads`, the old `OSRIP\` copy, `Web.config`).

   If `OSRIP.Launcher` is not bold: right-click it > **Set as Startup Project**.

   **Build, Clean and Rebuild:**
   - **Build > Build Solution** (Ctrl+Shift+B in Visual Studio; in VS Code the same keys start
     OSRIP) checks the TypeScript code and makes the production build (`npm run build`, about 15
     seconds). It does not start OSRIP: use F5 for that. The Python projects have nothing to
     compile.
   - **Clean** deletes that build output. Only files are deleted, because Windows refuses to
     remove the read-only folders that OneDrive creates (the project lived in OneDrive until
     14 October 2026).
   - **Rebuild** does both.
   - F5 builds only the startup project, which takes no time.
3. Press **F5** (or the green Start button). **Ctrl+F5** runs without the debugger and starts
   slightly faster.
4. A console window shows the combined log (`[ db]`, `[api]`, `[web]`); the browser opens when
   OSRIP is ready. The same log is written to `%LOCALAPPDATA%\OSRIP-dev\logs\`.
5. **Shift+F5** (Stop Debugging) or closing the console window stops the API and frontend
   the launcher started (a Windows job object ends them even when Visual Studio kills the
   launcher), and PostgreSQL is stopped gracefully if the launcher started it.

The solution and the backend and frontend project files list files explicitly. After adding
or removing files, regenerate them (Visual Studio offers to reload):

```bash
backend\.venv\Scripts\python.exe tools\make_vs_projects.py
```

**Editor settings.** Two files in the repository root shape Visual Studio's behaviour:

- **`.editorconfig`** gives Visual Studio (and VS Code, with the EditorConfig extension) the
  project's existing style:
  - UTF-8 without a byte-order mark, and Unix (LF) line endings;
  - 2 spaces for TypeScript, JSON and Markdown; 4 for Python, SQL and TOML;
  - a final newline.

  Windows command scripts keep CRLF line endings, and PowerShell scripts keep a byte-order
  mark. Without this file, Visual Studio's Format Document indents TypeScript with its default
  of 4 spaces. New files and lines can also get Windows line endings, and a file that mixes the
  two makes Visual Studio ask to "normalize line endings".
- **`.vsconfig`** names the workloads the solution needs (*Python development* and *Node.js
  development*). If one is missing, Visual Studio offers to install it when the solution
  opens.

Scripts that write files into the repository (`tools\build_*.py`, the reference-pack builder,
and the performance and backup exercises) write LF line endings, even on Windows.

**SQL files.** The migrations are PostgreSQL. Visual Studio's SQL editor checks `.sql` files as
SQL Server (T-SQL) and underlines valid PostgreSQL as errors when a migration is open. These
are not project errors. To hide them: **Tools > Options > Text Editor > Transact-SQL >
IntelliSense**, clear **Underline errors** (or close the `.sql` tab).

**Open Folder mode** (File > Open > Folder) indexes everything in the folder, including the
older project copy in `OSRIP\OSRIP\` (not used by the solution), `node_modules` and `.venv`,
which fills the Error List with errors from files that are not part of OSRIP. The local file
`.vs\VSWorkspaceSettings.json` excludes those folders, and `.vs\launch.vs.json` adds
**OSRIP: start everything** to the Start button's drop-down, but the solution is the
supported entry point. Both files live in Visual Studio's local `.vs` folder.

## VS Code

VS Code settings are separate files and do not affect Visual Studio.

* **Terminal > Run Task > OSRIP: start everything** (also the default build task,
  Ctrl+Shift+B), or
* **Run and Debug > OSRIP: start everything** (`.vscode/launch.json`, Python debugger on the
  launcher; needs the Python extension).
* **Run and Debug > OSRIP: debug the interface in Edge** starts everything without opening a
  browser (task *OSRIP: start everything (no browser)*), waits for "OSRIP is ready", then opens
  Edge at `http://localhost:5173/` with the JavaScript debugger attached to `frontend/src`.
* Other tasks: first-time setup, check prerequisites, create a username account, backend unit
  tests, frontend type-check and lint. `OSRIP: debug the API only` debugs the backend with
  breakpoints while the dev database is running.
* Stop: the trash-can icon on the task terminal, **Shift+F5**, or Ctrl+C in the terminal.

## Without an IDE

Double-click `start-osrip.cmd`, or run
`backend\.venv\Scripts\python.exe tools\start_osrip.py` from any folder.

Options: `--setup` (reload demo data and the reference pack), `--no-browser`, `--keep-db`
(leave PostgreSQL running), `--check` (prerequisites and ports only).

Environment variables: `OSRIP_API_PORT` (default 8010), `OSRIP_WEB_PORT` (5173),
`OSRIP_DEV_PG_PORT` (55432), `OSRIP_PG_BIN`, `OSRIP_NODE`, `OSRIP_DEV_HOME`,
`OSRIP_NO_BROWSER=1`. If `OSRIP_DATABASE_URL` is set, that database is used as it is and the
launcher neither starts nor migrates it.

## Behaviour details

| Situation | What the launcher does |
|---|---|
| An OSRIP API already answers on 8010 | Reuses it and does not stop it later |
| Another program uses 8010 or 5173 | Leaves that program alone and moves OSRIP to the next free port (the frontend is pointed at the moved API) |
| Another program uses the database port | Stops with an explanation; nothing is killed |
| A second Start while one is running | Opens the browser at the running instance and exits |
| A service exits unexpectedly | Logs its last output, stops the others, exits with code 1 |
| Stop Debugging / window closed / Ctrl+C | Ends the API and frontend it started; stops PostgreSQL gracefully if it started it |

## What was verified, and what was not

Verified on 2026-10-16, on branch `review/codex-upgrade-2026-10-15` (first source upgrade):

- `tools\start_osrip.py --check` passed. Then
  `backend\.venv\Scripts\python.exe tools\start_osrip.py --no-browser --keep-db`, from the
  repository root (the VS Code task's command, plus `--keep-db`):
  - PostgreSQL started; the dev data folder was found; migrations were at head (0019).
  - The API was ready, and the services not configured were listed: voice, Google and
    Microsoft sign-in.
  - It reported **OSRIP is ready: http://localhost:5173/** 26 seconds after the start.
  - `/` and `/api/v1/health` answered 200 through the frontend.
  - Stopping the launcher ended the API (8010) and the frontend (5173). PostgreSQL kept
    running, as `--keep-db` asks, and was then stopped with `backend\scripts\devdb.py stop`.
- `MSBuild OSRIP.sln /t:Build` (Visual Studio 18 Community MSBuild): exit 0.
- **F5 inside Visual Studio was not operated.** Visual Studio was open on the owner's desktop
  with this solution, so it was left alone. F5 runs the same launcher with the working directory
  set to the repository root, under the Python environment selected in Visual Studio.
- AI answers and web search are configured but rejected by the providers (Anthropic HTTP 401,
  Brave `SUBSCRIPTION_TOKEN_INVALID`). The site starts and works without them; see
  `CODEX_REVIEW_2026-10-15.md`.
- During this session the laptop went into Modern Standby several times. Each time, browser
  tests stalled and provider calls failed with `network`. For long test runs, keep it plugged in
  and awake.

Verified on 2026-10-14, after the project moved out of OneDrive.

**What happened:**

- At 11:40, Windows' Desktop was moved from `C:\Users\Dell\OneDrive\Desktop` back to
  `C:\Users\Dell\Desktop`, and OneDrive moved the files in the background over about five
  hours.
- Until the move finished, the old OneDrive folder showed a project with folders but no files.
  Nothing was lost: all 46,867 files arrived. `docs\Downloads` has 8,134, the original count
  minus the two installers deleted to the Recycle Bin that morning.

**Two side effects of the move, both fixed:**

- **The backend's `.venv` still pointed at the old path** (its editable install and its
  `pytest.exe`/`alembic.exe` launchers). It was rebuilt in place with the same 95 packages (no
  difference in `pip freeze`), and `pip install --no-deps -e .` was re-run.
- **About 20,800 moved files kept OneDrive's cloud reparse point** (tag `0x9000201a`). Outside
  OneDrive's folder, Node.js reports such files as symbolic links, so Playwright found "No
  tests". Each file was rewritten as an ordinary file with the same bytes and modification time,
  and checked by SHA-256. Your personal `docs\Downloads`, the JDK and the old `OSRIP\` copy were
  left as they are.

**Afterwards, from `C:\Users\Dell\Desktop\OSRIP`:**

- backend suite: 551 passed;
- ruff: clean;
- `MSBuild OSRIP.sln` Clean and Build: 0 warnings, 0 errors;
- ESLint: clean;
- mock browser suite: 27 passed;
- the launcher, run with Visual Studio's Python 3.14.7 exactly as F5 runs it (ports
  8020/5190), reported "OSRIP is ready" in about 10 seconds;
  - `/`, `/overview`, `/api/v1/health/ready` and `/api/v1/assistant/voice` answered 200;
  - stopping it ended the API, the frontend and the PostgreSQL it had started.

**Backup made first:** `C:\Users\Dell\Documents\OSRIP-backups\` holds the project (592 files,
verified zip with a SHA-256 list) and a `pg_dump` of `osrip_dev`.

Verified on 2026-10-11 (Visual Studio files for this laptop):

- `make_vs_projects.py` now also writes `OSRIP.sln`. Solution Explorer lists 587 files: every
  project file except the intended exclusions.
- With MSBuild from Visual Studio Community 18.10.3, `OSRIP.sln` builds:
  - **Clean** in 1 s;
  - **Build** in 12 s (type check and production build);
  - **Rebuild** in 15 s;

  each with 0 warnings and 0 errors.
- Before this change, Clean and Rebuild of OSRIP.Frontend failed (`npm run clean`: missing
  script), and Build Solution skipped every project.
- 14 files written with Windows line endings were converted to LF, after checking that only
  line endings changed: the assistant profiles, the reference pack, the language files,
  `studies.py`, generated JSON, and the two files with mixed endings. The backend suite (551),
  ESLint and the mock browser suite (27) passed afterwards.
- F5 inside the Visual Studio window was again not operated from here. The launcher project
  and its id are unchanged, so it stays the startup project.

Verified on 2026-10-11 (migration 0019; integrated verification, see
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)):

* **Run exactly as the VS Code task runs it:**
  - `backend\.venv\Scripts\python.exe tools\start_osrip.py`, with `OSRIP_API_PORT=8020` and
    `OSRIP_WEB_PORT=5190`, so as not to disturb another instance. `--check` passed first.
  - The start reused the running PostgreSQL and confirmed migrations at head (0019). The API
    was ready, and the unconfigured services were listed (voice, Google and Microsoft
    sign-in).
  - It reported **OSRIP is ready** after 13 seconds.
  - `/`, `/overview`, `/energy/water`, `/api/v1/health/ready`, `/api/v1/assistant/status` and
    `/api/v1/assistant/voice` all answered 200 through the frontend.
  - Killing the launcher stopped the API and frontend it had started; PostgreSQL kept
    running.
* **Starts by the owner, outside this environment**, recorded in the launcher logs:
  - 2026-10-10 19:28 and 2026-10-11 07:52. Both reached **OSRIP is ready:
    http://localhost:5173/**: the first at migration 0018 (before the upgrade), the second at
    0019, and the second served assistant requests.
  - Both ran the launcher under Python 3.14.7 rather than the backend's 3.13.5 venv, which
    only Visual Studio's launcher project does. So they are consistent with F5 in Visual
    Studio, although the log does not name the IDE.
* **Not verified from here:** pressing F5 in the Visual Studio window, or running the task in
  the VS Code window.
* **Seen afterwards:** the development PostgreSQL had stopped without a clean shutdown (stale
  `postmaster.pid`), probably when the session that started it ended.
  `backend\scripts\devdb.py start` started it normally; the launcher does the same
  automatically.

Verified on 2026-10-02 (release 0.8; Visual Studio Community 2026 18.10 and 2022 17.14, both
with the Python and Node.js workloads, found by `vswhere`):

* From an ordinary (non-packaged) process, exactly as the VS Code task runs it
  (`backend\.venv\Scripts\python.exe tools\start_osrip.py --no-browser`, no `OSRIP_DEV_HOME`):
  the launcher found the existing cluster in the Claude app's virtualised AppData, reused the
  running PostgreSQL, confirmed migrations at head (0011), started the API and Vite, listed
  the five unconfigured services, and reported **OSRIP is ready: http://localhost:5173/**
  13 seconds after start. `http://localhost:5173/`, the direct route
  `/energy/water?mode=synthetic` and the proxied `/api/v1/assistant/status` all answered 200.
* Hard kill of the launcher (what Stop Debugging does): API and frontend processes ended;
  PostgreSQL, which it had not started, kept running; an unrelated OSRIP API on port 8011
  was untouched.
* `--check` from the same kind of process reports the data folder and reuses running services.
* The broken third entry of the old `.vscode/launch.json` (`http://Prj.SPRIP.com${cwd}`) was
  replaced by **OSRIP: debug the interface in Edge**. That configuration and the
  `preLaunchTask` were not run inside the VS Code window from this environment.

Earlier verification (2026-09-25 to 09-27; Visual Studio Community 18.10.2, Python 3.13.5
venv, launcher run under Python 3.14.7, Node 24.21):

* Command-line start from stopped services: PostgreSQL, migration check, API ready and
  frontend ready in about 9 seconds.
* Hard kill of the launcher process (what Stop Debugging does): API and frontend ended by
  the job object; PostgreSQL shut down cleanly by the watchdog (clean shutdown checkpoint
  in its log); no processes left.
* Port 8010 occupied by an unrelated program: API moved to 8011, the frontend proxied to it,
  the other program was not touched.
* A second launcher while one was running: detected it and started nothing.
* The frontend killed while running: the launcher stopped the API gracefully, then
  PostgreSQL, and exited with code 1.
* `MSBuild OSRIP.sln` builds without errors.

Not verified: **pressing F5 inside the Visual Studio window**. There is no way to operate the
Visual Studio user interface from this environment, and `devenv /Build` cannot load
Python projects headlessly (Visual Studio's own unmodified Python template fails the same
way), so it is not evidence either. The Open Folder `launch.vs.json` profile is likewise
unverified. Please run F5 once and report anything unexpected.

2026-10-09 (backend and frontend projects added): `MSBuild` builds `OSRIP.Launcher.pyproj`,
`OSRIP.Backend.pyproj` and `OSRIP.Frontend.njsproj` without errors (the frontend build runs
the Vite build). Headless `devenv /Build` loads `OSRIP.Frontend` and, as before, cannot load
Python projects (it reports "Catastrophic failure" for the launcher too).

Known limitation: if the laptop sleeps while the launcher waits for readiness, the
120-second readiness timeout can expire; start again after waking.
