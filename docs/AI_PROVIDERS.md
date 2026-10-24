# Governed AI and research providers

OSRIP's assistant (Al Mulhim / Ilham) answers from OSRIP's approved data first. It can also use
external AI models and web search. This document covers:

- which providers are used, and through which official APIs;
- how one is chosen for each question;
- how results are labelled;
- the limits that apply;
- what is stored;
- what has and has not been verified.

This arrived with migration `0018_provider_calls`. The vendor documentation was checked on **2026-10-10**.

## What is used, and what is not

| Provider | API (official) | Used for | Settings |
|---|---|---|---|
| OSRIP data and sources | OSRIP's own database, through deterministic backend tools | Answering every numerical question first | – |
| Anthropic | Messages API `POST https://api.anthropic.com/v1/messages` (existing adapter) | Answering | `OSRIP_ANTHROPIC_API_KEY`, `OSRIP_ASSISTANT_MODEL` |
| OpenAI | Responses API `POST https://api.openai.com/v1/responses` | Answering (function tools); web search (`web_search` tool) | `OSRIP_OPENAI_API_KEY`, `OSRIP_OPENAI_MODEL`, `OSRIP_OPENAI_SEARCH_MODEL` |
| Google Gemini | Interactions API `POST https://generativelanguage.googleapis.com/v1beta/interactions` | Answering (function tools); Grounding with Google Search (`google_search` tool) | `OSRIP_GEMINI_API_KEY`, `OSRIP_GEMINI_MODEL`, `OSRIP_GEMINI_SEARCH_MODEL` |
| Brave Search | Search API `GET https://api.search.brave.com/res/v1/web/search` (existing adapter) | Web search | `OSRIP_RESEARCH_API_KEY` |
| DeepSeek (optional, **usage-billed**) | Chat Completions API `POST https://api.deepseek.com/chat/completions` (OpenAI-compatible) | Answering (function tools; thinking switched off so a tool call can be required) | `OSRIP_DEEPSEEK_API_KEY`, `OSRIP_DEEPSEEK_MODEL`, `OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED=true` |

- **No consumer website is automated.** OSRIP never drives chatgpt.com, gemini.google.com, claude.ai or any other chat website, in a browser or otherwise.
- **A consumer subscription is not API access.** ChatGPT Plus, Gemini Advanced or a Claude app plan does not give OSRIP an API key or API billing. Each provider needs an API key from its developer console (platform.openai.com, aistudio.google.com or console.cloud.google.com, console.anthropic.com, api-dashboard.search.brave.com), with API billing set up there.
- **Model ids are configuration, never assumed.** The OpenAI and Gemini model settings have no default. A provider without its model id is reported as unavailable, with the missing setting named.
  - The Anthropic adapter keeps its documented default (`claude-sonnet-5-5`, overridable).
  - Choose ids from the provider's current model list. Check that the model supports the capability you need: function calling for answering, the web search tool or Google Search grounding for search.
- **Keys stay on the server.** They live in `backend/.env` (development) or `deploy/.env` (hosting secrets).
  - They are never sent to a browser, logged or stored in the database.
  - The readiness view and `/assistant/status` report setting *names* only.

## Cost: the recommended free-tier setup, and paid providers

Checked on **2026-10-23** against the providers' own pages.

