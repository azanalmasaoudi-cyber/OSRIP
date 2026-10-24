# Connected services

Everything here is optional. Anything that is not configured is shown in the
interface as "not configured" (sign-in providers, e-mail, assistant). No fake
button is shown and no secret is sent to the browser. Put the values in
`backend/.env` (development) or `deploy/.env` (deployment). Never commit them.

## Evaluation (API 0.6.0, 2026-09-26)

Each service was added only where it serves a stated purpose. Status words:
**implemented** = code exists; **tested** = automated tests pass (against a scripted or
mocked counterpart unless "live" is stated); **configured** = real credentials in use;
**pending** = not built.

| Service | Purpose | Data quality / compatibility | Cost | Privacy | Limits and failure behaviour | Maintenance | Status |
|---|---|---|---|---|---|---|---|
| NCSI publications list and Monthly Statistical Bulletin workbook (ncsi.gov.om) | Monthly electricity (gross and net production) and water production, by region | Authoritative. The public list of releases carries the release data as JSON; the bulletin has an official .xlsx. Verified 2026-10-23 (HTTPS 200) | Free (Open Government License – Sultanate of Oman) | Public aggregates only | Sync worker (`python -m app.worker`), off until an administrator switches it on; daily by default; new and changed figures staged as an import for approval; failures never change published data | Tables 21 and 22 only; a layout change stops the sync with a logged reason | **Implemented and tested; live check run 2026-10-23** (October 2026 bulletin: 104 new and 6 revised figures staged, not published). See [OFFICIAL_SOURCES.md](OFFICIAL_SOURCES.md) |
| NCSI data portal (data.gov.om) | Official electricity, water and trade statistics | Authoritative. CSV only; the documented API (`POST /api/1.1/data/details`) returned HTTP 403 to every anonymous request, including the documentation's own example (re-checked 2026-10-23), and downloads need a signed-in portal account, so **no API is assumed**. The reviewed converter keeps January 2022 onward and full years only | Free (Open Government License – Sultanate of Oman) | Public aggregates only | Manual download → approved file import → validate → approve → publish. Nothing is fetched at run time, so the site never depends on the portal being up | Re-download and re-import when NCSI publishes; the mapping file needs a review whenever NCSI renames a series | Implemented and tested (converter, import). **Not configured**: no official file loaded yet |
| OpenFreeMap (MapLibre style and tiles) | Basemap on Geography | OpenStreetMap-derived. No administrative boundaries are used or claimed | Free, no key; terms at openfreemap.org/tos | The browser requests tiles directly and sends its IP address to OpenFreeMap. No OSRIP data is sent | Loaded lazily. If the style fails, the page shows "map unavailable" and the area table still works. `VITE_MAP_STYLE_URL=none` switches it off | Style URL only; the CSP must list the tile host | Implemented and tested (the failure path only; e2e makes no external calls) |
| Directions links to facilities | Open a directions app at a verified facility location | **No verified facility coordinates exist** in the project | — | — | — | — | **Pending, deliberately not built**: a link to an invented location would be misleading. Build it only after coordinates are sourced and reviewed |
| Anthropic Messages API (Claude) | Assistant that explains published figures and stored forecasts | Answers are restricted to tool results; unmatched numbers are withheld. **It never produces forecasts** | Pay per token; per-user limits of 5 per minute and 30 per hour cap the spend | Questions and the retrieved published statistics are sent to Anthropic. No uploads or account data are sent. The key stays on the server | 30 s timeout; **one retry** after 1 s on 429, 5xx and network errors; then an explained "temporarily unavailable" message. Failures appear on Service health | Model name in `OSRIP_ASSISTANT_MODEL`; review when models are retired | Implemented and tested (mocked HTTP, including retry). **Not configured**: no key |
| SMTP relay | Confirmation, recovery and sign-in-link e-mails | — | Depends on the relay; the institution's relay is usually free | Recipient address and one link per message | Sent only when a user asks. A failure is logged, reported on Service health and shown to the user as "could not send". It is not retried automatically, because repeated sends would repeat the token | Credentials and sender address | Implemented and tested (outbox; SMTP code path unit-tested). **Not configured** |
| SMS verification (phone registration and sign-in) | Register and sign in with a mobile number, with no e-mail needed; add a verified number to an account | The provider generates, sends and checks the code; OSRIP never stores it. OSRIP also enforces expiry, attempt limits, single use and cooldowns itself | Per message; the limits (per number, per client, per hour in total) bound the cost | Each phone number goes to the provider. Numbers are stored only after verification and appear only masked in the interface, audit log and acceptance records | Provider errors become explained messages with an e-mail alternative. The provider call has a 10 s timeout and is **not retried** (a retry could send two codes). Failures appear on Service health | Provider credentials; the number-plan rule for Oman | **Application side implemented and tested** with a scripted test provider (36 backend and 18 browser tests). **No production provider selected, so no real adapter and no live delivery.** Disabled by default and shown as unavailable |
| Google / Microsoft OpenID Connect | Optional sign-in | Accounts are **not** merged on a matching e-mail | Free | Name, e-mail, subject ID | Discovery and keys are cached. **One retry** on metadata fetch. The token exchange is not retried (single-use code). Failures redirect with an explained error and appear on Service health | Register redirect URIs; rotate client secrets | Implemented and tested (scripted provider with real RSA keys). **Not configured** |
| Error monitoring (built-in) | Record server and browser errors to fix defects | E-mails, 24+ character tokens and query strings are removed before storage. Errors are grouped by fingerprint | Free (own database) | No cookies are sent with browser reports. At most 10 reports per page session, and 30 per hour per client on the server | Recording never breaks a request. Every 500 response carries a `request_id` | Review `/admin/health`; prune `app_error` rows as needed | Implemented and tested |
| Health checks | Container orchestration and uptime checks | `/health` (process), `/health/db`, `/health/ready` (database + migration at head) | — | No data returned | Used by the compose `api` healthcheck; `web` waits for it | — | Implemented and tested; the compose file has **not been run** |

