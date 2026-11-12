# OSRIP platform upgrade (branch `feature/osrip-platform-upgrade`, November 2026)

This branch upgrades the existing application without rebuilding it. It contains, in order:

1. Everything already on GitHub in pull requests #2 and #3 (e-mail, phone and WhatsApp
   verification), since this branch starts from them.
2. The local work that had never been pushed (`feature/username-accounts-fast-research`):
   username accounts with recovery codes, faster web research and the 3-second opening.
3. The redesign that had never been pushed (`redesign/omani-decision-platform`).
4. The upgrade itself, described below.

Nothing has been merged into `main`. The pull request is for review.

## What was added

### Accounts, roles and groups (migration `0026_groups_custom_roles`)

- **Custom roles:** administrators create roles with exactly the permissions chosen. The four
  built-in roles (administrator, data manager, analyst, viewer) stay fixed.
- **Groups:** a group gives every member its roles and permissions. Removing someone takes them
  away on their next request. The administrator role is never given through a group, and the
  last administrator cannot be removed.
- **Enforcement:** `load_principal` combines a person's own roles, group roles, group permissions
  and individual grants. The server checks every request. Hiding a menu item is only a
  convenience.
- **Audit:** every change to roles, groups and memberships is written to the audit log.
- **Page:** `/admin/users` has Users, Roles and Groups tabs, in English and Arabic.
- **First administrator (`ensure-admin`):** takes a temporary password from a hidden prompt.
  It is never printed, never stored in a file and never committed. The person must change it at
  first sign-in, and the account has no permissions until then.

#### Setting up the administrator account "Azzan"

