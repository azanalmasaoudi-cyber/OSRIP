# Central hosting: one OSRIP for the whole team

Arabic: `docs/CENTRAL_HOSTING_AR.md`. Server details: `docs/DEPLOYMENT.md`.

**Status, 27 November 2026: not deployed.** `https://osrip.vercel.app` serves the interface
only. `python tools/check_public_osrip.py https://osrip.vercel.app` passes the page and HSTS and
fails the API: `/api/v1/health/ready` answers Vercel's 404, without OSRIP's `X-OSRIP-API`
header. No server, hosting account or DNS access has been provided; nothing was created or paid
for. Do not call OSRIP deployed until that check passes on the real address and the acceptance
tests at the end of this page pass from two devices.

## The design (already in `deploy/`)

```
5 laptops / phones -> HTTPS (Caddy, ports 80/443) -> React interface and /api/v1 -> FastAPI -> PostgreSQL 17 (private)
```

`deploy/docker-compose.yml` runs five services:
- `db`: PostgreSQL 17, data on the persistent `pgdata` volume;
- `migrate`: a one-shot job (`alembic upgrade head`);
- `api`: FastAPI, as a non-root user, started only after the migrations succeed;
- `web`: Caddy, serving the interface, proxying `/api`, with automatic HTTPS certificates and
  security headers;
- `backup`: a nightly `pg_dump`, kept 14 days.

Reviewed on 27 November 2026 and now enforced by `deploy/predeploy_check.py` and
`backend/tests/test_hosting_tools.py`:
- **Only the web server publishes ports (80, 443).** PostgreSQL and the API publish none. Never
  open 5432 to the internet.
- **The database lives on the persistent volume.** The API waits for the migrations, and the
  API image runs as a non-root user.
- **No secret or backup enters an image:** `.env` files, `*.backup`, `*.dump` and
  `.osrip-local.json` are in `.dockerignore`.
- **No synthetic demonstration data on a real server.** `deploy/remote_up.sh` loads it only with
  `OSRIP_LOAD_SYNTHETIC_DEMO_DATA=1`; before 27 November it always did.
- **The pre-deploy check knows the real AI providers** (anthropic, openai, gemini, deepseek or
  disabled). It still refuses the scripted test double, and it warns when a key, a model or
  DeepSeek's billing acknowledgement is missing.
- **Accounts are a username and a password**, so `.env.example` now sets
  `OSRIP_EMAIL_BACKEND=disabled`. The AI provider is disabled by default: paid use needs the
  owner's approval.

Docker is not installed on the development computer, so the images have **not been built or run**
here. The compose file was checked statically (parsed, and each rule above tested).

## What only the owner can provide

1. **A Linux server** (for example Ubuntu 24.04, 2 vCPU, 4 GB RAM, persistent disk) with Docker
   and Compose, and the decision to pay for it.
2. **A DNS name** you control, pointing at the server, for example `osrip.<your-domain>`. Do not
   use `osrip.project.com` unless you control that zone.
3. **The data decision:**
   - copy everything from the original computer (accounts, password hashes, history); or
   - publish only approved official data on a fresh database.
4. **Optionally, the AI key**, entered on the server only.

Never send passwords, keys or database backups in a chat, and never commit them.

## 1. Back up the original computer (Windows)

With OSRIP's development database running (start OSRIP once, or
`backend\.venv\Scripts\python.exe backend\scripts\devdb.py start`):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\Backup-OSRIP-Local.ps1
```

What it does:
- It reads `osrip_dev` and never changes it. It writes
  `Documents\OSRIP-Backups\osrip_dev-<date>-<time>.backup` and a `.backup.json` manifest: the
  file's SHA-256, the migration version and the exact row count of every table. The manifest
  holds no secrets.
- Before it reports success, it checks that `pg_restore` can read the archive.
- It refuses a folder inside the repository and never overwrites a file.

`-Database osrip_preview` backs up another local database.

The backup holds every account, password hash and record: keep it encrypted (for example in a
BitLocker or 7-Zip AES archive) and out of GitHub, e-mail and chats. `.gitignore` and the
pre-deploy check refuse `*.backup`, `*.dump` and `OSRIP-Backups/` in the repository.

## 2a. Move to another Windows computer

1. Install Git, Python 3.13 and Node.js 24. Clone the repository and run `start-osrip.cmd` once.
   This creates the development database cluster and an `osrip_dev` with demonstration data.
   Then stop it.
2. Copy the `.backup` and its `.backup.json` to that computer privately, then:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\tools\Restore-OSRIP-Backup.ps1 -Backup <file.backup> -Database osrip_restored -Migrate
   ```

   - It checks the file's SHA-256 against the manifest.
   - It restores into the **new** database, never with `--clean`. An existing database, such as
     `osrip_dev`, is refused, never overwritten.
   - It compares every table's row count and the migration version with the manifest.
   - `-Migrate` then applies this checkout's migrations to the copy.