A hosted monitoring service (for example Sentry) was **not** added. The built-in
recorder covers the prototype's needs without sending error data to another company.
Add one only if the hosting team requires alerting. Note that external uptime
checks need a public address, which does not exist yet.

## Public address

| Setting | Value |
|---|---|
| `OSRIP_PUBLIC_BASE_URL` | The address people type in the browser, e.g. `https://osrip.example.org` (development: `http://localhost:5173`). E-mail links and provider redirect URIs are built from it. Must be `https://` in production (the API refuses to start otherwise) |

## E-mail (registration, confirmation, password recovery, magic links)

| Setting | Notes |
|---|---|
| `OSRIP_EMAIL_BACKEND` | `outbox` (development only: stored in the database and shown at `/dev/mail`, never sent; refused in production), `smtp`, or `disabled` (registration, magic links and recovery are then switched off and labelled) |
| `OSRIP_SMTP_HOST`, `OSRIP_SMTP_PORT` (587), `OSRIP_SMTP_USERNAME`, `OSRIP_SMTP_PASSWORD`, `OSRIP_SMTP_FROM`, `OSRIP_SMTP_STARTTLS` (true) | Any SMTP relay the institution provides. Messages are sent only when a user asks (register, resend, forgot password, magic link). The SMTP path has not been tested against a real server (see TEST_RESULTS) |
| `OSRIP_VERIFY_EMAIL_HOURS` (24), `OSRIP_RESET_PASSWORD_MINUTES` (30), `OSRIP_MAGIC_LINK_MINUTES` (15), `OSRIP_EMAIL_REQUESTS_PER_HOUR` (5 per account and purpose) | Token lifetimes and limits. Tokens are single-use. Only their SHA-256 digests are stored |

## Google sign-in

1. In the Google Cloud console, create an **OAuth client ID** of type *Web application*.
2. Authorised redirect URI: `{OSRIP_PUBLIC_BASE_URL}/api/v1/auth/oidc/google/callback`
   (development: `http://localhost:5173/api/v1/auth/oidc/google/callback`).
3. Scopes: `openid`, `email`, `profile`.
4. Set `OSRIP_GOOGLE_CLIENT_ID` and `OSRIP_GOOGLE_CLIENT_SECRET`.

## Microsoft sign-in (Entra ID)

1. In Microsoft Entra ID, go to **App registrations** and choose **New registration**.
2. Platform **Web**, with redirect URI `{OSRIP_PUBLIC_BASE_URL}/api/v1/auth/oidc/microsoft/callback`.
3. Create a client secret.
4. Optionally add the `xms_edov` optional claim, so domain-verified e-mail addresses are recognised.
5. Set `OSRIP_MICROSOFT_CLIENT_ID`, `OSRIP_MICROSOFT_CLIENT_SECRET` and `OSRIP_MICROSOFT_TENANT`:
   - `common` for any account;
   - `organizations` for work and school accounts;
   - your tenant ID for one organisation only.

