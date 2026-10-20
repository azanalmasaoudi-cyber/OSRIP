# OSRIP API (v1)

Generated reference: [`docs/api/openapi.json`](api/openapi.json) (OpenAPI 3, exported
from the running code; last regenerated 2026-10-20 after migration 0020: 125 paths, 143 operations). With the API running, interactive
documentation is at `http://localhost:8010/docs` and `http://localhost:8010/redoc`.
Every route below is exercised by the integration or browser tests listed in
[TRACEABILITY.md](TRACEABILITY.md).

Base path: `/api/v1`. The interface calls it on the same origin (Vite proxy in
development, Caddy in the deployment configuration).

## Conventions

| Topic | Rule |
|---|---|
| Data mode | Every data read takes `data_mode=verified_source` or `data_mode=synthetic`. The modes are never mixed; a dataset version of one mode cannot be read through the other |
| Values | Decimal strings, unrounded. Missing values are `null` in JSON and empty cells in CSV, never `0` |
| Metadata | Observations come with indicator (definition, limitation), unit, frequency, area, source, dataset version and data mode |
| Compatibility | A read that would mix frequencies or units for one indicator is refused: `422 incompatible_series`, with the combinations in `details`. Add `frequency=` to choose one |
| Errors | `{"error": {"code": "...", "message": "...", "details": ...}}`. Codes are stable; messages are English; no internals or credentials are returned. Database outages return `503 database_unavailable` |
| Sessions | `POST /auth/login` sets an HttpOnly, SameSite=Strict, Secure session cookie and a readable `osrip_csrf` cookie |
| CSRF | Every POST, PUT and DELETE made with a session must send the `osrip_csrf` value in the `X-CSRF-Token` header |
| Authorization | Checked on the server for every protected route, with permissions reloaded from the database on each request. Denials return 401 (not signed in) or 403 (`permission_denied`) and are audited |
| Exports | CSV files carry the data-mode label, filters, assumptions and dataset versions in `#` lines; text cells are protected against spreadsheet formulas |

## Roles and permissions

Roles: `viewer`, `analyst`, `data_manager`, `administrator` (public viewers need no
account). `import.approve` and `import.publish` are per-user grants that no role
implies (SPEC_CONFLICTS C6).

## Endpoints

### Public metadata and data

| Method and path | Purpose |
|---|---|
| `GET /health`, `GET /health/db`, `GET /health/ready` | Liveness; database reachability; readiness (database reachable and migrations at head; 503 otherwise) |
| `POST /telemetry/client-errors` `{kind, message, location}` | Browser error report. No cookies needed. E-mails, long tokens and query strings are removed before storage. At most 30 per hour per client (429) |
| `GET /indicators` | Definitions, dimensions, value types and compatible units |
| `GET /commodities?data_mode=` | Shared commodity registry (synthetic-only commodities appear in synthetic mode only) |
| `GET /observations?data_mode=&section=&indicator=&area=&commodity=&partner=&flow=&frequency=&period_from=&period_to=&dataset_version_id=` | Published observations with provenance. Without `dataset_version_id`, each source contributes its one published snapshot. `partner=total` selects stated totals |
| `GET /observations/export.csv?…` | The same selection as CSV |
| `GET /areas` | Registry: national area, 11 governorates, 63 wilayats with EN/AR names, parents, codes, verification date, references and the completeness check. No coordinates or geometry |
| `GET /areas/coverage?data_mode=` | Published observations per exact area and indicator; areas without data are absent ("No data") |
| `GET /analysis/{section}?data_mode=&commodity=&area=&frequency=&period_from=&period_to=&stock_assumption=&dataset_version_id=` | Transparent calculations (formula, inputs, versions, caveats, reasons). `section` is `electricity`, `water`, `food_security` or `trade`; `stock_assumption` is `assumed_zero` (default), `unknown` or `known` |
| `GET /analysis/{section}/export.csv?…` | Calculations as CSV |
| `GET /recommendations?data_mode=&section=` | Review cards of the latest rule run with their current status |
| `GET /forecast/eligibility?data_mode=` | Every published series checked for the forecasting experiment, with reasons |
| `GET /forecast/overview?data_mode=` | Each forecast target (electricity consumption and generation, gross and net generation, water consumption and production, food and crop production, capture fish landings, merchandise exports and imports, and import and domestic-export quantities and values): `available` or `insufficient_data` with reasons, the latest run per series, and `insufficient_label` ("Insufficient comparable historical data for a reliable forecast.") |
| `GET /forecast-runs?data_mode=`, `GET /forecast-runs/{id}` | Recorded forecast runs. Each has the definition (fixed before fitting), backtest predictions, errors, MAE and RMSE for every model and the selected model. It also has the future `outputs` (estimate, 80% and 95% bounds, or `null` when an interval cannot be estimated), the `interval_method`, the `history`, the `training_cutoff`, a deterministic EN/AR `explanation`, `assumptions` and `estimate_label` |
| `GET /forecast/conditions?data_mode=` | Candidate development conditions per domain (booklet Table 3.9): each `measured` (with the published indicators that measure it) or `scenario_assumption`, with the evidence still needed. Not causes; no coefficients |
| `GET /reference-pack` | The loaded curated reference pack: research cutoff, record counts, every reference (S01–S08) and the documented conflicts (Q01–Q09) |
| `GET /scenarios/series?data_mode=` | Series with a complete published value that a scenario can start from |
| `GET /scenarios/projection?data_mode=&series_id=&growth_pct=&years=&one_off_pct=` | Hypothetical arithmetic: base × (1 + one-off) × (1 + growth)^k. Growth −50 to 50 %, one-off −100 to 200 %, 1–10 years. Labelled as not a forecast |
| `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/export.csv` | Published reports for everyone; private reports for their owner only (others get 404) |

