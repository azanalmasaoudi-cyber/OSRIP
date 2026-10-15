# OSRIP architecture

Follows booklet §3.10–3.12 (Fig. 3.1 and 3.2). This file describes what exists in the
repository now and what is planned; see `VERIFICATION.md` for what has actually run.

```
Browser (React + TS)            Vite dev proxy    API (FastAPI)                     PostgreSQL 15+
┌──────────────────────┐  /api  ┌──────────┐     ┌─────────────────────────┐  SQL  ┌──────────────────────┐
│ pages / layout       │──────▶ │ same     │───▶ │ routes (thin)           │─────▶ │ reference entities   │
│ api/ adapters        │        │ origin   │     │ deps: session, CSRF,    │       │ sources, versions,   │
│   mockAdapter        │        └──────────┘     │   require(permission)   │       │ observations         │
│   httpAdapter (zod)  │                         │ services: accounts,     │       │ users, roles, grants,│
│ api/auth, api/imports│                         │   imports (csv, valid-  │       │ sessions             │
│ i18n (en, ar + RTL)  │                         │   ation, workflow),     │       │ import_job/_row      │
└──────────────────────┘                         │   observations, audit   │       │ analysis/recommend./ │
                                                 │ domain/ calculations    │       │ reports, audit_event │
                                                 │ models (SQLAlchemy 2.0) │       │ + triggers/checks    │
                                                 └─────────────────────────┘       └──────────────────────┘
```

## Separation of concerns

| Concern | Location | Rule |
|---|---|---|
| Business calculations | `backend/app/domain/calculations.py` | Pure functions, `Decimal`, return `CalcResult(status, value, reason, caveats)`. Single source of truth — the frontend never re-implements formulas. |
| Comparability guards | `backend/app/domain/compatibility.py`, `services/observations.py` | Units (same dimension *and* code), periods, coverage. Observation reads refuse to mix frequencies or units for one indicator. |
| Section calculations | `backend/app/services/analysis/sections.py` | Chooses compatible published inputs (one dataset version per series; conflicting sources withheld), calls the pure domain functions, and returns each result with its formula, inputs and provenance, caveats and explanatory notes, or an explained reason it is unavailable. Wording comes from `app/domain/explanations.py` (EN/AR), shared by the UI, CSV exports and reports. |
| Review rules | `backend/app/services/analysis/rules.py`, `runs.py` | R01–R04 turn calculations into cards: observation, rule and threshold (a parameter recorded with the run), inputs, limitations and next investigation. Cards are immutable; reviews are append-only and the latest review is the status. |
| Reports | `backend/app/services/reports.py` | Created with frozen filters, assumptions, observations, calculations, cards and source versions (`report_input`); a trigger forbids later changes. Owners choose private or published. |
| Exports | `backend/app/services/exports.py` | Every CSV carries the mode label, filters, assumptions and versions; missing values are empty cells; text cells are formula-safe. |
| Import validation | `backend/app/services/imports/validation.py` | Pure: rows + mapping + reference snapshot → one result per row with stable issue codes. Unit-tested without a database. |
| Import workflow | `backend/app/services/imports/workflow.py` | `dataset_version.status` is the lifecycle (draft → validated → approved → published → superseded, or rejected). Each step owns one transaction and a row lock; publication is all-or-nothing and idempotent. |
| Authentication | `backend/app/services/accounts.py`, `core/security.py` | Server-side sessions: opaque token in an HttpOnly, SameSite=Strict, Secure cookie; only SHA-256 digests stored; Argon2id passwords; login throttling; session-bound CSRF token for unsafe methods. |
| Authorization | `backend/app/api/deps.py` | `Depends(require(Permission.X))` on every protected route. Permissions are reloaded from the database on every request (suspension, role removal and revoked grants apply at once). Publish/approve are explicit grants (SPEC_CONFLICTS C6). Denials are audited in a separate transaction. |
| Data integrity | `backend/alembic/sql/*.sql` | Enforced in the database: mode inheritance via composite FKs, natural key `UNIQUE NULLS NOT DISTINCT`, unit-dimension and frequency/period checks, verified ⇏ fictional partners or synthetic-only commodities, synthetic ⇏ publisher or real partners, verified sources must name a file or table (not a catalogue page), immutability of published observations and approved import rows, one published version per source, append-only audit events and review history. |
| Migrations | `backend/alembic/versions` + `app/db/sql_files.py` | Reviewed SQL files executed verbatim through Alembic. |
| API contracts | `backend/app/schemas/` | Pydantic models; stable error envelope `{error: {code, message, details?}}`; no internals in errors. |
| Frontend data access | `frontend/src/api/` | `DataAdapter` interface; UI code never calls `fetch` directly; responses validated with zod. Query keys include the data mode. |
| Datasets | `backend/fixtures/booklet_synthetic_fixtures_v1.csv`, `frontend/src/api/syntheticFixtures.ts` | Synthetic only, no publisher, fictional partners, invented commodity. Seeded through the import workflow (`python -m app.cli seed-synthetic`). No verified data exists in the repo. |
| UI state that must survive language switch | URL query (`?mode=`, page filters) | Language lives in i18next; switching changes labels/direction only. |