What the server checks on every callback:

- the single-use `state`, bound to the browser by an HttpOnly cookie;
- PKCE (S256);
- the ID token: RS256 signature against the provider's published keys, issuer (for Microsoft, per tenant), audience, expiry and nonce.

A **new** account is created only when the provider confirms the e-mail address, and it gets the Viewer role. If an existing OSRIP account uses the same address, the accounts are **not** merged: the person signs in to that account first, then links the provider from **Account**.

Status: tested against a scripted OpenID provider with real RSA keys (14 tests). Not tested against the live Google or Microsoft services, because no client IDs exist yet.

## Assistant (Claude)

| Setting | Notes |
|---|---|
| `OSRIP_ASSISTANT_PROVIDER` | `anthropic`, `openai`, `gemini` or `disabled` (OpenAI and Gemini: see [AI_PROVIDERS.md](AI_PROVIDERS.md)). `fake` is the scripted test double used by the automated tests, and it is refused in production |
| `OSRIP_ANTHROPIC_API_KEY` | Anthropic API key. It stays on the server and is never sent to browsers. Without it, the assistant is shown as "not configured" |
| `OSRIP_ASSISTANT_MODEL` (`claude-sonnet-5-5`), `OSRIP_ASSISTANT_TIMEOUT_SECONDS` (30), `OSRIP_ASSISTANT_MAX_PER_MINUTE` (5), `OSRIP_ASSISTANT_MAX_PER_HOUR` (30), `OSRIP_ASSISTANT_MAX_MESSAGE_CHARS` (1000) | Model, timeout, per-user limits and message length |

Using the key sends users' questions, together with the retrieved published statistics, to Anthropic's API. Decide this with the project team, and tell users.

Status: tested with a scripted model and with the real HTTP client against a mocked API (request format, tool loop, failures, timeouts). **Not tested against the live Anthropic API**, because no key was available.

Without a provider the assistant does not pretend to answer: replies are a labelled **non-AI record lookup** (status `lookup`, "Not AI-generated") listing the latest published national records for the topics named in the question. Lookups never use the guest allowance.

Every evidence item carries `evidence_class`: `observed` (a published value), `calculated` (OSRIP arithmetic on published values), `forecast` (a validated model estimate), `hypothetical` (a user-stated scenario assumption) or `reference` (definitions and formulas). The system prompt states the research cutoff of the loaded reference pack (2026-09-27) and forbids describing the data as live. Only published dataset versions are reachable by the tools; private imports never are.

### Guest allowance (five answers) and fair use

| Setting | Default | Notes |
|---|---|---|
| `OSRIP_GUEST_ANSWER_LIMIT` | 5 | Successful AI answers per guest session, across Arabic and English |
| `OSRIP_GUEST_SESSION_DAYS` | 90 | Lifetime of the anonymous cookie and record after the last visit |
| `OSRIP_GUEST_POLICY_VERSION` | 1 | Recorded with each guest session |
| `OSRIP_GUEST_ASKS_PER_MINUTE` | 10 | Abuse limit per guest session |
| `OSRIP_GUEST_ASKS_PER_CLIENT_HOUR` | 60 | Abuse limit per client address (keyed hash, no raw IP stored) |
| `OSRIP_GUEST_SESSIONS_PER_CLIENT_HOUR` | 30 | New guest sessions per client address |
| `OSRIP_ASSISTANT_MAX_PER_DAY` | 100 | Signed-in fair use per account, besides the per-minute and per-hour limits |

How it is enforced (migration `0010_guest_allowance`): the anonymous identity is a random value in an HttpOnly, SameSite=Strict cookie (`osrip_guest`), stored only as a SHA-256 digest; state-changing guest requests also echo a guest CSRF token (`osrip_guest_csrf` → `X-Guest-CSRF`). Each question carries a client request id. With the guest row locked, the server releases abandoned reservations, replays a completed request id without charging, and otherwise reserves one slot; the table constraint `answers_used + answers_reserved <= answer_limit` makes over-reservation impossible even under concurrency. The provider runs outside the transaction; the reply and the charge are committed together. A completed reply with status `answered`, `clarification` or `no_evidence` is charged; failures, withheld (`unverified`) replies, timeouts and lookups are not. A sixth question is refused with `403 guest_allowance_exhausted` and `details.authentication_required = true` before any provider request.

