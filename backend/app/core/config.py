"""Application settings, read from environment variables (prefix ``OSRIP_``).

Secrets are never committed; see ``backend/.env.example``.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Automated tests set OSRIP_ENV_FILE=none, so a developer's backend/.env (which may hold
# real provider keys) is never read by them.
_ENV_FILE = os.environ.get("OSRIP_ENV_FILE", ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OSRIP_", env_file=None if _ENV_FILE == "none" else _ENV_FILE, extra="ignore"
    )

    environment: str = Field(default="development")
    database_url: str = Field(
        default="postgresql+psycopg://osrip:osrip@localhost:5432/osrip",
        description="SQLAlchemy URL using the psycopg (v3) driver.",
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    api_prefix: str = "/api/v1"

    # ------------------------------------------------------------ sessions (booklet 3.15)
    session_cookie_name: str = "osrip_session"
    # Secure cookies need HTTPS; only plain-HTTP local development may turn this off.
    session_cookie_secure: bool = True
    session_absolute_hours: int = 8
    session_idle_minutes: int = 30
    # Keys the hash of client addresses in login_attempt (no raw IPs are stored).
    client_hash_key: SecretStr = Field(default=SecretStr("development-only-change-me"))

    # ------------------------------------------------------------ login throttling
    login_max_failures: int = 5
    login_window_minutes: int = 15

    # ------------------------------------------------------------ public address
    # Origin the browser uses (frontend; /api is served from the same origin). Used to
    # build e-mail links and OpenID Connect redirect URIs.
    public_base_url: str = "http://localhost:5173"

    # ------------------------------------------------------------ e-mail
    # outbox: development sink (stored, not sent; readable at /dev/outbox in development);
    # smtp: real delivery; disabled: no e-mail features (registration and links are off).
    email_backend: str = "outbox"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    verify_email_hours: int = 24
    reset_password_minutes: int = 30
    magic_link_minutes: int = 15
    email_requests_per_hour: int = 5
    # Changing a verified e-mail address or phone number needs the current password, or,
    # for an account without one (phone or Google/Microsoft sign-in), a session opened
    # within this many minutes.
    reauth_minutes: int = 10

    # ------------------------------------------------------------ external identity (OIDC)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: SecretStr | None = None
    microsoft_tenant: str = "common"
    oidc_request_minutes: int = 10

    # ------------------------------------------------------------ assistant
    # The answering model: anthropic (Messages API), openai (Responses API), gemini
    # (Interactions API), deepseek (Chat Completions, usage-billed); fake: scripted replies
    # for automated tests (refused in production); "" or disabled. One provider answers a
    # question; the fallback is used only when the primary fails before answering (timeout,
    # network, rate limit, server error, budget).
    assistant_provider: str = "anthropic"
    assistant_fallback_provider: str = ""
    anthropic_api_key: SecretStr | None = None
    assistant_model: str = "claude-sonnet-5-5"  # the Anthropic model id (configurable)
    # OpenAI and Gemini: model ids must be set explicitly (no assumed "latest" model).
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None  # answering model (Responses API, function tools)
    openai_search_model: str | None = None  # web search route (Responses API web_search tool)
    # Reasoning models may need longer than other providers: each OpenAI call may run this long.
    openai_timeout_seconds: float = 60.0
    # Reasoning effort (none, minimal, low, medium, high, xhigh; the model's default when unset):
    # lower is faster and cheaper. Which values a model accepts is in its model page.
    openai_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = (
        None
    )
    # Web search route: how much context the search gathers, and optionally only these domains
    # (at most 100, without https://; subdomains included). Empty: the whole web, with official
    # Omani sources preferred by the instructions.
    openai_search_context_size: Literal["low", "medium", "high"] = "medium"
    openai_search_allowed_domains: list[str] = Field(default_factory=list)
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None  # answering model (Interactions API, function tools)
    gemini_search_model: str | None = None  # Grounding with Google Search route
    # DeepSeek (Chat Completions API, optional): billed per token from a topped-up balance (no
    # general free tier; checked 2026-10-23 on api-docs.deepseek.com). It is used only when
    # billing is acknowledged too, so a key alone never starts paid use, as primary or fallback.
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str | None = None  # e.g. deepseek-flash (set explicitly)
    deepseek_billing_acknowledged: bool = False
    # Spending and request limits per provider and UTC day (provider_call records). The
    # budget applies only with prices configured, e.g. OSRIP_PROVIDER_PRICES=
    # {"openai": {"input_per_mtok": 1.0, "output_per_mtok": 4.0, "per_search": 0.01}}
    # (values from the provider's price list; nothing is assumed).
    provider_daily_call_limit: int = 500
    provider_daily_budget_usd: float | None = None
    provider_prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Google Search grounded results may be stored for at most two years (Gemini API terms).
    grounded_retention_days: int = 730
    assistant_timeout_seconds: float = 30.0
    assistant_max_per_minute: int = 5
    assistant_max_per_hour: int = 30
    # Signed-in fair use (booklet 3.35): a daily ceiling on provider calls per account.
    assistant_max_per_day: int = 100
    assistant_max_message_chars: int = 1000

    # ------------------------------------------------------------ web research (assistant tools)
    # The search route: brave (Brave Search API, research_api_key), openai (Responses API
    # web_search, openai_search_model), gemini (Grounding with Google Search,
    # gemini_search_model; shown to the person verbatim with its Search Suggestions and never
    # given to another model, as the Gemini API terms require); deepseek (DeepSeek Search API
    # with the DeepSeek key, only with OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED); fake / fake-openai
    # / fake-gemini: scripted routes for tests (refused in production); "" or disabled.
    # The fallback route is used only when the primary fails, or for a cross-check the
    # person asks for.
    research_provider: str = "brave"
    research_fallback_provider: str = ""
    research_api_key: SecretStr | None = None
    research_timeout_seconds: float = 10.0
    research_max_searches_per_answer: int = 3
    research_max_pages_per_answer: int = 3
    research_fetch_max_bytes: int = 2 * 1024 * 1024
    research_per_client_hour: int = 60  # web searches per client address per hour
    # How pages are read: direct (OSRIP's SSRF-safe fetcher, HTML and PDF) or deepseek (the
    # DeepSeek Fetch API, Markdown; the direct fetcher when it fails). Hosts ending in one of
    # research_fetch_direct_hosts are read directly first: DeepSeek Fetch timed out (HTTP 504)
    # on ncsi.gov.om and data.gov.om when checked on 2026-10-25, while direct reads worked.
    research_fetch_provider: str = "direct"
    research_fetch_direct_hosts: str = "gov.om"
    research_fetch_timeout_seconds: float = 40.0
    # Searches and pages are reused for this many hours (research_search, research_document);
    # when a search fails, the last successful results are shown with their own date.
    research_cache_hours: int = 24
    # Paid search and fetch calls per UTC day, across all users and jobs (provider_call rows).
    research_daily_search_limit: int = 200
    research_daily_fetch_limit: int = 200
    # Figures one answer may submit for validation, and whether validation may save a figure
    # that passes every check (an official document read in full, unambiguous codes, no
    # duplicate or conflict). Off: every figure waits for a reviewer.
    research_max_candidates_per_answer: int = 10
    research_auto_save: bool = True
    # A research answer may take more model rounds (search, read, look up codes, submit,
    # answer) and more time than an ordinary question; the last round must still answer.
    research_max_rounds: int = 12
    research_answer_seconds: float = 240.0
    research_max_searches_research: int = 6
    research_max_pages_research: int = 6

    # ------------------------------------------------------------ studies and page retrieval
    # Background studies (research jobs): a repeated study with the same parameters and the
    # same published data is served from cache for this many hours; bounded attempts.
    research_job_cache_hours: int = 24
    research_job_max_attempts: int = 3
    research_job_stale_minutes: int = 15  # a running job without a heartbeat is resumed
    # Firecrawl page retrieval (https://docs.firecrawl.dev, v2 /scrape and /map). Without a
    # key, studies retrieve pages directly with the SSRF-safe fetcher, or not at all.
    firecrawl_api_key: SecretStr | None = None
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    firecrawl_timeout_seconds: float = 45.0
    # Per study: pages retrieved, link depth followed from retrieved pages (0: only the
    # discovered addresses), run time, credits (1 per page, plus 1 per PDF page) and PDF
    # pages parsed. Hosts are limited to the official registry of the chosen source scope,
    # or to this list when set; each host is asked at most once per interval.
    crawl_max_pages: int = 8
    crawl_max_depth: int = 0
    crawl_max_runtime_seconds: int = 300
    crawl_max_credits: int = 60
    crawl_max_pdf_pages: int = 30
    crawl_host_interval_seconds: float = 2.0
    crawl_allowed_domains: list[str] = Field(default_factory=list)
    # Scheduled reports run only when this is switched on, and each schedule is off until
    # an administrator enables it; schedules that call paid services need allow_paid too.
    scheduled_reports_enabled: bool = False

    # ------------------------------------------------------------ speech (voice in and out)
    # azure: Azure AI Speech REST (speech_key and speech_region, or speech_endpoint);
    # "" or disabled: the browser's own speech features are used where available.
    speech_provider: str = "azure"
    speech_key: SecretStr | None = None
    speech_region: str | None = None  # e.g. "uaenorth"
    speech_endpoint: str | None = (
        None  # optional resource endpoint https://NAME.cognitiveservices.azure.com
    )
    # Al Mulhim speaks with a man's voice in both languages: Abdullah (Omani Arabic) and Ryan
    # (British English) are male neural voices. Choose only male voices if these change.
    speech_voice_ar: str = "ar-OM-AbdullahNeural"
    speech_voice_en: str = "en-GB-RyanNeural"
    speech_locale_ar: str = "ar-OM"
    speech_locale_en: str = "en-GB"
    speech_timeout_seconds: float = 20.0
    speech_max_seconds: int = 60  # the short-audio REST API limit
    speech_per_client_hour: int = 120

    # ------------------------------------------------------------ real-time voice (Talk)
    # Feature flag plus a LiveKit project (cloud or self-hosted). The backend issues short-lived,
    # room-scoped client tokens; the agent worker (app/voice/agent.py, livekit-agents) joins the
    # room and answers through the same conversation service and guest allowance as text.
    voice_realtime_enabled: bool = False
    livekit_url: str | None = None  # wss://YOUR-PROJECT.livekit.cloud
    livekit_api_key: str | None = None
    livekit_api_secret: SecretStr | None = None
    voice_token_minutes: int = 10
    voice_max_call_minutes: int = 15
    # Speech models for the agent session (LiveKit Inference model ids, chosen per language
    # after measuring Arabic and English quality; the speaking voices must be male, like the
    # Azure voices above); empty = not configured.
    voice_stt_model: str | None = None
    voice_tts_model_ar: str | None = None
    voice_tts_model_en: str | None = None
    # Optional avatar plugin (for example "did"); requires its plugin package and account.
    voice_avatar_provider: str | None = None
    voice_avatar_id: str | None = None

    # ------------------------------------------------------------ guest allowance (booklet 3.35)
    # Successful AI answers a visitor without an account may receive, across languages.
    guest_answer_limit: int = 5
    guest_policy_version: int = 1
    # Lifetime of the anonymous cookie and its server record after the last visit.
    guest_session_days: int = 90
    # Abuse limits. Per client address they are deliberately generous: one shared address
    # (a campus or mobile network) is many people, so it only caps automated abuse.
    guest_asks_per_minute: int = 10  # per guest session; the allowance itself bounds AI calls
    guest_asks_per_client_hour: int = 60
    guest_sessions_per_client_hour: int = 30

    # ------------------------------------------------------------ SMS verification (phone accounts)
    # Off unless explicitly enabled AND a provider is configured. Adapters: "twilio_verify"
    # (Twilio Verify API v2; the provider generates, sends and checks the code), "whatsapp"
    # (Meta WhatsApp Cloud API; OSRIP generates and checks the code, WhatsApp delivers it
    # with an authentication template) and "test" (scripted delivery for automated tests;
    # refused in production). Twilio credentials: the Account SID with either an API key
    # (SID and secret, preferred) or the Auth Token, and the Verify Service SID. Server side
    # only; never in the frontend. The OSRIP_SMS_* limits apply to every channel.
    sms_enabled: bool = False
    sms_provider: str = ""
    twilio_account_sid: str | None = None  # AC...
    twilio_api_key_sid: str | None = None  # SK... (with the secret below; preferred)
    twilio_api_key_secret: SecretStr | None = None
    twilio_auth_token: SecretStr | None = None  # used only when no API key is set
    twilio_verify_service_sid: str | None = None  # VA...
    # WhatsApp: "test" sends only to the numbers in whatsapp_test_recipients (Meta's free test
    # sender accepts up to 5 verified recipients); "production" sends to anyone and every
    # delivered code is charged by Meta. Production stays off until billing and business
    # verification are in place (docs/INTEGRATIONS.md).
    whatsapp_mode: str = "test"
    whatsapp_access_token: SecretStr | None = None  # a system user token (or the temporary one)
    whatsapp_phone_number_id: str | None = None  # the sender's phone number ID, not the number
    whatsapp_business_account_id: str | None = None  # WABA ID: template setup script only
    whatsapp_template_name: str = "osrip_verification_code"  # authentication template, en and ar
    whatsapp_test_recipients: str = ""  # comma-separated E.164 numbers, e.g. +96891234567
    whatsapp_api_version: str = "v23.0"
    sms_code_minutes: int = 10  # challenge lifetime
    sms_max_attempts: int = 5  # wrong codes allowed per challenge
    sms_resend_seconds: int = 60  # cooldown before another code to the same number
    sms_per_number_hour: int = 5  # codes per number per hour
    sms_per_client_hour: int = 10  # codes per client address per hour
    sms_global_hour: int = 200  # all codes per hour (cost protection)
    sms_default_country: str = "+968"  # Oman
    sms_provider_timeout_seconds: float = 10.0

    # ------------------------------------------------------------ uploads (untrusted input)
    upload_max_bytes: int = 5 * 1024 * 1024  # matches ck_import_job_file_size
    upload_max_rows: int = 50_000

    # ------------------------------------------------------------ datasets for analysis
    # Files people upload to analyse (CSV, Excel .xlsx, JSON): private to their owner, never
    # part of the published statistics. Limits per file and per account; AI summaries of a
    # dataset's computed results per account per UTC day (each is one model call).
    dataset_max_bytes: int = 5 * 1024 * 1024  # at most 10 MB (ck_analysis_dataset_size)
    dataset_max_rows: int = 20_000
    dataset_max_columns: int = 60
    dataset_max_per_user: int = 50
    dataset_summaries_per_day: int = 20

    # ------------------------------------------------------------ report exports (PDF, Excel)
    # A TrueType font with Latin letters and Arabic presentation forms, embedded (as a subset)
    # in PDF reports. Unset: Arial, Tahoma or Segoe UI (Windows), DejaVu Sans (Linux,
    # package fonts-dejavu-core) or Arial (macOS), the first one found.
    report_font_path: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