## Data modes

`verified_source` (default) and `synthetic`. They are separate at every layer:
DB (`data_mode` inherited source → version → observation / import / analysis run /
report via composite FKs), API (`data_mode` required on every observation read and
export; a version of one mode cannot be read through the other), cache (mode in the
query key), exports (mode in the file name and heading), and UI (banner and badge on
every series card). In verified mode nothing falls back to synthetic values.

## Import workflow (booklet 3.12)

| Step | Endpoint | Permission |
|---|---|---|
| Register provenance | `POST /sources` | `source.register` |
| Upload (private, ≤ 5 MB CSV, checksum) | `POST /imports` | `import.create` |
| Map columns | `PUT /imports/{id}/mapping` | `import.validate` + owner or `import.manage_any` |
| Validate | `POST /imports/{id}/validate` | same |
| Review errors | `GET /imports/{id}/rows`, `GET /imports/{id}/errors.csv` | `import.read` |
| Approve (must acknowledge the rejected-row count) | `POST /imports/{id}/approve` | `import.approve` (explicit grant) |
| Publish (one transaction, idempotent) | `POST /imports/{id}/publish` | `import.publish` (explicit grant) |
| Reject | `POST /imports/{id}/reject` | `import.reject` |
| Public read | `GET /observations`, `GET /observations/export.csv`, `GET /sources`, `GET /commodities` | none |

## Calculations, review cards and reports (booklet 3.13, Table 3.5)

| Route | Purpose | Control |
|---|---|---|
| `GET /analysis/{section}` (+ `/export.csv`) | Transparent calculations for the filters (`commodity`, `area`, `frequency`, `period_from`/`period_to`, `stock_assumption`, `dataset_version_id`) | Public, published data only |
| `POST /analysis-runs` | Run R01–R04 over the published snapshot of a mode | `analysis.run` |
| `GET /recommendations` | Cards of the latest run with their current status | Public |
| `GET/POST /recommendations/{id}/reviews` | Review history / append a review | Read: analysts and reviewers. Write: `recommendation.review` |
| `POST /reports`, `PUT /reports/{id}/visibility` | Freeze a section view as a report; publish or unpublish it | `report.create`, owner |
| `GET /reports`, `GET /reports/{id}` (+ `/export.csv`) | List / read / export | Owner, or anyone if published |

## Geography and forecasting (booklet 2.4, 3.11, 3.14, 4.6)

| Route | Purpose | Control |
|---|---|---|
| `GET /areas` | Registry coverage: national area, 11 governorates, 63 wilayats with EN/AR names, parents, codes (ISO 3166-2 or OSRIP), verification date, references and the stored completeness check. No coordinates or geometry | Public |
| `GET /areas/coverage?data_mode=` | Statistical coverage: published observations per exact area and indicator. Areas without observations are absent (the UI says "No data"); nothing is inherited from a parent or allocated from a national total | Public |
| `GET /observations?area=` | Observations recorded for that exact area (existing endpoint) | Public |
| `GET /forecast/eligibility?data_mode=` | Every published series checked against the experiment's requirements, with reasons | Public |
| `POST /forecast-runs` | Records the experiment definition, then its held-out predictions (`forecast_prediction`, append-only). Ineligible series are recorded as withheld with reasons (T10) | `analysis.run` |
| `GET /forecast-runs`, `GET /forecast-runs/{id}` | Runs with predictions, errors, MAE/RMSE recomputed from the stored rows | Public |

Pure logic lives in `app/domain/forecasting.py` (eligibility, rolling-origin
evaluation, baseline and candidate, metrics); `app/services/forecasting.py` and
`app/services/geography.py` read the database. The interface's basemap
(`frontend/src/components/geography/`) is MapLibre GL JS, loaded lazily, with
the tile provider's attribution; it has no data layers (SPEC_CONFLICTS C8).

## Planned next increments (booklet §3.1 order)

1. A licensed boundary layer linked to registry codes, if one becomes available (C8).
2. Comparison views across dataset versions (FR04) beyond the per-series changes.
3. A water source-type dimension, if a source publishes one (SPEC_CONFLICTS C24).