Limits stated to users: clearing cookies, a private window or another device cannot be recognised as the same visitor. No fingerprinting is used. After sign-in, guest conversations move to the account only through `POST /assistant/guest/link`, which needs the signed-in session (with CSRF) and the guest cookie in the same request; nothing is merged by e-mail address or phone number.

### Web research (assistant tools `web_search` and `read_web_page`)

**Provider chosen: Brave Search API** (independent web index; `GET https://api.search.brave.com/res/v1/web/search` with the `X-Subscription-Token` header; parameters `q`, `count`, `search_lang` (`ar` or `en`), `extra_snippets`, `safesearch`; results carry `page_age` when the engine knows a page date). Checked against Brave's official documentation on 2026-10-02. The adapter is `backend/app/services/research/search.py`; another provider needs only a class with the same `search()` method.

| Setting | Default | Notes |
|---|---|---|
| `OSRIP_RESEARCH_PROVIDER` | `brave` | `brave`, `openai`, `gemini` (see [AI_PROVIDERS.md](AI_PROVIDERS.md)) or `disabled`; `fake`, `fake-openai` and `fake-gemini` are scripted test routes, refused in production |
| `OSRIP_RESEARCH_FALLBACK_PROVIDER` | – | A second route, used only when the first fails or for a cross-check the person asks for |
| `OSRIP_RESEARCH_API_KEY` | – | Brave Search API subscription token, server side only. Without it the assistant says web search is unavailable |
| `OSRIP_RESEARCH_TIMEOUT_SECONDS` | 10 | Search and page retrieval timeout |
| `OSRIP_RESEARCH_MAX_SEARCHES_PER_ANSWER` / `..._PAGES_PER_ANSWER` | 3 / 3 | Budget per answer |
| `OSRIP_RESEARCH_PER_CLIENT_HOUR` | 60 | Searches per client address per hour |

How it works and what is guaranteed:

* Web search needs a configured model as well (the model writes the explanation). The reader can switch it off per question ("Search the web" in the panel).
* **Authoritative sources first.** Results are ranked by the host name alone (`backend/app/services/research/sources.py`): `official` = Omani government domains (`*.gov.om`: NCSI, ministries, Oman Customs) and the official electricity and water bodies (APSR `apsr.om`, Nama PWP `omanpwp.om`, OETC `omangrid.com`, Nama companies `*.nama.om`); `international` = FAO, World Bank, UN, IMF, WTO, IEA, IRENA, GCC-Stat, OECD; everything else is `secondary` (reported, not official data), whatever the page claims. If a search returns no official result, one more search restricted to `site:gov.om` is made.
* **Evidence, not memory.** Every result and page excerpt becomes evidence (`kind: web`) with URL, title, publisher, source class, the date the page states (`published_basis: page_metadata`) or the date the search engine gives (`search_engine`, labelled as only an indication), the retrieval time and the exact text the model saw. Every search attempt is recorded too (`kind: search`, status `ok`, `no_results`, `failed`, `rate_limited` or `not_configured`) and always shown under the reply, so a failed or missing search can never be presented as a successful one.
* **Numbers are checked.** The existing evidence check also covers the web: every number in the reply must appear in the text of a cited web result (or other cited evidence); otherwise the reply is withheld.
* **Untrusted content.** Page text is passed to the model labelled as untrusted, with instructions to ignore any instruction in it; the model's tools are read-only, so a page cannot trigger a privileged action, and `read_web_page` accepts only the evidence id of a search result, never a URL chosen by page text. Secrets are never in the model context.
* **Network protection** (`safe_fetch.py`): `http`/`https` on the default ports only, no credentials in URLs; the host is resolved and every address must be public (loopback, private, link-local including 169.254.169.254, CGNAT, multicast, reserved and IPv4-mapped IPv6 are refused); the connection is pinned to the checked address (TLS still verifies the real host name), so DNS rebinding cannot redirect it; redirects are followed manually (at most 3, each re-checked, never https→http); 2 MB, HTML/plain-text only.
* **Review queue, not the dataset.** Numerical observations the model reports from cited web evidence (`web_records`) are stored in `research_candidate` with indicator, value (as written and parsed), unit, geography, observation period, publication date, publisher, source URL, retrieval date, excerpt and provider; only values that appear verbatim in the cited text and periods ending in 2022 or later are kept; repeats are de-duplicated. Data managers (`research.review`) see them under **Data Management → Statistics found by web research** with duplicate, revision, unit, comparable-period, scope and source checks against published observations, and can accept (a note is required), reject or mark as duplicate. Accepting never publishes: accepted rows can be downloaded as CSV and must go through the normal upload, validation, approval and publication workflow.
* A reply that only reports that the web search failed is not charged to the guest allowance.