3. Put `{"database": "osrip_restored"}` in that checkout's `.osrip-local.json` and start OSRIP.
   Sign in with an existing account and check a sector, the map and a saved study.
   Replacing `osrip_dev` itself is a separate decision, and only for the owner.

Verified on this computer on 27 November 2026 (`docs/TEST_RESULTS.md`): back up `osrip_dev`,
restore into a new database, compare 70 tables with no difference, then migrate 0034 → 0036.
The drill database was then dropped.

## 2b. Move the data to the server (a new, empty server)

On the server, from the repository root, with `deploy/.env` filled in (step 3):

```bash
compose() { docker compose -f deploy/docker-compose.yml --env-file deploy/.env "$@"; }
compose up -d db                                  # the database only
compose exec -T db psql -U osrip -d osrip -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
# must print 0: restore only into an empty database
compose exec -T db pg_restore -U osrip -d osrip --no-owner --no-acl --exit-on-error \
  < osrip_dev-YYYYMMDD-HHMMSS.backup
compose exec -T db psql -U osrip -d osrip -tA -c "$(python3 tools/compare_restore_counts.py --sql)" > counts.txt
python3 tools/compare_restore_counts.py osrip_dev-YYYYMMDD-HHMMSS.backup.json counts.txt
# "Match: ... as in the backup" before going on
compose up -d --build                             # migrate brings it to the current head, then api and web
```

Rules:
- **Never** use `pg_restore --clean`, `--if-exists` or `DROP DATABASE` on a database that holds
  data without the owner's explicit decision and a fresh backup of it.
- On a server that already has users, back up its own database first (`compose exec -T db
  pg_dump -U osrip -Fc osrip > before-restore.dump`). Then restore into a separate database and
  compare before switching anything.
- PostgreSQL versions: the development cluster is 17.11 and the server image is `postgres:17`, so
  archives restore directly.
- If only approved official data should be published, skip this and start from an empty
  database. Then publish through Data Management's reviewed import workflow.

## 3. Configure and start the server

```bash
cp deploy/.env.example deploy/.env    # on the server only; never commit it
# Fill in:
#   POSTGRES_PASSWORD and OSRIP_CLIENT_HASH_KEY: 32+ random characters each
#     (python3 -c "import secrets; print(secrets.token_urlsafe(48))")
#   OSRIP_DOMAIN, OSRIP_PUBLIC_BASE_URL=https://<domain>, OSRIP_CORS_ORIGINS=["https://<domain>"]
#   OSRIP_EMAIL_BACKEND=disabled (username and password accounts)
#   the AI provider: disabled, or one provider with its key and model (owner's approval for paid use)
python3 deploy/predeploy_check.py                 # fix every FAIL first
sh deploy/remote_up.sh                            # or: docker compose ... up -d --build
python3 deploy/predeploy_check.py --url https://<domain>
python3 tools/check_public_osrip.py https://<domain>
```

Open only 80 and 443 to the public, plus SSH for administrators (by key, restricted by source
address where possible). Create the administrator with
`compose run --rm api python -m app.cli ensure-admin --username <name>`; the password is typed at
a prompt, never stored. This step applies only to an empty database: restored accounts already
exist.

## 4. Backups on the server

The `backup` service writes a nightly dump into the `backups` volume and keeps 14 days, **on the
same disk**. That does not survive losing the server.

Copy the dumps off the host, encrypted, to a destination the owner chooses and authorizes. It is
not configured yet, because none has been provided. Rehearse a restore into an isolated database
each month with `compare_restore_counts.py`.

## 5. Acceptance before announcing the address

1. `check_public_osrip.py https://<domain>` passes: page, HSTS, API ready.
2. From two different devices outside the server's network:
   - sign in with two accounts, and check that a viewer cannot reach Data Management;
   - electricity and water show verified data, labelled, not synthetic;
   - choose a governorate, then its wilayats, on the map;
   - Al Mulhim answers only if a provider and key are configured; otherwise it says it is
     unavailable.
3. Restart the server: the data are still there. Restore last night's dump into an isolated
   database and compare.

Only after all three: announce the address to the team.