Run this on the machine that hosts the database, from `backend\`, in a normal terminal so the
password prompt is hidden:

```bash
python -m app.cli ensure-admin --username Azzan --name "Azzan"
```

1. Type a temporary password of 12 or more characters twice. It is not shown.
2. Sign in as `Azzan` with it. OSRIP asks for a new password before anything else.
3. Afterwards, change the password from the account page whenever needed. A one-time recovery
   code can be created there too.

If an account named Azzan already exists, the command changes nothing. Add `--promote` to give
that account the administrator role. No password is written anywhere in the repository.

### Navigation and design

- **Modules:** the sidebar is grouped in the requested order:
  1. Dashboard
  2. Economic and Development Axes
  3. Scenarios, Data and Analysis
  4. Oman Geographic Map
  5. Reports
  6. AI Research Assistant
  7. Administration: Data Management; Users, Roles and Groups; Service Health
  8. Account
- **Collapsing:** modules start open and can be collapsed; the choice is remembered in the
  browser.
- **Permissions:** administration items appear only to people who hold the permission, and the
  server checks again.
- **Glass surfaces:** translucent cards with a soft blur over a gradient background, in light and
  dark themes. They fall back to solid cards where the browser or the person's settings ask for
  reduced transparency.

### Service Health (administrators, `audit.read`)

`GET /admin/monitoring` now also returns:

- **API usage and costs** per provider over the last 24 hours and 30 days: calls, failures,
  refusals by OSRIP's own limits, tokens, average time, and estimated cost. A cost appears only
  for providers with prices in `OSRIP_PROVIDER_PRICES`; it is not the provider's invoice.
- **Data synchronisation:** each official-statistics feed with its schedule, last checks and
  releases awaiting approval.
- **System performance:** median, 95th percentile and slowest response time, the count of server
  errors, and the slowest route patterns. These cover the latest 2,000 requests of the running
  process, keyed by route pattern only, with no paths, queries or people.

The OpenAI (and other provider) **Test** buttons were already on the page. They make one small
live call, so they are shown only to people who also hold `user.manage`.

### Decision brief for each axis (`GET /analysis/{section}/brief`)

Each axis page (electricity, water, food security, trade) has a decision brief built by the
server. It uses only the published data of the selected data mode and contains:

- **Current performance:** the latest complete-year change, plus the latest within-year change
  when it is newer. The largest changes are marked.
- **Key factors:** shares of published parts in their registry total, for example electricity
  use by customer type or merchandise exports by group.
- **Strengths and weaknesses** by stated rules: supply up or down, demand against supply over the
  same periods, self-sufficiency, the trade balance.
- **Surplus and shortage:** self-sufficiency ratios, and export minus import for product groups
  of the same scope. Where no balance is published, as for electricity and water (no peak demand
  or reserve margins), the brief says so instead of estimating one.
- **Trade development**, **regional distribution** (shares of the national total), **data gaps
  and governorate coverage**, **risks** (the existing review rules R01–R04 and concentration),
  and **series that can start a scenario**.
- **Recommendations:** suggested next steps tied to the findings that produced them.
- **Provenance:** findings carry reference ids only. Sources, locations in the source, dataset
  versions, publication times and review status sit in a collapsed "Sources and verification"
  panel. A switch shows the references in the findings when wanted.

No AI and no estimates are used: every figure is a published value or a stated calculation over
values of the same unit, period and dataset version.

### Oman map (`/geography`)

- **Boundaries:** all 11 governorates and all 63 wilayats, from OpenStreetMap (ODbL), matched to
  the registry. The source, licence, simplification and the one correction (a Sur boundary
  mislabelled in OSM) are in `frontend/public/geo/README.md`. Every match is in
  `boundaries-report.json`. To rebuild, run `backend/scripts/build_boundaries.py`.
- **Shading:** a choropleth of published values per area, or of the indicator chosen in "Compare
  governorates", with the share of the national total on hover. Areas without a value are shown
  as "No data", never as zero. Clicking an area selects it, as the table does.
- **Basemap:** with the provider's tiles, the sea covers boundaries drawn out to the territorial
  limit. Without them, the boundaries are drawn on a plain background.
- **Not included:** terrain relief, because no elevation source is configured.

## Configuration you need to provide

None of these values belong in chat or in the repository. Put them in `backend/.env` on the
server.

| What | Settings | Notes |
|---|---|---|
| OpenAI answers and research | `OSRIP_OPENAI_API_KEY`, `OSRIP_OPENAI_MODEL`, `OSRIP_OPENAI_SEARCH_MODEL`; `OSRIP_ASSISTANT_PROVIDER=openai` and/or `OSRIP_RESEARCH_PROVIDER=openai` | Needs an OpenAI **API** account with billing, which is separate from a ChatGPT subscription. Not configured on this machine, so live OpenAI calls were **not tested**. The integration code and its mocked tests exist (see `docs/AI_PROVIDERS.md`). |
| Cost estimates on Service Health | `OSRIP_PROVIDER_PRICES` (JSON per provider) | Optional. Without it, costs show "No price set". |
| Daily limits | `OSRIP_PROVIDER_DAILY_CALL_LIMIT`, `OSRIP_PROVIDER_DAILY_BUDGET_USD` | Defaults: 500 calls a day, no budget. Raising them can increase spending. |
| Basemap tiles | `VITE_MAP_STYLE_URL` (frontend) | Defaults to OpenFreeMap. Set it to `none` to switch the basemap off; the boundaries still draw. |

## Deployment

1. Back up the database.
2. In `backend/`, run `alembic upgrade head`. This adds `0025_username_recovery` and
   `0026_groups_custom_roles`. Both have tested downgrades.
3. In `frontend/`, run `npm ci` and `npm run build`. The boundary files in `public/geo/` are
   copied into `dist/` automatically.
4. Restart the API and the sync worker.
5. Create or promote the first administrator with `ensure-admin` (see above).
6. Open Service Health. Check that the database shows as ready, that the migration is
   `0026_groups_custom_roles`, and which providers show as configured.

## Security review (this branch)

- **Access:** roles, groups and permissions are enforced on the server. The administrator role
  cannot be given through a group, and people cannot remove their own administrator role or the
  last one. Tests cover non-managers (403) and every refusal.
- **No secrets in the code:** no passwords or keys. `ensure-admin` reads the temporary password
  from a hidden prompt or an environment variable, and a change is forced at first sign-in.
- **Monitoring:** no prompts, answers, request bodies, query strings or user identifiers are
  stored or shown. Request timings are kept in memory by route pattern only.
- **Decision brief:** a public, read-only view of published data. It only reads.
- **Map:** the boundary files are static data. ODbL attribution is shown on the map, and the
  derived files are offered under the same licence.
- **Data changes:** sync releases are still staged for an administrator's approval unless
  automatic publishing is switched on per feed. No scraping or automatic overwrite was added.

## Not done, and why

- **Live OpenAI:** no API key is configured, so nothing could be tested end to end. The
  integration is in place.
- **Terrain relief and marine layers on the map:** they need an elevation source and a marine
  dataset that were not chosen.
- **PDF export of the decision brief:** reports already export to CSV, Excel and PDF, but the
  brief is not yet one of them.
- **AI-written interpretation of the brief:** deliberately left out of the brief. "Request
  analysis" on the axis page sends the selection to the assistant, which uses its grounding
  rules.