Status: implemented and tested with a scripted search provider and mocked HTTP (unit and integration tests, including SSRF cases). **Not tested against the live Brave API: no key was available.**

### Research and decision support (API 0.9, migration `0012_research_library`)

The same assistant (and the same speaking avatar) answers in five modes, chosen in the panel and sent as `mode` with each question:

| Mode | What changes |
|---|---|
| Ask | Direct answer from published data (as before) |
| Analyze | Growth rates (`growth_rate`, compound annual), shares (`share_of_total`, only for a component and its own parent total) and changes are calculated by OSRIP, never by the model; **recommendation cards** |
| Research | Web research is always requested; the model searches in both languages (`query` + `query_other_language`) and reads pages, tables and (optionally) PDFs; recommendation cards |
| Compare | `compare_areas`: each governorate's own published value for one indicator, unit and period. Missing values stay "missing in the source"; areas without data are "no published value"; national totals and combined reporting groups are shown apart and never divided; wilayat values are never inferred from governorates |
| Scenario | `scenario_projection` is available only here; scenarios stay separate from validated forecasts (`get_forecast`) |

What the server checks before anything is shown (`backend/app/services/assistant/grounding.py`):

* **Inline citations.** Every statistical number must be followed by an `[E#]` marker in the same sentence or paragraph, and must match the evidence that marker cites. Otherwise the reply is withheld. Standalone years only need to appear somewhere in the evidence.
* **Recommendation cards** (Finding, Evidence, Suggested action, Expected benefit, Prerequisites, Uncertainty, Sources) are kept only when every field is filled, at least one existing source is cited, and **every number in every field appears in the card's cited evidence**. So a card cannot claim an invented saving, cost or percentage improvement. Dropped cards are counted and shown as "withheld".
* **Drivers** (weather, population, industrial activity, desalination, renewable energy, irrigation, agricultural productivity, commodity prices, logistics, trading partners) each carry a basis: `evidence` (needs citations), `hypothesis` or `assumption` (labelled as such; an assumption may contain only numbers the user stated). Evidence points, hypotheses and assumptions are separate lists.
* **Conflicting sources** are listed with each value and the source it is written in; a value that is not in its source is dropped. Documented conflicts between official publications come from the reference pack (`data_quality_notes`).
* **Source classes** (by host name only): `official` (Omani government and sector bodies), `international` (FAO, World Bank, UN, IMF, WTO, IEA, IRENA, GCC-Stat, OECD), `research` (journal publishers and repositories, e.g. doi.org, ScienceDirect, Springer, MDPI, Taylor & Francis, Wiley, IWA, arXiv, SSRN, Sultan Qaboos University, UTAS: context and methods, not official statistics) and `secondary`. Results are ranked in that order.
* **Publication date vs period covered**: the date a page or PDF states (`page_metadata` / `document_metadata`) or the search engine's date (labelled as an indication) is kept apart from the period the figures refer to. Only figures for periods ending in 2022 or later go to the review queue.
* **Pages and tables**: HTML tables are kept as `Table: caption` and `cell | cell` rows, not flattened into snippets.

Library features (all behind the signed-in session; nothing is computed in the browser):

