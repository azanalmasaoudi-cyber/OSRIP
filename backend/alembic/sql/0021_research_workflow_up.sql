-- 0021: the research workflow.
--
-- 1. Replies given as a data-based report without AI interpretation ('data_report': the
--    answer service failed; the reply lists published records and OSRIP calculations; never
--    charged).
-- 2. Page retrieval (Firecrawl) as a metered provider capability; credits are its billing unit.
-- 3. Scheduled reports, configured by an administrator and off by default.
-- 4. Studies run as background jobs: their steps, progress, attempts, cancellation, cache key
--    and result.
-- 5. The documents a study retrieved, with their provenance (URL, publisher, title, retrieval
--    time, publication date, reporting period), content digest, duplicates and revisions.
--    Retrieved text is untrusted evidence: kept as a bounded excerpt, never as data.

ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN (
        'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup',
        'profile', 'cancelled', 'data_report'
    )
);

ALTER TABLE provider_call DROP CONSTRAINT provider_call_capability_check;
ALTER TABLE provider_call ADD CONSTRAINT provider_call_capability_check CHECK (
    capability IN ('answer', 'search', 'retrieve', 'test_answer', 'test_search', 'test_retrieve')
);
ALTER TABLE provider_call ADD COLUMN credits integer CHECK (credits IS NULL OR credits >= 0);

CREATE TABLE report_schedule (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    sector               text NOT NULL CHECK (sector IN ('electricity', 'water', 'food_security', 'trade')),
    area                 text NOT NULL DEFAULT 'OM' CHECK (area ~ '^[A-Z]{2}(-[A-Z0-9]{2,3}){0,2}$'),
    data_mode            text NOT NULL CHECK (data_mode IN ('verified_source', 'synthetic')),
    question             text NOT NULL CHECK (length(question) BETWEEN 1 AND 1000),
    language             text NOT NULL DEFAULT 'en' CHECK (language IN ('en', 'ar')),
    frequency            text NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'quarterly')),
    -- none: OSRIP's published data only (no external calls); official: Omani official sites;
    -- official_international: also international statistical organisations.
    source_scope         text NOT NULL DEFAULT 'none'
                         CHECK (source_scope IN ('none', 'official', 'official_international')),
    max_pages            integer NOT NULL DEFAULT 5 CHECK (max_pages BETWEEN 0 AND 50),
    max_credits_per_run  integer NOT NULL DEFAULT 25 CHECK (max_credits_per_run BETWEEN 0 AND 1000),
    max_credits_per_month integer NOT NULL DEFAULT 100 CHECK (max_credits_per_month BETWEEN 0 AND 10000),
    -- A schedule that calls paid services must be allowed explicitly; none is by default.
    allow_paid           boolean NOT NULL DEFAULT false,
    enabled              boolean NOT NULL DEFAULT false,
    next_run_at          timestamptz,
    last_run_at          timestamptz,
    created_by           uuid REFERENCES app_user (id) ON DELETE SET NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_report_schedule_paid CHECK (source_scope = 'none' OR allow_paid OR NOT enabled)
);

CREATE TABLE research_job (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              uuid REFERENCES app_user (id) ON DELETE CASCADE,
    schedule_id          uuid REFERENCES report_schedule (id) ON DELETE SET NULL,
    sector               text NOT NULL CHECK (sector IN ('electricity', 'water', 'food_security', 'trade')),
    area                 text NOT NULL CHECK (area ~ '^[A-Z]{2}(-[A-Z0-9]{2,3}){0,2}$'),
    period_from          date,
    period_to            date,
    question             text NOT NULL CHECK (length(question) BETWEEN 1 AND 1000),
    language             text NOT NULL CHECK (language IN ('en', 'ar')),
    data_mode            text NOT NULL CHECK (data_mode IN ('verified_source', 'synthetic')),
    source_scope         text NOT NULL CHECK (source_scope IN ('none', 'official', 'official_international')),
    limits               jsonb NOT NULL DEFAULT '{}'::jsonb,
    state                text NOT NULL DEFAULT 'queued'
                         CHECK (state IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled')),
    stage                text,
    steps                jsonb NOT NULL DEFAULT '[]'::jsonb,
    attempts             integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts         integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 5),
    cache_key            text NOT NULL CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    cached_from          uuid REFERENCES research_job (id) ON DELETE SET NULL,
    cancel_requested_at  timestamptz,
    error_code           text CHECK (error_code IS NULL OR error_code ~ '^[a-z0-9_]{1,40}$'),
    analysis_id          uuid REFERENCES study_run (id) ON DELETE SET NULL,
    result               jsonb NOT NULL DEFAULT '{}'::jsonb,
    credits_used         integer NOT NULL DEFAULT 0 CHECK (credits_used >= 0),
    created_at           timestamptz NOT NULL DEFAULT now(),
    started_at           timestamptz,
    finished_at          timestamptz,
    heartbeat_at         timestamptz,
    CONSTRAINT ck_research_job_period CHECK (
        period_from IS NULL OR period_to IS NULL OR period_from <= period_to
    ),
    CONSTRAINT ck_research_job_finished CHECK (
        (state IN ('succeeded', 'partial', 'failed', 'cancelled')) = (finished_at IS NOT NULL)
    )
);

CREATE INDEX ix_research_job_queue ON research_job (created_at) WHERE state IN ('queued', 'running');
CREATE INDEX ix_research_job_user ON research_job (user_id, created_at DESC);
CREATE INDEX ix_research_job_cache ON research_job (cache_key, finished_at DESC) WHERE state = 'succeeded';
CREATE INDEX ix_research_job_schedule ON research_job (schedule_id, created_at DESC);

CREATE TABLE research_document (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id               uuid NOT NULL REFERENCES research_job (id) ON DELETE CASCADE,
    url                  text NOT NULL CHECK (url ~ '^https?://' AND length(url) <= 2048),
    final_url            text CHECK (final_url IS NULL OR (final_url ~ '^https?://' AND length(final_url) <= 2048)),
    host                 text NOT NULL,
    source_class         text NOT NULL CHECK (source_class IN ('official', 'international', 'research', 'secondary')),
    publisher            text,
    title                text,
    retrieved_at         timestamptz NOT NULL DEFAULT now(),
    published            date,
    reporting_period     text,
    content_type         text,
    retriever            text NOT NULL CHECK (retriever IN ('firecrawl', 'direct', 'fake')),
    status               text NOT NULL CHECK (status ~ '^[a-z0-9_]{1,40}$'),
    depth                integer NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 3),
    pages                integer CHECK (pages IS NULL OR pages >= 0),
    credits              integer NOT NULL DEFAULT 0 CHECK (credits >= 0),
    sha256               text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    excerpt              text CHECK (excerpt IS NULL OR length(excerpt) <= 20000),
    duplicate_of         uuid REFERENCES research_document (id) ON DELETE SET NULL,
    -- The same address retrieved earlier with different content (a revised publication).
    revision_of          uuid REFERENCES research_document (id) ON DELETE SET NULL
);

CREATE INDEX ix_research_document_job ON research_document (job_id, retrieved_at);
CREATE INDEX ix_research_document_url ON research_document (url, retrieved_at DESC);
CREATE INDEX ix_research_document_sha ON research_document (sha256);
