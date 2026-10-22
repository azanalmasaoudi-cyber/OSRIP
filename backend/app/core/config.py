"""Application settings, read from environment variables (prefix ``OSRIP_``).

Secrets are never committed; see ``backend/.env.example``.
"""

import os
from functools import lru_cache

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

    # ------------------------------------------------------------ external identity (OIDC)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: SecretStr | None = None
    microsoft_tenant: str = "common"
    oidc_request_minutes: int = 10

    # ------------------------------------------------------------ assistant
    # The answering model: anthropic (Messages API), openai (Responses API), gemini
    # (Interactions API); fake: scripted replies for automated tests (refused in production);
    # "" or disabled. One provider answers a question; the fallback is used only when the
    # primary fails before answering (timeout, network, rate limit, server error, budget).
    assistant_provider: str = "anthropic"
    assistant_fallback_provider: str = ""
    anthropic_api_key: SecretStr | None = None
    assistant_model: str = "claude-sonnet-5-5"  # the Anthropic model id (configurable)
    # OpenAI and Gemini: model ids must be set explicitly (no assumed "latest" model).
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None  # answering model (Responses API, function tools)
    openai_search_model: str | None = None  # web search route (Responses API web_search tool)
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None  # answering model (Interactions API, function tools)
    gemini_search_model: str | None = None  # Grounding with Google Search route
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
    # given to another model, as the Gemini API terms require); fake / fake-openai /
    # fake-gemini: scripted routes for tests (refused in production); "" or disabled.
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
    # Off unless explicitly enabled AND a provider is configured. No production SMS
    # provider has been selected for this project yet, so the only implemented adapter
    # is "test" (scripted delivery for automated tests; refused in production). A real
    # adapter must be written against the chosen provider's official documentation.
    sms_enabled: bool = False
    sms_provider: str = ""
    sms_provider_api_key: SecretStr | None = None
    sms_provider_service_id: str | None = None
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
