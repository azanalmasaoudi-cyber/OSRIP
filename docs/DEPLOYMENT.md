# Deployment guide

**Status (2026-11-24): still only the interface is public. The API and database are not deployed:
no hosting account, server or DNS access was available, and nothing was created or paid for.**

Measured on 2026-11-24 with `python deploy\predeploy_check.py --env deploy\.env.example --url https://osrip.vercel.app`
(the `main` branch as deployed then):

| Check | Result |
|---|---|
| The page names itself OSRIP | yes (`<title>OSRIP</title>`) |
| `/api/v1/health/ready` | 404 from Vercel: no API behind the site |
| Admin and import routes refuse anonymous access | 404 from Vercel (nothing there), not the API's 401/403 |
| HSTS | present (Vercel) |
| Content-Security-Policy, framing denied | missing: added to both `vercel.json` copies on this branch (the same policy as `deploy/Caddyfile`) |
| `robots.txt` | missing: written by the build on this branch |

Measured again that evening, with the electricity and water branch built locally: 29 passed, 3
warnings, 16 failed. The site was unchanged (`main` as deployed). Every failure is one of these:
- the API is missing (readiness, sign-in providers, the four protected routes answering Vercel's 404);
- the headers and `robots.txt` wait for pull request #27;
- one known test value in `backend/tests/test_data_report_integration.py`, which is not a
  credential.
The electricity and water work is therefore **not deployed**.

**What this branch adds for a public release** (no hosting change):
- The page is named "OSRIP – Oman Smart Resource Intelligence Platform", with a description,
  Open Graph and Twitter tags.
- The build writes `robots.txt` (sign-in, account, administration and `/api/` disallowed). When a
  real public address is known it also writes a canonical link, absolute share-image links and
  `sitemap.xml`. That address is `VITE_PUBLIC_SITE_URL`, or on Vercel's production build the
  domain Vercel itself assigned (`VERCEL_PROJECT_PRODUCTION_URL`, today `osrip.vercel.app`). A local
  or non-https address is refused (`frontend/src/lib/siteUrl.ts`). Search engines index on their
  own schedule; nothing guarantees it.
- The production bundle calls the API at the relative `/api/v1` only: it has no `127.0.0.1` and no
  `localhost:<port>`. The only `http://localhost` strings are React Router's URL-parsing base,
  never fetched. `predeploy_check.py` now fails a built `frontend/dist` that calls a local
  address. Local development keeps its localhost proxy (`frontend/vite.config.ts`).

**Exactly what is missing for the whole platform to be public under the OSRIP name.** These are
decisions and accounts only the owner can provide:
1. **A host for the API and PostgreSQL**, with the owner's approval of any cost. Either:
   - an Ubuntu server for `deploy/` (Caddy, API, PostgreSQL, backups, migrations); or
   - a container host plus a managed PostgreSQL service.
   The owner creates the account; its password and verification codes stay with the owner.
2. **The public address.**
   - `https://osrip.vercel.app` already carries the project name. Proxying its `/api/` to the API
     host keeps one origin: the rewrite in step 2 of the next section.
   - A custom OSRIP domain needs DNS control by the owner.
3. **Server-side settings on that host only:**
   - `OSRIP_ENVIRONMENT=production`, `OSRIP_PUBLIC_BASE_URL`, `OSRIP_CORS_ORIGINS`;
   - `OSRIP_DATABASE_URL`, `OSRIP_CLIENT_HASH_KEY`;
   - the AI provider key.
4. **Data and accounts:**
   - Run the migrations, then load the reviewed data releases.
   - Create the administrator with `ensure-admin` (the password is prompted, never stored).
5. **Checks, before calling it public:**
   - `predeploy_check.py --url <address>` passing;
   - sign-in, the four sectors, Al Mulhim and the map, tested from a device outside this network.

**Status before (2026-11-13): only the interface is public; the API and database are not deployed.**
- **The published site:** https://osrip.vercel.app is the built interface, served by Vercel (see the next section).
- **No server behind it:** no OSRIP API or database runs there, so it cannot show data, sign anyone in or run Al Mulhim. Since this release it says so on every page.
- **`deploy/`:** the full configuration has not been built or run. Docker is not installed in the development environment, and no server, domain or DNS access was provided.
- **Decisions needed:** creating any paid resource, or making the API and data public, needs an explicit decision by the project team and supervisor first.

`localhost` addresses in this repository are development addresses only.

## The published site on Vercel (https://osrip.vercel.app)

**What it is.** A Vercel project (`osrip`) created through the v0 integration.
- **What it serves:** it builds `main` on every merge and serves the built interface only. Vercel serves static files and does not run the FastAPI server or PostgreSQL.
- **Addresses:** `https://osrip.vercel.app` is public. The team and deployment addresses (`osrip-…-azan-f208.vercel.app`) ask for a Vercel sign-in (deployment protection).
- **Root folder:** this repository cannot see the project's root-folder setting, so the same `vercel.json` is kept in `frontend/` and at the repository root. Vercel reads the one in the project's root folder and ignores the other. A unit test keeps the two identical.

**What happened before 2026-11-13 (measured on the live site).**

| Request | Answer from Vercel | What the page showed |
|---|---|---|
| Every `/api/v1/...` call (`auth/me`, `observations`, `analysis/.../brief`, ...) | `404`, `X-Vercel-Error: NOT_FOUND`, body `{"error": {"code": "404", "message": "The page could not be found"}}` | Six "Data unavailable" cards on the dashboard; "Something went wrong … Technical detail: The page could not be found" on the sector, map, forecast, report, library and source pages; "Authorized access only" on Account, Users and Service Health; Al Mulhim "Ready" |
| Opening `/overview`, `/energy/electricity` or any address other than `/` directly, or refreshing it | `404` text page | Vercel's "page not found" |

Vercel's JSON 404 has the same shape as OSRIP's own errors, so the interface took it for an API error.

**What changed on branch `fix/backend-connectivity-and-error-states`.**
- **`vercel.json`:** every address without a file extension is answered with `index.html`, so pages open and refresh. `/api/` is never rewritten.
- **The interface:**
  - It treats an answer as the API's own only when it carries `X-Request-ID` (every OSRIP release) or `X-OSRIP-API` (added in this release).
  - Anything else in the API's place counts as "not connected to the OSRIP server". A gateway error means "not responding".
  - A banner on every page says so, with Try again. Every panel, card and the assistant give the same reason in Arabic or English.

**What it still needs before data, sign-in and Al Mulhim work there (a decision for the team).**
1. **An HTTPS host for the API and a persistent PostgreSQL database.** Options are in "What is needed from the team" below:
   - a small virtual machine running `deploy/` (US$5–25 a month, or free on university infrastructure);
   - a container host together with a managed PostgreSQL service, usually with a free tier that sleeps or is size-limited.

   Each needs an account the owner creates; nothing was created or paid for.
2. **The same-origin proxy.** Once the API has an address, add this rule as the first entry of `rewrites` in both copies of `vercel.json`. The browser then sees one origin, so the session cookie (`SameSite=Strict`) and the CSRF check work without CORS:
   ```json
   { "source": "/api/:path*", "destination": "https://<api-host>/api/:path*" }
   ```
3. **The API's settings, on the API host only** (never in a `VITE_*` variable):
   - `OSRIP_ENVIRONMENT=production`;
   - `OSRIP_PUBLIC_BASE_URL=https://osrip.vercel.app` and `OSRIP_CORS_ORIGINS=["https://osrip.vercel.app"]`;
   - `OSRIP_DATABASE_URL`, `OSRIP_CLIENT_HASH_KEY` and the AI provider key.
4. **The data.** A new database starts empty. Run the migrations (`alembic upgrade head`), then load the same reviewed releases as the development database:
   - `python -m app.cli import-reference-pack --publish`;
   - the reviewed imports in `docs/data-imports/`.

   Then create the administrator with `ensure-admin`; its password is prompted, never stored. Synthetic data is never loaded as official figures.
5. **Checks.** Test every page against that API, in Arabic and English, before calling the site working.

## Requested hostname: https://osrip.project.com (2026-10-02)

The configuration (`deploy/.env`, `deploy/.env.example`, `deploy/laptop_server.ps1`) now
uses **osrip.project.com**. Whether it can go live depends on DNS, which only the owner of
the parent domain controls:

* `project.com` is an existing domain whose name servers are `ns65/ns66.domaincontrol.com`
  (GoDaddy DNS). On 2026-10-02 `osrip.project.com` had no DNS record. No access to that
  zone was available in this environment, and nothing indicates that the project owns it.
* **Exact requirement:** whoever manages the `project.com` DNS zone must add a record for
  the host `osrip`, either an **A** record pointing to the server's public IPv4 address
  (Caddy then obtains the HTTPS certificate automatically) or a **CNAME** to a hosting
  provider's address. For the laptop tunnel the zone must be on that owner's Cloudflare
  account instead.
* If that is not possible, use a name you control (for example `project.osrip.com` on the
  team's `osrip.com` zone at IONOS, prepared earlier: set `OSRIP_DOMAIN`,
  `OSRIP_PUBLIC_BASE_URL` and `OSRIP_CORS_ORIGINS` in `deploy/.env`) or the hosting
  provider's own address. Only the domain name changes; everything else stays the same.

Nothing was purchased, registered or published, and **there is no public URL**.

Production checklist for this release (all in the repository; `python deploy\predeploy_check.py`
checks the configuration):

| Requirement | Where it is handled |
|---|---|
| Production builds | `deploy/Dockerfile.web` (Vite build served by Caddy), `deploy/Dockerfile.api` |
| Persistent database and migrations | `pgdata` volume; the one-shot `migrate` service runs `alembic upgrade head` (0001-0011) before the API starts |
| HTTPS | Caddy with automatic certificates for `OSRIP_DOMAIN`; HSTS |
| API and sign-in callback URLs | Same origin (`/api` proxied); `OSRIP_PUBLIC_BASE_URL` builds e-mail links and the Google/Microsoft callback `https://<host>/api/v1/auth/oidc/<provider>/callback` |
| Restricted CORS | `OSRIP_CORS_ORIGINS` must list exact `https://` origins; the API refuses to start in production otherwise |
| Secure sessions | HttpOnly, Secure, SameSite=Strict cookies, CSRF tokens, idle and absolute expiry |
| Server-side secrets | Only in `deploy/.env` on the server (git-ignored, excluded from images); the pre-publication check fails on any key-like `VITE_*` variable |
| Health checks | `GET /api/v1/health/ready` (database and migration), used by the container health check |
| Backups | Nightly `pg_dump` service with pruning; restore drill below |
| Direct-route refresh | Caddy `try_files {path} /index.html`; the laptop server does the same |
| Microphone and audio | `Permissions-Policy: microphone=(self)`; CSP `media-src 'self' blob:` for synthesised speech |

## Deploying to https://project.osrip.com (prepared 2026-09-27; superseded by the hostname above)

Prepared on the development machine:

| Item | Where |
|---|---|
| Deploy SSH key (ed25519, no passphrase, opens only this server) | `%USERPROFILE%\.ssh\osrip_deploy` (private, never copied), `osrip_deploy.pub` (goes on the server) |
| Production settings with fresh secrets | `deploy/.env` (not in images, not in version control). The pre-publication check passes (22/22). E-mail, assistant and SMS are off until they are configured |
| One-time server setup | `deploy/bootstrap_server.sh`: Docker and Compose from Ubuntu packages, a firewall allowing only 22/80/443, swap on small machines |
| Deploy from Windows | `deploy/deploy_to_server.ps1` checks `.env`, checks that DNS points at the server, copies the source (no secrets or build output, about 2.3 MB), starts the stack, loads the synthetic data and probes the live site |

Steps for the domain owner (these need your accounts; nobody else can do them):

1. Create an **Ubuntu 24.04** server with a public IPv4 address and at least 2 GB of RAM
   (1 GB works with the swap the setup adds, but builds slowly). Add the contents of
   `osrip_deploy.pub` as its SSH key.
2. In **IONOS**, go to Domains & SSL, then osrip.com, then DNS. Add a record of type
   **A**, host name **project**, pointing to the server's IPv4 address.
3. Run, or ask Claude to run:
   `powershell -ExecutionPolicy Bypass -File deploy\deploy_to_server.ps1 -Server <IPv4> -Bootstrap`.
   The first run downloads Ubuntu packages and the Docker images (postgres, python,
   node, caddy), then Caddy obtains the HTTPS certificate.
4. Create the first administrator yourself; the password is prompted, never passed as
   an argument:
   `ssh -i %USERPROFILE%\.ssh\osrip_deploy root@<IPv4>`, then
   `cd /opt/osrip/src && docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api python -m app.cli create-user --email you@example.org --name "Administrator" --role administrator`.
5. To update later, run the same script without `-Bootstrap`.

## Temporary public demonstration (from the development laptop)

On 2026-09-27 a temporary public copy was run from the development laptop through a
Cloudflare Quick Tunnel (a random `https://….trycloudflare.com` address, no account).
It works only while the laptop is on and both processes are running. The address
changes on every restart, and Cloudflare gives no uptime guarantee.

```powershell
# once (from backend\): separate database osrip_public, synthetic data, least-privilege role
python scripts\serve_public.py setup
# terminal 1: the tunnel prints the public address
& "$env:LOCALAPPDATA\OSRIP-dev\tools\cloudflared.exe" tunnel --no-autoupdate --url http://127.0.0.1:8090
# terminal 2: production-mode server for that address (builds the interface first)
python scripts\serve_public.py serve --url https://<printed-name>.trycloudflare.com
# optional: an administrator on the public copy (the password is prompted)
$env:OSRIP_DATABASE_URL = (python scripts\devdb.py url osrip_public)
python -m app.cli create-user --email you@example.org --name "Administrator" --role administrator
```

Settings for the demo:

- production mode, Secure cookies, and a random key kept in
  `%LOCALAPPDATA%\OSRIP-dev\public.env` (outside the repository);
- e-mail (and so self-registration) and the assistant are off;
- the same security headers as the Caddyfile.

The live pre-publication probes passed (12 of 12).

**State on 2026-10-02 (12:30).** A demo started at 08:35 that day was still running locally:
`serve_public.py serve` (API 0.7.0 code) on 127.0.0.1:8090 and `cloudflared` for
`https://having-bean-appointments-caused.trycloudflare.com`. That hostname no longer
resolved in DNS, from this machine or from outside, so **the tunnel was not reachable and
there was no working public URL**. While checking release 0.8, `osrip_public` was migrated
to 0011 (additive) and the demo's interface folder was rebuilt with the 0.8 interface. The
0.7 API still running there is compatible with it, but restart it to run 0.8 throughout: stop
both processes, start a new tunnel, then `python scripts\serve_public.py serve --url <new
address> --skip-build` (it now migrates and re-grants by itself).

Running the live check found two defects, and both are fixed in the Caddyfile too:

- the CSP blocked the self-hosted fonts that the build inlines as `data:` URIs;
- the app shell was cacheable, so browsers kept the old headers.

Zod is set to its no-compile mode, so it no longer triggers CSP `eval` violations.

## What is needed from the team

| Item | Why | Approximate cost (check current prices) |
|---|---|---|
| A Linux virtual machine (2 vCPU, 2–4 GB RAM, 40 GB disk) with Docker | Runs the database, API, web server and backups | About US$5–25 a month at common providers, or free on university infrastructure |
| A domain or sub-domain, and access to its DNS | HTTPS certificates and the public address | About US$10–20 a year, or free as a university sub-domain |
| Off-host backup storage (object storage or a second machine) | A backup on the same disk is not recovery | A few US dollars a month for a few GB |
| SMTP relay credentials | Confirmation, recovery and sign-in e-mails (or set `OSRIP_EMAIL_BACKEND=disabled`) | Usually free through the institution |
| Optional: Anthropic API key | Enables the assistant | Pay per use; the per-user limits (5 per minute, 30 per hour) bound it |
| Optional: Google and Microsoft OAuth clients | Optional sign-in | Free |

Alternatives: a managed PostgreSQL service (often US$15+ a month) instead of the
`db` container. It needs the same `OSRIP_DATABASE_URL` and gives you the provider's
backups, but you still need a restore drill. A platform-as-a-service can also run the
two Dockerfiles, provided it offers persistent PostgreSQL and HTTPS on a custom domain.

## Pre-publication check

```bash
python deploy/predeploy_check.py                                   # configuration + repository
python deploy/predeploy_check.py --url https://<your-domain>       # after start-up: live probes
```

It fails unless:

- the environment is `production`;
- the secrets are real and at least 32 characters;
- the public address is `https://`, matches the domain and is the only CORS origin;
- cookies are Secure;
- the development mail outbox and the assistant test double are off;
- the OAuth ID and secret are set in pairs (it prints the exact redirect URIs to register);
- no credential pattern appears in the source tree;
- `.dockerignore` keeps `.env` files out of images;
- the web image uses the API adapter;
- migrations run before the API, and a backup service and an API health check exist.

With `--url` it also checks:

- readiness;
- the HSTS, CSP and framing headers;
- that uploads, user administration, monitoring and audit refuse anonymous access;
- that the development outbox is absent;
- that cookies are Secure and HttpOnly;
- that synthetic data is labelled.

Run on 2026-09-26 against `deploy/.env.example`: the repository checks passed and,
as expected, the placeholder values failed.

## Target layout

One Linux host (a small virtual machine is enough for a demonstration) running
four containers with Docker Compose:

| Service | Image | Role |
|---|---|---|
| `db` | `postgres:17` | Database, data in the `pgdata` volume |
| `migrate` | `deploy/Dockerfile.api` | Runs `alembic upgrade head` once, then exits |
| `api` | `deploy/Dockerfile.api` | FastAPI under uvicorn (`OSRIP_WORKERS`, default 2), not exposed publicly. Health check: `/api/v1/health/ready` (database + migrations at head) |
| `backup` | `postgres:17` + `deploy/backup.sh` | Nightly `pg_dump -Fc` into the `backups` volume, keeps `BACKUP_KEEP_DAYS` (14) |
| `web` | `deploy/Dockerfile.web` | Built React app served by Caddy, which proxies `/api` to `api` and obtains HTTPS certificates automatically |

HTTPS is mandatory: session cookies are `Secure`, and the API refuses to start
outside `development` with the development client-hash key or non-Secure cookies.

## Steps

```bash
# on the host, from the repository root
cp deploy/.env.example deploy/.env
# edit deploy/.env: POSTGRES_PASSWORD, OSRIP_CLIENT_HASH_KEY (long random values),
# OSRIP_DOMAIN and OSRIP_CORS_ORIGINS (the public https:// address), VITE_MAP_STYLE_URL,
# and optionally VITE_MAPTILER_KEY (restricted to OSRIP_DOMAIN; docs/MAP.md)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build

# first run only: seed the synthetic fixtures and create accounts
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api python -m app.cli seed-synthetic
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api \
    python -m app.cli create-user --email admin@example.org --name "Administrator" --role administrator
```

The DNS name in `OSRIP_DOMAIN` must point at the host, with ports 80 and 443 open,
before Caddy can obtain a certificate.

Stop: `docker compose -f deploy/docker-compose.yml down` (data stays in the volumes).
Update: pull the new code, then `up -d --build`; `migrate` applies new migrations first.

## Verification after deployment (not yet done)

1. `https://<domain>/api/v1/health` returns `{"status":"ok"}`; `/api/v1/health/db` reports the database.
2. Run the full-stack suite against the deployment, or at least the journey:
   sign in, upload, validate, approve, publish, report.
3. Check that the session cookie is `Secure; HttpOnly; SameSite=Strict` and that the
   Content-Security-Policy does not block the map (it allows only `api.maptiler.com`,
   `tiles.openfreemap.org` and `elevation-tiles-prod.s3.amazonaws.com`; adjust it if
   `VITE_MAP_STYLE_URL` names another host). With a MapTiler key, the note under the map
   should name MapTiler and must not say it fell back.
4. Repeat the performance workload on the host and record the results separately
   from the laptop measurements.
5. Run a backup and a restore into a separate database on the host (next section).

## Backups

Local exercise: `backend/scripts/backup_restore_drill.py` (passed on 2026-09-25, see
TEST_RESULTS.md). For a deployment, schedule `pg_dump -Fc` from the `db` container,
copy the files off the host, and repeat the restore exercise into a separate database
before calling recovery verified:

```bash
docker compose -f deploy/docker-compose.yml exec db pg_dump -U osrip -Fc osrip > osrip-$(date +%F).dump
```

The `backup` service in `docker-compose.yml` does this nightly. It keeps 14 days
by default, and writes each dump to a temporary name so that a failed dump never
replaces a good one. Copy the `backups` volume off the host (for example with
`rclone` or `restic` from the host's cron). Off-site storage and point-in-time
recovery remain decisions for the hosting team.

## Monitoring

- **Service health**, at `/admin/health` (administrators with `audit.read`), shows:
  - readiness;
  - the release and migration;
  - each connected service's status and recent failures;
  - grouped server and browser errors, with personal data removed.
- **Uptime checks**, from any external monitor: `GET /api/v1/health/ready`, where 200
  means ready. None is set up, because there is no public address.
- **Logs:** `docker compose logs api`. Each 500 response carries a `request_id` that
  also appears in the error record.

## Before a release

1. Put the code under version control (git is not installed on the development
   machine, so there is no commit history). Tag the release and record the commit
   hash in TEST_RESULTS.md, as booklet §3.16 requires.
2. Commit `frontend/package-lock.json` and `backend/requirements.lock`.
3. Decide the tile provider (SPEC_CONFLICTS C28).
4. Replace every placeholder in `deploy/.env`; never commit that file.

## Unresolved limitations

| Area | Limitation |
|---|---|
| Data | No verified-source data. Every value is a declared synthetic fixture. Commodity product forms and HS codes are unconfirmed (C14) |
| Geography | No licensed current boundary geometry; the map cannot select or colour areas (C8). No service areas registered |
| Forecasting | No eligible verified series: official monthly data is not loaded, and annual data since 2022 is too short. History thresholds are project assumptions (C10). Tested on synthetic monthly data only |
| Performance | Measured on a laptop only. Under 10 concurrent clients with one worker, p95 4.7 s (two-second target not met). Not measured on server hardware, with several workers, or over a network |
| Deployment | Configuration not built or run; no hosting account or domain; no public URL; CSP untested |
| Backups | Local exercise only; no schedule, off-site copy or point-in-time recovery |
| Accessibility and devices | Automated keyboard, focus, overflow (6 widths, 360–1920 px, EN and AR), reduced-motion and contrast checks only. No screen-reader test or axe audit. Edge (Chromium) only: no Firefox or Safari/WebKit run, and no real phones or tablets |
| Language | Arabic texts drafted by the development team; not reviewed by a qualified Arabic speaker. API error messages are English only |
| Security | Password reset by e-mail only. Rate limits on sign-in, e-mail and SMS requests are per process. No external penetration test |
| SMS | No provider selected: no adapter, no live delivery, and phone registration disabled (C40). After a provider is chosen and the adapter written, run `backend/scripts/sms_acceptance.py` with an authorized number before enabling it |
| Evaluation | Usability study not conducted (needs college clearance); supervisor confirmation of the platform choice pending (C12) |
| Scale | The whole electricity calculations response for 63 monthly series is 286 kB; larger datasets need pagination (not implemented) |
| Versioning | No git repository, so no commit hash for this release |