* **Source library** `GET /library/sources`: the reference-pack sources, registered verified datasets with their published record counts, and sources found by web research with how many figures were accepted. Pending (unreviewed) web sources are shown only to people with `research.review`.
* **Saved research** `/library/saved`: a snapshot of the reply (text, mode, evidence, calculations, citations, validated cards and drivers), so the saved item never changes afterwards. **Research briefs** `GET /library/saved/{id}/brief?format=html|md`: question, answer, recommendations, drivers, evidence/hypotheses/assumptions, conflicts, a source table (type, value, period covered, publisher, publication date, accessed date, record, link) and the limitations. The HTML brief is escaped and served with `Content-Security-Policy: default-src 'none'`, so no script can run in it.
* **Watchlist and alerts** `/watchlist`, `/alerts`: watch an indicator for one area, period kind and data mode; rules `new_data` (new or revised value), `above` / `below` a threshold in the indicator's display unit; each rule can be switched off, changed or deleted. Rules are evaluated **inside the publication transaction**, so an alert exists only if the publication commits. A republished unchanged value is not reported again, and a changed value is reported as "revised". E-mail alerts are sent after the commit; a failed or unavailable e-mail is recorded on the alert and never undoes the publication.

**Setup steps** (in `backend/.env` for development, `deploy/.env` for deployment; restart the API afterwards):

1. Apply the migration: `cd backend` then `.venv\Scripts\alembic upgrade head` (additive; no data is removed).
2. AI answers: `OSRIP_ASSISTANT_PROVIDER=anthropic` (the default) and `OSRIP_ANTHROPIC_API_KEY=<key from console.anthropic.com>`. Model `claude-sonnet-5-5` by default, up to 4,096 output tokens per model call so replies with recommendation cards are not cut off. Without a key the panel says so and gives labelled record lookups. Automated tests never read `backend/.env` or `OSRIP_*` shell values, so a real key cannot be used by a test run.
3. Web research (Research mode): `OSRIP_RESEARCH_PROVIDER=brave` and `OSRIP_RESEARCH_API_KEY=<Brave Search API subscription token from api-dashboard.search.brave.com>`. Without them Research mode shows "Research mode needs web search, which is not configured on this server" and every reply records the search as `not_configured`.
4. Optional PDF reading: `cd backend` then `.venv\Scripts\pip install -e ".[pdf]"` (installs `pypdf` 6.19+, pure Python). Without it a PDF is reported as `pdf_unsupported` and only its snippet is used. Text-based PDFs only: scanned pages (images) yield no text, because there is no OCR. **Installed on the development machine (pypdf 6.19.0, 2026-10-05)**; a deployment must install it too.
5. E-mail alerts: the existing e-mail settings (`OSRIP_EMAIL_BACKEND=smtp` and the `OSRIP_SMTP_*` values). The user needs a confirmed e-mail address. Without delivery, choosing "By e-mail" is refused with `email_not_configured` and in-app alerts still work.

Status: implemented and tested with the scripted model and search providers (backend: 18 unit and 11 integration tests; browser: `e2e-api/research.spec.ts`). PDF reading is tested with pypdf installed on a generated PDF: text, title and creation date, then the full `read_web_page` path to a grounded citation. **Not tested against the live Anthropic or Brave APIs, or on real published PDF bulletins.**

### Governed AI and research providers (migration `0018_provider_calls`)

OpenAI (Responses API) and Google Gemini (Interactions API) are now available as answering providers and as search routes, alongside Anthropic and Brave. All of them go through official APIs only; no consumer chat website is automated, and a consumer subscription is not API access. The full policy is in [AI_PROVIDERS.md](AI_PROVIDERS.md). In short:

* **Routing:**
  * numerical questions use approved OSRIP data first;
  * one answering provider and one search route per question;
  * a fallback only after a failure;
  * a cross-check only when the person asks for it in Research mode.
* **Model ids** are settings with no assumed default (`OSRIP_OPENAI_MODEL`, `OSRIP_OPENAI_SEARCH_MODEL`, `OSRIP_GEMINI_MODEL`, `OSRIP_GEMINI_SEARCH_MODEL`).
* **Display rules:**
  * Every source carries a data status.
  * OpenAI web-search citations are labelled provider summaries.
  * Grounding with Google Search results are shown verbatim, with Google's Search Suggestions, apart from the answer. They are never given to a model.
* **Limits and logging:**
  * a daily call limit per provider and an optional budget (only with configured prices);
  * every call is logged in `provider_call`, without prompts or answers.
* **Readiness:** Service health shows each provider as unavailable / configured / tested / failed, with a live Test button.

Status: implemented and tested with scripted providers and mocked HTTP. **Live calls are pending, because no working OpenAI, Gemini, Anthropic or Brave key is available.**

### Voice (speech recognition and synthesis)