**Gemini (recommended start).** Google's price list (<https://ai.google.dev/gemini-api/docs/pricing>,
updated 2026-10-22) shows a free tier for, among others, `gemini-3.8-flash`, `gemini-3.6-flash`
and `gemini-3.5-flash-lite`. The rate-limit page (<https://ai.google.dev/gemini-api/docs/rate-limits>)
publishes no fixed numbers: the limits depend on the project's usage tier and are shown in Google
AI Studio. On the free tier Google may use the content to improve its products. So:

- set `OSRIP_ASSISTANT_PROVIDER=gemini`, `OSRIP_GEMINI_API_KEY` (from Google AI Studio, for a
  project without billing) and `OSRIP_GEMINI_MODEL=gemini-3.8-flash` (or `gemini-3.5-flash-lite`
  for higher free limits), in `backend/.env`;
- confirm that the model answers *for your account* with Settings › AI and search providers ›
  Test. OSRIP cannot see an account's free-tier eligibility or limits until a real call is made;
  this was **not** verified here, because no key is configured on this machine;
- the model receives the question, OSRIP's rules and the public statistical evidence the tools
  return. It never receives credentials, account details or other people's records.

**DeepSeek (optional).** The price page (<https://api-docs.deepseek.com/quick_start/pricing>)
bills per input and output token, deducted from a topped-up (or granted) balance; there is no
general free tier. The adapter is built only when `OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED=true` is set
as well as the key and model: a key alone never starts paid use, as the primary or as the fallback.
An exhausted balance (HTTP 402) is reported as a budget failure and is not retried.

**Never switched silently.** The fallback provider is used only when an administrator sets
`OSRIP_ASSISTANT_FALLBACK_PROVIDER`; Settings marks a usage-billed fallback. Settings shows each
provider's billing basis (usage-billed, free tier available, plan, credits).

## Reliability and limits

- **Timeout:** `OSRIP_ASSISTANT_TIMEOUT_SECONDS` per call (30 s), and twice that for a whole answer.
- **Bounded retries:** one retry on a timeout, network error, 429 or 5xx. On 429/503 the
  provider's `Retry-After` (seconds) is waited for, up to 10 s; a longer wait fails at once and
  the fallback provider (if one is set) answers. Authentication, model and balance errors are
  not retried.
- **Usage limits:** a daily call limit per provider (`OSRIP_PROVIDER_DAILY_CALL_LIMIT`), an
  optional daily budget with prices from the provider's list (`OSRIP_PROVIDER_PRICES`,
  `OSRIP_PROVIDER_DAILY_BUDGET_USD`), per-account limits per minute, hour and day, and five free
  answers per guest. Every call is logged (outcome, time, tokens; never the question).
- **Caching:** a repeated submission of the same question (same request id, for example after a
  dropped connection) returns the stored reply without a second model call; a background study
  with the same parameters and the same published data is served from its cache for 24 h
  (`OSRIP_RESEARCH_JOB_CACHE_HOURS`). Answers are not shared between people: each rests on the
  evidence retrieved for that question.
- **Status:** Settings › Services and AI and search providers show configured / tested /
  failed / unavailable, the role of each provider, today's calls and errors, and the names
  (never values) of missing settings.

## Answering from a sector page

"Request analysis" on a sector page sends the applied selection (sector, indicator, area,
frequency, start and end period, and breakdown) with the question. It is validated as codes and
dates and becomes one rule in the model's instructions: answer for exactly that selection, and name
any other period used (for example the same months a year earlier) as an additional comparison
period. The assistant shows the selection above the question box; the reader can remove it.

When no provider answers, the tables, calculations and charts on the sector pages keep working;
the assistant gives a data-based reply labelled as prepared without AI interpretation, and the
sector summary is labelled as a statistical summary, not AI-generated analysis.

## Routing policy (decided by rules, not by a model)

1. **Numbers start with approved OSRIP data.**
   - A question asking for a figure, quantity, rate, share, change or comparison is classified as numerical (`backend/app/services/assistant/routing.py`, English and Arabic patterns).
   - Web search is refused (`data_first`) until a platform data tool has run in that answer (`list_indicators`, `get_observations`, `latest_period`, ...).
2. **Missing or recent context may use the web.**
   - The web may fill what the data do not cover.
   - A question about recent events ("latest news", "this week", "اليوم", ...) may search first.
   - Web research runs only when the person has it switched on, or in Research mode, and only when a search route is configured.
3. **One primary provider per task.** One model answers each question, and one search route searches.
4. **A second provider only for a fallback or a justified comparison:**
   - *Answering fallback* (`OSRIP_ASSISTANT_FALLBACK_PROVIDER`): used only when the primary fails before its first answer. Failures that count are timeout, network, rate limit, server error, the daily call limit or the budget.
   - *Search fallback* (`OSRIP_RESEARCH_FALLBACK_PROVIDER`): used only when the first route's search fails.
   - *Cross-check*: in Research mode, only when the person ticks **"Cross-check with a second search route"**. The option is shown only when two different routes are configured, and is off by default.
5. **Not every provider for every question.** Nothing fans out. The routes used, and why, are recorded with the answer under "How this answer was prepared":
   - the answering provider and model;
   - any fallback, with its reason;
   - the routing decision;
   - every search route with its role and outcome.
6. **Agreement is not evidence.** A cross-check result carries the note "Agreement between two AI models or search routes is not independent factual evidence". The interface repeats it next to the option and in the method summary.

## How results are labelled

Every evidence item has a `data_status`, shown as a badge next to the source.

| `data_status` | Meaning |
|---|---|
| `approved_official` | A published value from a registered official source (verified data mode) |
| `synthetic_demonstration` | Labelled demonstration data (synthetic mode); never presented as Omani statistics |
| `unreviewed_external` | Found on the web; not OSRIP data until reviewed and imported |
| `calculated` | Computed by OSRIP's deterministic functions from the cited inputs |
| `model_forecast` | A validated model estimate, not an official statistic |
| `assumption_scenario` | Arithmetic on the person's stated assumption |
| `reference` | Definitions, methods, documented notes and search records |

What each item states:

- **Observations** keep the indicator, value, unit, geography, period (with incomplete or year-to-date flags), revision status, source title, publisher, record locator and dataset version.
- **Web items** keep the URL, title, publisher, source class (official Oman, international, research, secondary), the publication date and its basis, the retrieval time, and the exact text seen.
- **Ranking.** Official Omani sources rank first. If a search engine route finds no official result, one more search restricted to `site:gov.om` is made.
- **Citations from each provider are kept as that provider returns them:**
  - *Brave:* the engine's snippet (`search_snippet`).
  - *OpenAI web search:* each `url_citation` annotation (URL, title and the cited span) becomes a **provider summary** (`content_kind: provider_summary`, `summary_by: <model>`). It is labelled "Summary by <model> with a citation, not the source's own words", with a visible, clickable link.
    - The model is told to read the page (`read_web_page`) before relying on a figure from it.
    - Provider summaries never enter the review queue.
  - *Grounding with Google Search (Gemini):* the Gemini API terms say grounded results must be shown with their Search Suggestions and must not be modified or mixed with other content. So this route is **display-only**:
    - The grounded text, its citations and Google's Search Suggestions are stored with the reply (`structured.grounded_context`).
    - They are shown verbatim in a separate "Google Search results" panel below the answer.
    - The Search Suggestions are Google's HTML, rendered in a sandboxed frame without scripts; links open in a new tab.
    - They are **never given to the answering model**, never used as evidence for the answer and never queued as figures. The model only learns that results were "shown separately".
    - They are removed from stored replies after `OSRIP_GROUNDED_RETENTION_DAYS` (730, the two-year limit in the terms) by `python -m app.cli purge-grounded`.
- **New observations need review.** Figures the model reports from cited page text go to the data managers' review queue (`research_candidate`) with all their metadata. Accepting one never publishes it: it must go through the normal upload, validation, approval and publication workflow. Nothing found on the web is written into approved data.
- **No invented statistics.** Every number in a reply must appear in the evidence its `[E#]` marker cites. Otherwise the reply is withheld (`unverified`), and so are the recommendation cards. A grounded panel cannot back a number in the answer, because it is not evidence.

## Safety

- **No model-generated code is run.** The model can call only the fixed, read-only backend tools, with validated arguments. All calculations (growth, shares, comparisons, studies, scenarios) are OSRIP's deterministic functions. No SQL, Python, shell or browser script from a model is ever executed.
- **Retrieved content is untrusted.**
  - Search results and page text are passed to the model labelled as untrusted, with instructions to ignore any instruction inside them.
  - A planted instruction in a provider summary is tested (`FakeOpenAISearch` "inject" case). It cannot change the identity, tools or evidence rules.
  - Pages are fetched only by evidence id, never by a URL taken from page text. They go through `safe_fetch.py`:
    - public addresses only (no private, loopback or link-local);
    - the connection pinned to the checked address;
    - at most 3 redirects, each re-checked;
    - 2 MB and a timeout.
- **Valid abstention.** With no evidence the reply says so (`no_evidence`). With unsupported numbers it is withheld (`unverified`). If every search failed, the failures are listed and nothing is claimed. If no model is configured, a labelled non-AI record lookup is given instead.

## Limits and spending

| Limit | Setting | Default |
|---|---|---|
| Searches per answer | `OSRIP_RESEARCH_MAX_SEARCHES_PER_ANSWER` | 3 (each route attempt counts) |
| Pages read per answer | `OSRIP_RESEARCH_MAX_PAGES_PER_ANSWER` | 3 |
| Searches per client per hour | `OSRIP_RESEARCH_PER_CLIENT_HOUR` | 60 |
| Model and search timeouts | `OSRIP_ASSISTANT_TIMEOUT_SECONDS`, `OSRIP_RESEARCH_TIMEOUT_SECONDS` | 30 s, 10 s; an answering call is retried once after a transient failure, then the fallback (if any); a failed search goes to the fallback route (if any) |
| Calls per provider per day | `OSRIP_PROVIDER_DAILY_CALL_LIMIT` | 500 |
| Budget per provider per day (USD) | `OSRIP_PROVIDER_DAILY_BUDGET_USD` with `OSRIP_PROVIDER_PRICES` | off |
| Questions per person | guest allowance, `OSRIP_ASSISTANT_MAX_PER_*` | see `INTEGRATIONS.md` |

- **Call log.** Every provider call, successful or not, is recorded in `provider_call`: provider, capability, model, outcome code, duration, tokens, search count and estimated cost. **No prompt, question or answer is stored there.**
- **Daily limit.** Over the limit the call is refused before anything is sent, and the refusal is recorded. The guest is not charged, and the fallback (if any) is tried.
- **Budget.** Enforced only for providers with prices in `OSRIP_PROVIDER_PRICES`, using `input_per_mtok`, `output_per_mtok` and `per_search` from the provider's own price list. OSRIP assumes no prices. Without them the readiness view says "cost not estimated".

## Provider readiness (administrators)

**Service health** (`/admin/health`, permission `audit.read`) lists each provider:

- **Unavailable:** not configured. The missing setting names are shown.
- **Configured, not tested:** settings are present. A key alone proves nothing.
- **Tested:** the latest test or call succeeded.
- **Failed:** the latest test or call failed, with its code.

Each card also shows:

- the roles the provider plays (answers or searches, primary or fallback);
- the configured model;
- today's calls, failures and the limit;
- the estimated cost;
- the last call;
- a link to the official API documentation;
- a **Test** button for each configured capability, shown only to administrators (`user.manage`; reading the view alone is not enough). It makes one minimal live call (limited to 20 an hour per administrator), and the result is recorded as a test call.

The API behind it:

- `GET /api/v1/admin/providers`
- `POST /api/v1/admin/providers/{anthropic|openai|gemini|brave}/test?capability=answer|search`

## Setting up a provider (no secret goes into chat or into the repository)

1. Create an API key in the provider's developer console and set up API billing there.
2. Put it in `backend/.env` (development) or the hosting secret settings / `deploy/.env` (deployment). Set the model id from the provider's current model list. For example, to answer with OpenAI and search with Gemini grounding:
   ```
   OSRIP_ASSISTANT_PROVIDER=openai
   OSRIP_OPENAI_API_KEY=<from platform.openai.com>
   OSRIP_OPENAI_MODEL=<a Responses API model with function calling>
   OSRIP_RESEARCH_PROVIDER=gemini
   OSRIP_GEMINI_API_KEY=<from Google AI Studio>
   OSRIP_GEMINI_SEARCH_MODEL=<a Gemini model that supports Grounding with Google Search>
   ```
3. Optionally set a fallback, the daily limit, the prices and the budget.
4. Apply the migration (`alembic upgrade head`; additive, `0018_provider_calls`) and restart the API.
5. Open **Service health → AI and search providers** and press **Test**. The card shows "Tested" only after a real call has worked.

Production refuses to start if a scripted test route (`fake`, `fake-openai` or `fake-gemini`) is configured for any provider or fallback.

## Verification status

- **Implemented and tested locally** with scripted providers and mocked HTTP (no network):
  - **Backend:** `tests/test_ai_providers.py` (21) and `tests/test_ai_providers_integration.py` (9). They cover:
    - request and response formats for OpenAI and Gemini;
    - function-call round trips;
    - byte-offset citations;
    - transient-failure retry and fallback;
    - daily limit and budget;
    - readiness states;
    - unavailable providers;
    - prompt injection in a provider summary;
    - timeouts;
    - the routing policy;
    - grounded results kept display-only;
    - cross-check only when asked;
    - conflicting sources across routes, each reported with its own source and status;
    - unsupported figures withheld;
    - administrator-only readiness;
    - grounded retention.
  - Also `tests/test_api_foundation.py` (the production refusal of scripted routes) and `tests/test_migrations_roundtrip_integration.py` (the `provider_call` checks and the 0018 round trip).
  - **Browser:** `e2e-api/governed-ai.spec.ts` (4 tests):
    - data-status badges;
    - data-first route;
    - fallback after a failed route, with the Google results panel and sandboxed suggestions;
    - cross-check off by default and labelled;
    - readiness view without keys.
  - Also `e2e-api/upgrade.spec.ts`: both routes failing, both shown, not charged.
  - **DeepSeek and Retry-After** (2026-10-24): `tests/test_ai_providers_deepseek.py` (7, mocked
    transport): request format, tool calls, usage, the billing acknowledgement, 402 as budget,
    one wait of up to 10 s on `Retry-After`, longer waits refused.
  - **Sector selection** (2026-10-24): `tests/test_assistant_selection_integration.py` (3): the
    rule reaches the model; malformed selections are refused before any provider call; the
    scripted model looks up exactly the selected indicator, area, frequency and years and cites
    only the periods inside the range. In the browser: `e2e-api/interface.spec.ts` and the
    evaluation scenario (`e2e-demo`, test 9).
- **Not verified live.** No working OpenAI, Gemini, Anthropic or Brave API key is available here (the earlier Anthropic and Brave keys were rejected). Live behaviour is therefore **pending**:
  - real response shapes;
  - how often each model calls the tools;
  - citation quality;
  - Search Suggestions rendering;
  - the real token and search counts.

  Once keys are set, use the Test buttons and one Research-mode question per route, and record the results in `docs/TEST_RESULTS.md`.

## Official documentation consulted (2026-10-10)

- OpenAI:
  - Responses API reference: https://developers.openai.com/api/reference/resources/responses
  - Web search tool: https://developers.openai.com/api/docs/guides/tools-web-search
  - Function calling: https://developers.openai.com/api/docs/guides/function-calling
- Google:
  - Gemini Interactions API: https://ai.google.dev/gemini-api/docs/interactions (reference https://ai.google.dev/api/interactions)
  - Function calling: https://ai.google.dev/gemini-api/docs/function-calling
  - Grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
  - Gemini API Additional Terms (Grounded Results, Search Suggestions): https://ai.google.dev/gemini-api/terms
- Anthropic Messages API: https://docs.anthropic.com/en/api/messages
- Brave Search API: https://api-dashboard.search.brave.com/app/documentation