### Authentication

| Method and path | Purpose |
|---|---|
| `POST /auth/login` `{email, password}` | Sign in. Unknown account and wrong password get the same answer; 5 failures in 15 min → 429 |
| `POST /auth/logout` | Revokes the session |
| `GET /auth/me` | Current user, roles, permissions and whether the e-mail is confirmed (anonymous if not signed in) |
| `GET /auth/providers` | Which sign-in methods are configured: password, registration, magic link, e-mail delivery mode, Google, Microsoft, and `sms` `{available, status: disabled or not_configured or test or configured, default_country, resend_seconds, code_minutes}`, plus the offered `country_codes` |
| `POST /auth/register` `{email, display_name, password}` | 202 with the same answer whether or not the address exists. Creates an unconfirmed account with the Viewer role only and sends a confirmation link |
| `POST /auth/verify-email` `{token}`, `POST /auth/verify-email/resend` `{email}` | Confirm the address (single-use, 24 h) / send a new link |
| `POST /auth/password/forgot` `{email}`, `POST /auth/password/reset` `{token, password}` | Recovery link (single-use, 30 min). A reset revokes every session |
| `POST /auth/magic-link` `{email}`, `POST /auth/magic-link/consume` `{token}` | Sign-in link for confirmed accounts (single-use, 15 min) |
| `GET /auth/oidc/{google or microsoft}/start?intent=sign_in or link` | Redirects to the provider (404 when not configured). `link` needs a signed-in session |
| `GET /auth/oidc/{provider}/callback` | Validates state, browser binding, PKCE and the ID token; redirects to `/account` or `/sign-in?error=…` |
| `GET /auth/identities`, `DELETE /auth/identities/{id}` | Linked providers of the signed-in user; the last sign-in method cannot be removed |
| `POST /auth/phone/request` `{country_code (default +968), number, purpose: sign_in or link}` | Sends a code by SMS through the configured provider. Returns 202 `{challenge_id, phone_masked, expires_in, resend_after, max_attempts}`, never the code, with the same shape whether or not the number has an account. `link` needs a signed-in session. Errors: `sms_unavailable` (503), `invalid_phone` (422), `sms_resend_cooldown` (429, `retry_after`), `sms_number_limit` / `sms_client_limit` (429), `sms_busy` (503), `sms_invalid_number` / `sms_undeliverable` (422), `sms_provider_unavailable` (503) |
| `POST /auth/phone/verify` `{challenge_id, code, display_name?}` | Checks the code through the provider. `sign_in` opens a session and creates an ordinary (Viewer) account for a new number; `link` adds the number to the signed-in account. Returns `{status: registered or signed_in or linked, me}`. Errors: `sms_code_incorrect` (400, `attempts_left`), `sms_code_expired`, `sms_too_many_attempts`, `sms_challenge_invalid` (unknown, spent or another session's), `phone_taken` (409, never merged), `invalid_code_format` (422) |
| `POST /auth/email/link` `{email}`, `POST /auth/email/link/confirm` `{token}` | A signed-in account without a confirmed address (for example a phone-only one) adds one. It is stored only when the single-use link sent to it is confirmed. Another account's address gets the same 202 reply, and that account's owner is told instead |
| `GET /dev/outbox` | Development only (404 otherwise): stored e-mails |
| `GET /dev/sms-outbox` | Development and tests only, with the scripted `test` SMS provider (404 in production and with any other provider): codes that were 'sent' |

Password sign-in is refused with `403 email_not_verified` until the address is confirmed.

### Assistant

| Method and path | Purpose |
|---|---|
| `GET /assistant/profile` | Public, read-only (migration 0013): the active version of Al Mulhim's identity and approved project knowledge: `version`, `sha256`, `activated_at`, `name`, `meaning`, `distinguished_from`, `linguistic_note` (`status: interpretation`), `reference`, `self_description`, `introduction`, `greeting_reply`, `purpose`, `domains`, `statistics_from`, `data_modes`, `users`, `capabilities`, `limitations`, `memory_policy`, and (version 3, migration 0017) `personas[]`: `code` (`mulhim`, `ilham`), `default`, `gender`, `name`, `meaning`, `linguistic_note`, `self_description`, `introduction`, `avatar` {`portrait`, `figure`, `alt`, `live_avatar_id`}, `voices` {`azure` {`ar`, `en`}, `realtime` {`ar`, `en`}}. No write method exists (405); new versions are published with `python -m app.cli assistant-profile publish FILE`. 503 `assistant_profile_missing` if none is active |
| `GET /assistant/persona`, `PUT /assistant/persona` `{persona}` | (0017) The signed-in person's saved persona (`{persona, stored: "account"}`; `null` = the default). Visitors get `{persona: null, stored: "browser"}` (their choice stays in the browser). `PUT` needs a signed-in session and CSRF; an unknown code → 422 `unknown_persona` |
| `GET /assistant/status` | Public: configured or not, `fallback` (`lookup` when no provider), limits (per minute, hour, day), `guest_answer_limit`, `research_cutoff`, suggested questions (EN/AR) |
| `GET/POST /assistant/conversations`, `GET/DELETE /assistant/conversations/{id}` | Own conversations only (others' return 404). Deleting removes all messages |
| `POST /assistant/conversations/{id}/messages` `{content, language, request_id?}` | Reply with `status` (answered, clarification, no_evidence, unverified, unavailable, lookup), `citations`, `evidence` (value, operator, unit, period kind, source URL and code, record reference, revision status, `evidence_class`), `calculations` (formula, inputs, result, computed by OSRIP) and `ai_generated`. Needs `assistant.use`; limited per user per minute, hour and day (429 `assistant_rate_limited`). The same `request_id` again returns the stored reply (`replayed: true`); reused for another question → 422 `request_id_reused`; still running → 409 `request_in_progress` |
| `GET /assistant/guest` | Public. Issues the anonymous cookie on first use and returns `{authenticated: false, allowance: {limit, used, in_progress, remaining, authentication_required, policy_version}, notice (EN/AR cookie limitation), conversations}`; signed in: `{authenticated: true, linkable_history}` |
| `POST /assistant/guest/messages` `{content, language, request_id, conversation_id?, data_mode}` | Guest question (header `X-Guest-CSRF`). Returns `{message, conversation_id, allowance}`. Five successful answers per guest session; then 403 `guest_allowance_exhausted` with `details.authentication_required` before any provider call. Failures, withheld replies and lookups are not charged; a repeated `request_id` is replayed without a charge. 401 `guest_session_required`, 403 `csrf_failed`, 429 `too_many_requests`, 409 `use_account_conversations` when signed in |
| `GET /assistant/guest/conversations/{id}` | The guest session's own conversation with its allowance (others' return 404) |
| `POST /assistant/guest/link` | Signed in (CSRF) and with the guest cookie: moves this browser's guest conversations to the account. 409 `guest_session_linked` if another account linked it |
| Both message endpoints: `web_research` (default `true`) | Lets the model use `web_search`/`read_web_page` when a search provider is configured (`GET /assistant/status` → `web_research`). Web evidence has `kind: web`, `evidence_class` `official` or `secondary`, `source_class` (`official`, `international`, `secondary`), `url`, `title`, `publisher`, `published` with `published_basis` (`page_metadata` or `search_engine`), `retrieved_at` and the exact `text` seen. Every search attempt is evidence of `kind: search` with `status` (`ok`, `no_results`, `failed`, `rate_limited`, `not_configured`). A reply that only reports a failed search is not charged to a guest |
| Both message endpoints: `cross_check` (0018, default `false`) | Research mode only: also search with the second configured route (`GET /assistant/status` → `cross_check_available`). Its results carry `role: cross_check` and the note that agreement between two AI routes is not independent evidence. Without it, the second route is used only as a fallback after the first fails (`role: fallback`) |
| Replies (0018): `data_status`, provider summaries, `structured.grounded_context` | Every evidence item has `data_status`: `approved_official`, `synthetic_demonstration`, `unreviewed_external`, `calculated`, `model_forecast`, `assumption_scenario` or `reference`. Web evidence from the OpenAI search route has `content_kind: provider_summary`, `summary_by` (the model) and `locator: provider_citation`; it is never queued for review. Search evidence has `provider`, `role` (`primary`, `fallback`, `cross_check`) and, for Grounding with Google Search, `display_only: true`. Those results are in `structured.grounded_context[]` {`provider`, `attribution`, `model`, `text`, `citations` [`url`, `title`, `segment`, `source_class`], `search_suggestions` (Google's HTML), `queries`, `retrieved_at`, `stored_at`, `role`}: shown verbatim apart from the answer, never evidence for it, removed after `OSRIP_GROUNDED_RETENTION_DAYS`. `structured.method` adds `answer_provider`, `answer_model`, `answer_fallback` {`from`, `to`, `reason`}, `route` {`numerical`, `recent`, `web_first`}, `search_routes` [`provider`, `role`, `status`, `display_only`], `provider_summaries` and `grounded_results`. `GET /assistant/status` adds `web_research_provider` and `cross_check_available` |
| Both message endpoints: `persona` (0017, optional) | Who replies (`mulhim` or `ilham`); default: the saved choice, then the profile's default. Only the name, introduction and Arabic grammatical gender of the reply change; tools, evidence checks, results and the guest allowance do not. Stored replies carry `persona`. Unknown → 422 `unknown_persona` |
| `GET /assistant/voice` | Public: whether server speech is configured, provider, voices and locales per language (the default persona's), `personas[]` (`code`, `default`, `gender`, `voices` {`ar`, `en`}), `max_seconds`, `stores_audio: false` |
| `POST /assistant/voice/transcribe?language=en\|ar` (body `audio/wav`, PCM 16 kHz mono, ≤ 60 s) | Signed in with `assistant.use`, or a guest (cookie and `X-Guest-CSRF`; refused with `guest_allowance_exhausted` once the allowance is used). Returns `{text, stored_audio: false}` for review; nothing is asked. 422 `speech_invalid_audio`/`speech_too_long`/`speech_no_speech`, 503 `speech_not_configured`, 502 `speech_unavailable`, 429 per client |
| `GET /assistant/voice/voices` | (0020) Public: each persona's configured voice per language with `verified` (true or false from the speech service's own voice list, cached for an hour; `null` when it cannot be checked or speech is not configured), `locale` and `gender`. English is read only by English voices |
| `POST /assistant/voice/test` `{persona?, language}` | (0020) A fixed sample sentence (with a number and a unit) in the persona's configured voice, for the person to hear before relying on it; never arbitrary text. Same callers, limits and errors as `voice/speak`; header `X-Voice` |
| `POST /assistant/voice/analysis` `{analysis_id, persona?, language}` | (0020) A concise spoken summary of a stored shortage and surplus analysis (its summary and each balance's status, not every table cell). Unknown analysis 404 |
| `POST /assistant/voice/speak` `{message_id, language, segment_id?}` | `audio/mpeg` of an assistant reply the caller owns (others' 404), spoken with the configured voice of the persona that gave the reply (header `X-Voice` names it); evidence markers are not read. With `segment_id` (0019, `N1`…): only that narration segment of the reply's completed live study, so playback can follow the explanation sentence by sentence; unknown segment 404 |
| Replies (0019): `structured.study_id` | The live study the reply was prepared as (the request id); the workspace reopens it |
| `GET /assistant/memory`, `DELETE /assistant/conversations` | Signed in: what is kept (conversation and message counts, saved research, retention policy `until_deleted`); delete every own conversation (saved research is kept separately). Returns `{deleted}` |
| `DELETE /assistant/guest/conversations/{id}` | A guest deletes one of this browser's conversations (header `X-Guest-CSRF`). The allowance already used is unchanged |
| `GET /assistant/requests/{request_id}/progress`, `GET /assistant/guest/requests/{request_id}/progress` | (migration 0016) The caller's own request only (others' 404): `state` (`reserved`, `completed`, `released`, `cancelled`), `cancel_requested` and `stages[]` (`stage` of `received`, `published_data`, `calculating`, `web_search`, `reading`, `checking`, `done`, `cancelled`; `at`; `label` EN/AR). A stage is recorded only when that step really happens |
| `GET /assistant/requests/{request_id}/events`, `GET /assistant/guest/requests/{request_id}/events` | (migration 0019) The caller's live study as server-sent events (`text/event-stream`; see [WORKSPACE.md](WORKSPACE.md)). Events: `study.started`, `stage`, `search`, `evidence`, `dataset` (validated table and charts), `warning`, `study.completed` (findings, narration segments with targets, final and provisional datasets, recommendations, assumptions, method), `study.cancelled`, `study.failed`. Each event has `id: seq` and JSON `{study_id, seq, type, result_version, at, payload}`. Replays from the start (or after `?after=` / `Last-Event-ID`), follows new events while the request runs, and ends with `event: end`. Another person's request is never found: the stream ends with `end` `{"reason":"unknown"}` |
| `GET /assistant/requests/{request_id}/study`, `GET /assistant/guest/requests/{request_id}/study` | Every event of the caller's study as JSON `{study_id, state, events}` (others' 404) |
| `POST /assistant/requests/{request_id}/cancel`, `POST /assistant/guest/requests/{request_id}/cancel` | 202. Stops a running question at its next step; the reply has `status: cancelled` and is never charged. A finished request is left unchanged |
| `GET /assistant/voice/realtime` | Public readiness of real-time voice: `configured`, `agent_sdk_installed`, `missing` (names of settings, and `profile: real-time voice for <persona> (<language>)` while a persona has none; never values), `avatar` `{configured, provider, reason, personas}`, `fallback: push_to_talk`, `note` (EN/AR) |
| `POST /assistant/voice/realtime/session` `{language, persona?}` | Signed in with `assistant.use`, or a guest with allowance left. A short-lived (10 min) LiveKit token for one new room: microphone publishing only, no room creation, admin, list or recording rights, the agent dispatched; signed metadata `{language, persona}`. The identity (`user:<id>` or `guest:<id>`) is set by the server. Returns `url`, `room`, `token`, `end_key`, `persona`, `expires_at`, `max_call_minutes`. 503 `voice_realtime_not_configured` with `details.missing` |
| `POST /assistant/voice/realtime/end` `{room, end_key}` | (0017) End call: deletes the caller's room on the LiveKit server, which disconnects the agent and any avatar worker (no paid session keeps running). Only the caller the room was issued to (checked with `end_key`); otherwise 404. 502 `voice_realtime_end_failed` |
| Message replies: `structured.method`, `structured.studies` | `method`: what was actually done (`steps`, `published_records`, `calculations`, `studies`, `searches`, `failed_searches`, `search_languages`, `web_results`, `pages_read`, `stale_sources`, `undated_sources`). `studies`: studies cited by the reply (`id`, `kind`, `title`, `status`), stored with the message and readable at `/studies/{id}`. Web evidence also has `freshness` (`current`, `stale` = published more than three years earlier, `undated`), `locator` (for example `p. 3` in a PDF) and `content_sha256` of the document as retrieved |

| Both message endpoints: `mode` (0.9; `ask` default, `analyze`, `research`, `compare`, `scenario`) | Chooses the prompt rules, the tool set (`scenario_projection` only in `scenario`; `growth_rate`, `share_of_total`, `compare_areas`, `data_quality_notes` everywhere) and the structured parts the model may return. `research` always requests web research. Replies and stored messages carry `mode` and `structured`: `recommendations` (Analyze and Research: `finding`, `evidence`, `action`, `expected_benefit`, `prerequisites`, `uncertainty`, `citations`), `drivers` (`driver` of ten, `basis` `evidence`/`hypothesis`/`assumption`, `relation`, `citations`), `evidence_points`, `hypotheses`, `assumptions` (`statement`, `citations`), `conflicts` (`topic`, `values` [`evidence_id`, `value_text`], `note`) and `withheld` (count of dropped parts per kind). Every part has passed the evidence check; unsupported parts are never returned. Web evidence may also have `source_class` `research` (`evidence_class` `research`) and `content_kind` `pdf_excerpt`; search evidence lists `queries` [`query`, `language`] and `languages` |

The model can only call read-only tools that run in a READ ONLY database
transaction. Every number in a reply must match cited evidence (for web evidence: the
retrieved text) and, from 0.9, be followed by an inline `[E#]` marker in the same sentence or
paragraph; otherwise the reply is withheld (`unverified`) and the evidence is shown instead.

### Research library (0.9)

| Method and path | Purpose |
|---|---|
| `GET /library/sources?q=&source_class=official\|international\|research\|secondary\|reference_pack\|dataset\|web&domain=` | Public. `sources[]` of `kind` `reference_pack` (code, publisher, publication, role, URL, accessed date, research cutoff), `dataset` (verified sources with published data and their `published_records`) and `web_found` (URL, title, publisher, class, publication date, retrieved date, `figures_found`, `figures_accepted`; `figures_pending` only for `research.review`). Without `research.review` only sources with accepted figures are listed. `note` (EN/AR) |
| `GET/POST /library/saved` `{message_id, title?, note?}` | Signed in. Saves one of the caller's own completed assistant replies with a snapshot (text, mode, evidence, calculations, citations, structured parts, research cutoff). Saving the same reply again returns the existing item. At most 500 items. Another user's reply → 404 |
| `GET/PATCH/DELETE /library/saved/{id}` `{title?, note?}` | The caller's own item only (others' → 404). `GET` includes `snapshot` |
| `GET /library/saved/{id}/brief?format=html\|md` | Downloadable research brief (attachment, `no-store`, `Content-Security-Policy: default-src 'none'`); built from the snapshot only |
| `GET/POST /watchlist` `{indicator, area, period_kind, data_mode}` | Signed in. Watched series with the latest published value, the change between the two latest values (OSRIP calculation) and the rules. At most 50 items (same series twice returns the existing item) |
| `DELETE /watchlist/{id}` | Stops watching (deletes its rules) |
| `POST /watchlist/{id}/rules` `{kind: new_data\|above\|below, threshold?, channel: in_app\|email}` | A threshold is required for `above`/`below`, in the indicator's display unit. `email` → 503 `email_not_configured` without e-mail delivery, 422 `verified_email_required` without a confirmed address |
| `PATCH/DELETE /alerts/rules/{id}` `{enabled?, channel?, threshold?}` | The caller's own rules only |
| `GET /alerts?unread_only=` | `{unread, events[]}`: kind, indicator, area, value and unit, period, threshold, `message` (EN/AR), `delivery` (`in_app`, `email_pending`, `email_sent`, `email_failed`, `email_unavailable`), `read_at`. Events are created inside the publication transaction for new or revised values only |
| `POST /alerts/read` `{event_id?}` | Marks one or all events read; returns `{marked}` |
| `GET /areas/compare?indicator=&data_mode=&period_kind=annual&period_start=&level=governorate\|wilayat&flow=` | Public. `status` `ok`, `not_comparable` (`reason` `different_units` or `different_period_lengths`), `no_data` or `choose_flow` (`flows`). `rows[]` per area with `status` `published`, `missing_in_source` or `no_published_value`; `areas_without_value`; `national` and `reporting_groups` (never divided); `available_periods`. Without `period_start`: the latest period that at least two areas report. Wilayat level lists only wilayats with their own value. Unknown indicator → 422 |

### Studies (migration 0015)

| Method and path | Purpose |
|---|---|
| `GET /studies/catalog` | Public. The ten allowlisted kinds (`trend`, `growth`, `compare_regions`, `seasonal_profile`, `import_dependence`, `partner_concentration`, `data_quality`, `scenario`, `forecast_eligibility`, `programme_assessment`) with EN/AR titles and the JSON Schema of their parameters |
| `POST /studies` `{kind, data_mode, params}` | Public (a signed-in caller must send the CSRF token). Runs the study on the server from published observations and stores it: `{id, created_at, sha256, study}`. `study` follows `osrip.study/1`: `status` (`ok`, `not_available`, `not_comparable`) with `reason`, `findings` (EN/AR, citing `S#` evidence), `cards`, `table` (`columns` with units for every number; `rows` with decimal strings or `null`, never zero for missing), `charts` (`line`, `bar` or `heatmap`, each series `observed`, `calculated`, `forecast` or `scenario`), `evidence` (source, dataset version, record), `method`, `assumptions`, `limitations`, `next_questions`. Unknown codes or parameters outside the allowlist → 422 `unknown_indicator`, `unknown_area`, `invalid_study_parameters`. 240 runs per hour per client |
| `POST /studies/preview` `{kind, data_mode, params}` | (0019) The same validated study, computed but not stored: `{study}`. Used by the workspace for the current selection. 600 per hour per client |
| `GET /studies` | Signed in: the caller's own runs (latest 100) |
| `GET /studies/{id}` | The stored study (anyone with its identifier; studies contain published data and the stated parameters only) |
| `GET /studies/{id}/reproduce` | Rebuilds from the stored parameters: `{identical, stored_versions, current_versions}` |
| `GET /studies/{id}/export.csv?language=en\|ar`, `GET /studies/{id}/export.json` | The table exactly as shown, with provenance comment lines (CSV has a BOM for spreadsheet programs; since 0020 its text cells are neutralised against spreadsheet formula injection) / the full stored result |
| `DELETE /studies/{id}` | Signed in: the caller's own run only (others' 404) |

The assistant's `run_study` tool runs the same builders in its read-only transaction; a
study cited by a reply is stored with that message.

### Shortage and surplus analysis (migration 0020)

| Method and path | Purpose |
|---|---|
| `POST /analysis/balance` `{data_mode, params}` | Public. `params`: `sector` (`electricity`, `water`, `food_security`, `trade`), `area` (default `OM`), `period_kind` (`annual` or `year_to_date`) and an optional scenario given in full (`supply_growth_pct`, `demand_growth_pct` between −50 and 50, `years` 1–10). Runs and stores the analysis: `{id, created_at, sha256, analysis}`. `analysis` follows `osrip.balance/1`: `status` (`ok`, `partial`, `not_available`), `summary` (EN/AR), `balances[]` (each `surplus`, `shortfall`, `balanced` or `not_determinable` with its `reason`, `interpretation`, `gap` and unit, own `table` and `charts`, evidence `S#`, `constraints`), `recommendations[]` (problem, evidence, action, quantity and unit or why not quantified, horizon, constraints, `cost` always unknown with `cost_known: false`, outcome and assumptions, priority with its basis, monitoring KPI, nature), `prioritization`, `data_gaps[]`, `scenario` (labelled assumptions, never a forecast), `forecast` (whether the forecasting method accepts the demand series), `sources[]` (publisher, title, URL, publication, retrieval date, period, value, dataset version, record, `older_context` before 2022). 422 `invalid_analysis_parameters`. 240 per hour per client |
| `POST /analysis/balance/preview` `{data_mode, params}` | The same analysis, not stored: `{analysis}`. 600 per hour per client |
| `GET /analysis/balance/{id}` | The stored analysis (a study's identifier here, or an analysis's at `/studies/{id}`, is 404) |
| `GET /analysis/balance/{id}/reproduce` | `{identical, stored_versions, current_versions}` |
| `GET /analysis/balance/{id}/export.csv?language=en\|ar` | Every balance table, the recommendation table, the missing information, the scenario and the sources (BOM; text cells neutralised against spreadsheet formula injection; missing values empty) |
| `GET /analysis/balance/{id}/report.html?language=en\|ar` | A readable, printable report (`lang`/`dir` per language, values escaped, no script; served with `Content-Security-Policy: default-src 'none'`) |

The assistant's `balance_analysis` tool builds the same document; each balance appears in the
live study as a validated dataset, and every figure the reply takes from it is checked
against it.

### Accounts (additions in 0.8)

| Method and path | Purpose |
|---|---|
| `POST /auth/login` `{email, password}` | `email` is the sign-in identifier: an e-mail address or a username (case-insensitive) |
| `GET /auth/me` | Adds `username` and `password_change_required` |
| `POST /auth/password/change` `{current_password, new_password}` | Signed in (CSRF). New password 12+ characters and different; revokes the account's other sessions; clears a required change. While a change is required every other authenticated endpoint returns 403 `password_change_required` (sign-out still works) |

### Web research review (`research.review`, data managers)

| Method and path | Purpose |
|---|---|
| `GET /research/candidates?status=pending\|accepted\|rejected\|duplicate` | Figures found on the web with full provenance; pending ones include `checks` (official source, 2022+ scope, publication date, comparable period, unit, duplicates and possible revisions against published observations) |
| `POST /research/candidates/{id}/review` `{decision: accepted\|rejected\|duplicate, note}` | A note is required to accept. 409 `already_reviewed`. Never publishes anything |
| `GET /research/candidates/accepted.csv` | Accepted figures as CSV, to prepare a normal import |

### Protected actions

| Method and path | Permission |
|---|---|
| `GET /sources?data_mode=` | Public: sources with a published or superseded version. Users with `import.read` also see drafts |
| `POST /sources` | `source.register` |
| `POST /imports` (multipart: `source_id`, `version_label`, `file` ≤ 5 MB CSV) | `import.create` |
| `GET /imports`, `GET /imports/{id}`, `GET /imports/{id}/rows`, `GET /imports/{id}/errors.csv` | `import.read` |
| `PUT /imports/{id}/mapping`, `POST /imports/{id}/validate` | `import.validate` (owner, or `import.manage_any`) |
| `POST /imports/{id}/approve` `{acknowledged_rejected_rows, note}` | `import.approve` (explicit grant) |
| `POST /imports/{id}/publish` | `import.publish` (explicit grant); one transaction, idempotent |
| `POST /imports/{id}/reject` | `import.reject` |
| `POST /analysis-runs` `{data_mode, growth_threshold_pct?, share_threshold_pct?, unit_value_gap_pct?}` | `analysis.run` |
| `GET /recommendations/{id}/reviews` | `recommendation.review` or `analysis.run` |
| `POST /recommendations/{id}/reviews` `{status, reason}` | `recommendation.review` |
| `POST /forecast-runs` `{data_mode, series_id}` | `analysis.run`; an ineligible series is recorded as withheld |
| `POST /reports` `{title, data_mode, section, filters, stock_assumption, visibility}` | `report.create` |
| `PUT /reports/{id}/visibility` `{visibility}` | `report.create` and owner |
| `GET/POST /admin/users`, `POST /admin/users/{id}/roles`, `DELETE …/roles/{role}`, `POST …/grants`, `DELETE …/grants/{permission}`, `POST …/suspend`, `POST …/reactivate` | `user.manage` |
| `GET /admin/audit-events` | `audit.read` |
| `GET /admin/monitoring` | `audit.read`: readiness, release, connected-service status and recent grouped errors |
| `GET /admin/providers` | `audit.read` (migration 0018). AI and search provider readiness ([AI_PROVIDERS.md](AI_PROVIDERS.md)). Returns `providers[]` for `anthropic`, `openai`, `gemini`, `brave`, each with: `label`, `docs`, `roles` (`answer_primary`, `answer_fallback`, `search_primary`, `search_fallback`), `capabilities` {`answer`/`search`: `missing` (setting names, never values), `model`, `chosen`}, `status` (`unavailable`, `configured`, `tested`, `failed`), `last_test`, `last_call`, `today` {`calls`, `errors`, `estimated_cost_usd` (null without configured prices)}, `limits`. Also `routing` {`answer`, `search`: {`primary`, `fallback`}} and `policy` (EN/AR) |
| `POST /admin/providers/{anthropic\|openai\|gemini\|brave}/test?capability=answer\|search` | `audit.read` **and** `user.manage` (an administrator: the call may cost a little), 20 an hour per administrator. One minimal live call, recorded as a test call. Returns `status` (`ok`, `not_configured` with `missing`, `unsupported`, or the failure code such as `timeout`, `http_401`, `daily_limit`), `duration_ms` and the updated `readiness` |

Unhandled server errors return `500 internal_error` with a `request_id`. The same ID
is stored with the (scrubbed) error record.

## Example

```bash
curl "http://localhost:8010/api/v1/observations?data_mode=synthetic&section=electricity&indicator=ELEC_GENERATION"
```

Returns the booklet fixture (48,000 and 50,100 GWh) with its synthetic label, source
and dataset version `fixtures-v1`.