**Provider chosen: Azure AI Speech (REST).** Checked against Microsoft's official documentation on 2026-10-02: speech to text supports `ar-OM` (Arabic, Oman) and `en-GB`; neural voices exist for Omani Arabic (`ar-OM-AbdullahNeural`, male; `ar-OM-AyshaNeural`, female) and British English (`en-GB-RyanNeural`, `en-GB-SoniaNeural` and others), so Arabic is never read with a foreign voice. Recognition uses the short-audio REST API (WAV PCM 16 kHz mono, up to 60 seconds); synthesis returns MP3 (`audio-24khz-48kbitrate-mono-mp3`).

| Setting | Default | Notes |
|---|---|---|
| `OSRIP_SPEECH_PROVIDER` | `azure` | `azure` or `disabled`; `fake` is a test double, refused in production |
| `OSRIP_SPEECH_KEY` | – | Speech resource key, server side only |
| `OSRIP_SPEECH_REGION` or `OSRIP_SPEECH_ENDPOINT` | – | e.g. `uaenorth`, or `https://NAME.cognitiveservices.azure.com` |
| `OSRIP_SPEECH_VOICE_AR` / `_EN` | `ar-OM-AbdullahNeural` / `en-GB-RyanNeural` | The male voices match the avatar |
| `OSRIP_SPEECH_LOCALE_AR` / `_EN` | `ar-OM` / `en-GB` | Recognition locales |
| `OSRIP_SPEECH_MAX_SECONDS` | 60 | Longest recording |

Behaviour: the microphone is requested only when the user presses **Speak**; the browser records in memory and converts to WAV; the recording is sent once to `POST /api/v1/assistant/voice/transcribe`, passed to the provider and discarded (never stored or logged); the text fills the box for review and is never sent automatically. Answers are read with `POST /api/v1/assistant/voice/speak`, which only synthesises an assistant reply the caller owns (not arbitrary text); evidence markers are removed. Text and voice share the same guest allowance (only answers are counted; a guest who has used it is asked to sign in before recording). Without server speech the panel falls back to the browser's Web Speech API where available (the panel then says the browser's vendor processes the audio), and otherwise to text only. **Stop speaking**, **Mute** and **Cancel** are always available; nothing plays automatically except the reply to a question the user just asked by voice.

The avatar's speaking animation follows the measured loudness of the audio actually playing (Web Audio analyser); it is a simple speaking animation, **not lip synchronisation**, and the panel says so.

Status: implemented and tested with a scripted provider (WAV validation, ownership, CSRF, limits). **Not tested against live Azure Speech: no key was available; Arabic and English recognition quality not evaluated.**

### Canva (visual production)

The Canva integration connected to this workspace was used on 2026-10-01 and 2026-10-02. It offers image generation, design creation, editing and export; exporting a generated image at full size needs it placed in a saved Canva design, and saving needs the account owner's explicit approval. Results so far:

| Image | Canva media id | Source size | Native 4K | Status |
|---|---|---|---|---|
| AI Assistant face (fictional) | `MAHW1qlLO9M` | 1264 × 1264 | no | In use as the 200 × 200 preview returned by the connector (shown ≤ 96 CSS px) |
| Omani professional | `MAHWw5aV9sw` | 1680 × 944 | no | Generated, not exported |
| Electricity and renewables | `MAHWw39gpLA` | 1680 × 944 | no | Generated, not exported |
| Water | `MAHWw37y4X0` | 1680 × 944 | no | Generated, not exported |
| Agriculture, fisheries and food security | `MAHWwykGUko` | 1680 × 944 | no | Generated, not exported |
| Ports and trade | – | – | – | Failed: `quota_exceeded` (2026-10-01) |

Canva's generator returns at most 1680 px wide here, so a 3840 × 2160 file would be an upscale (2.29×) and must be labelled as such. Details and prompts: `frontend/assets/editorial/sources.json`.

## Official statistics (NCSI)

The automatic release checks, the registry, the worker and the live test are described in [OFFICIAL_SOURCES.md](OFFICIAL_SOURCES.md). The data portal below still needs a manual download.

### NCSI data portal

The electricity, water and foreign-trade datasets on data.gov.om need a signed-in portal account to download. Download the CSV files yourself, then follow the steps in `backend/scripts/ncsi_import.py`:

