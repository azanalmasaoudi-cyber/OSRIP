-- OSRIP migration 0011: usernames and required password changes for operator-created
-- accounts, and the review queue for statistics found by the assistant's web research.

-- ================================================================== accounts
-- An operator may create an account identified by a username alone (no e-mail address
-- or phone number is invented for it). Usernames are compared case-insensitively.
-- Self-registration still requires a verified e-mail address or phone number.
ALTER TABLE app_user ADD COLUMN username text
    CONSTRAINT ck_app_user_username CHECK (username IS NULL OR username ~ '^[A-Za-z][A-Za-z0-9_.-]{2,31}$');
CREATE UNIQUE INDEX uq_app_user_username ON app_user (lower(username)) WHERE username IS NOT NULL;

ALTER TABLE app_user DROP CONSTRAINT ck_app_user_has_identifier;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_has_identifier
    CHECK (is_service_account OR email IS NOT NULL OR phone_e164 IS NOT NULL OR username IS NOT NULL);

-- Set for temporary credentials (for example an initial password shared with the
-- account holder). While true, the account can only change its password or sign out.
ALTER TABLE app_user ADD COLUMN password_change_required boolean NOT NULL DEFAULT false;

-- ================================================================== research review queue
INSERT INTO permission (code, description) VALUES
    ('research.review', 'Review statistics found by web research before any import');
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('data_manager', 'research.review');

-- A numerical observation the assistant found on a web page. It is evidence for a data
-- manager to check, never part of the published dataset: accepting a candidate only
-- marks it as ready to be imported through the normal upload, approval and publication
-- workflow. Every field the brief requires is kept with the value.
CREATE TABLE research_candidate (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status            text NOT NULL DEFAULT 'pending'
                          CONSTRAINT ck_research_candidate_status
                          CHECK (status IN ('pending', 'accepted', 'rejected', 'duplicate')),
    domain            text NOT NULL
                          CONSTRAINT ck_research_candidate_domain
                          CHECK (domain IN ('electricity', 'water', 'food_security', 'trade', 'general')),
    indicator         text NOT NULL CONSTRAINT ck_research_candidate_indicator CHECK (length(indicator) BETWEEN 1 AND 300),
    indicator_code    text REFERENCES indicator (code),   -- the platform indicator it may correspond to
    value             numeric NOT NULL,
    value_text        text NOT NULL,                       -- the number exactly as it appears in the excerpt
    unit              text NOT NULL CONSTRAINT ck_research_candidate_unit CHECK (length(unit) BETWEEN 1 AND 80),
    geography         text NOT NULL CONSTRAINT ck_research_candidate_geo CHECK (length(geography) BETWEEN 1 AND 120),
    period_label      text NOT NULL,
    period_start      date,
    period_end        date,
    CONSTRAINT ck_research_candidate_period CHECK (period_start IS NULL OR period_end IS NULL OR period_end >= period_start),
    -- Statistical observations are kept from 2022 onward (earlier material is background only).
    CONSTRAINT ck_research_candidate_scope CHECK (period_end IS NULL OR period_end >= DATE '2022-01-01'),
    publication_date  date,
    publisher         text NOT NULL,
    source_title      text NOT NULL,
    source_url        text NOT NULL CONSTRAINT ck_research_candidate_url CHECK (source_url ~ '^https?://'),
    source_class      text NOT NULL
                          CONSTRAINT ck_research_candidate_class
                          CHECK (source_class IN ('official', 'international', 'secondary')),
    excerpt           text NOT NULL,                       -- the retrieved text that contains the value
    retrieved_at      timestamptz NOT NULL,
    search_provider   text NOT NULL,
    language          text NOT NULL CONSTRAINT ck_research_candidate_language CHECK (language IN ('en', 'ar')),
    message_id        bigint REFERENCES assistant_message (id) ON DELETE SET NULL,
    proposed_by       uuid REFERENCES app_user (id) ON DELETE SET NULL,   -- NULL for a guest's conversation
    checks            jsonb NOT NULL DEFAULT '{}'::jsonb,  -- duplicate, revision, unit and period checks at review time
    review_note       text,
    reviewed_by       uuid REFERENCES app_user (id),
    reviewed_at       timestamptz,
    CONSTRAINT ck_research_candidate_review CHECK ((status = 'pending') = (reviewed_at IS NULL)),
    created_at        timestamptz NOT NULL DEFAULT now()
);
-- The same figure from the same page is queued once, however often it is found again.
CREATE UNIQUE INDEX uq_research_candidate_figure
    ON research_candidate (source_url, lower(indicator), period_label, value);
CREATE INDEX ix_research_candidate_status ON research_candidate (status, created_at DESC);