1. **inventory:** list every series in the file.
2. **Write a reviewed mapping file:** NCSI indicator name → OSRIP code and unit.
3. **convert:** only January 2022 onward, no partial years, regions matched by exact NCSI spelling.
4. **Register the source:** publisher National Centre for Statistics and Information, the statistical-table URL, the access date, and the Open Government License – Sultanate of Oman.
5. **Upload in Data Management,** then validate, approve and publish.

## SMS verification (registration and sign-in by phone)

**Status: application side complete and tested; no production provider.** No SMS
provider has been chosen for the project, so no real adapter exists. OSRIP does not
guess any vendor's endpoints, SDK calls or credential names. Phone registration stays
**disabled** (`OSRIP_SMS_ENABLED=false`), and the interface marks it unavailable with
e-mail offered instead.

What exists:

- Provider interface in `backend/app/services/sms.py`:
  - `request_verification(phone_e164) -> provider_ref`;
  - `check_verification(provider_ref, code) -> approved | denied | expired`;
  - errors: `invalid_number`, `undeliverable`, `provider_unavailable`.
- Routes `POST /auth/phone/request` and `POST /auth/phone/verify` (API.md).
- Rules enforced by OSRIP whatever the provider does:
  - E.164 normalization, with Oman (+968) as the default and the Omani mobile rule
    (8 digits beginning with 7 or 9);
  - a resend cooldown, and limits per number, per client and in total;
  - expiring, single-use challenges with a wrong-code limit, a row lock and a
    database trigger against replay;
  - accounts created only after verification, with the Viewer role only;
  - linking only from a signed-in session, and numbers never moved or merged
    between accounts.
- `test` provider: scripted delivery for automated tests and local development.
  - Codes live in process memory and are shown only by `GET /dev/sms-outbox` and the
    `/dev/mail` page.
  - Test numbers `+96890000000` (undeliverable) and `+96890000001` (outage) simulate
    failures.
  - The API refuses to start with this provider in production, and the dev endpoint
    answers 404 there.

Settings (`backend/.env`, `deploy/.env`; never in the frontend, never committed):

| Setting | Meaning |
|---|---|
| `OSRIP_SMS_ENABLED` | `false` by default. Phone sign-in is offered only when `true` and a known provider is set |
| `OSRIP_SMS_PROVIDER` | Adapter name. Only `test` exists today, and it is for tests only |
| `OSRIP_SMS_PROVIDER_API_KEY`, `OSRIP_SMS_PROVIDER_SERVICE_ID` | Placeholders. **Rename or extend them to the chosen provider's real fields** when the adapter is written |
| `OSRIP_SMS_CODE_MINUTES` (10), `OSRIP_SMS_MAX_ATTEMPTS` (5), `OSRIP_SMS_RESEND_SECONDS` (60), `OSRIP_SMS_PER_NUMBER_HOUR` (5), `OSRIP_SMS_PER_CLIENT_HOUR` (10), `OSRIP_SMS_GLOBAL_HOUR` (200), `OSRIP_SMS_DEFAULT_COUNTRY` (+968), `OSRIP_SMS_PROVIDER_TIMEOUT_SECONDS` (10) | Limits enforced by OSRIP |

(The brief names these `SMS_ENABLED`, `SMS_PROVIDER`, `SMS_PROVIDER_API_KEY` and
`SMS_PROVIDER_SERVICE_ID`; every OSRIP setting carries the `OSRIP_` prefix.)

**What remains before SMS can be switched on:**

1. **Choose a provider** that can deliver to Omani mobile networks. Record its terms,
   price per message and data-processing terms for phone numbers.
2. **Create the provider account.** The team does this; it cannot be done from the
   code. Keep the credentials out of chat and out of the repository.
3. **Write the adapter** from the provider's official documentation. Implement the two
   operations above, map the provider's error responses to the three error codes, use
   the timeout setting with no automatic retry, and register it in `_ADAPTERS`.
4. **Replace the placeholder settings** with the provider's real credential fields,
   and put the values in `deploy/.env` only.
5. **Register a sender ID** if the provider or Omani regulations require one.
6. **Run the live acceptance test** against a test deployment, with the owner of one
   authorized number present:
   `python backend\scripts\sms_acceptance.py --url https://<test-deployment>`.
   - It refuses to run unless the provider status is `configured`.
   - It checks delivery, a wrong code, the right code and a replayed code.
   - It writes `docs/sms/acceptance-*.json` with the number masked and without the code.
7. **Enable SMS only after that test passes.** Until then, phone registration must not
   be reported as active.
