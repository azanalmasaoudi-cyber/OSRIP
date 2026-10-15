-- OSRIP migration 0012: assistant modes and structured replies, research papers as a
-- source class, saved research, indicator watchlists and data-update / threshold alerts.

-- ================================================================== structured replies
-- ask | analyze | research | compare | scenario (NULL for replies stored before 0012).
ALTER TABLE assistant_message ADD COLUMN mode text
    CONSTRAINT ck_assistant_message_mode
    CHECK (mode IS NULL OR mode IN ('ask', 'analyze', 'research', 'compare', 'scenario'));
-- Validated structured parts of a reply: recommendation cards, drivers, the separation of
-- evidence, hypotheses and assumptions, and source conflicts. Never free-form model output:
-- every part is checked against the evidence before it is stored.
ALTER TABLE assistant_message ADD COLUMN structured jsonb NOT NULL DEFAULT '{}'::jsonb;

-- ================================================================== research papers
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_class;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_class
    CHECK (source_class IN ('official', 'international', 'research', 'secondary'));

-- ================================================================== saved research
-- A user's saved copy of an assistant reply. The snapshot keeps the reply, its evidence and
-- citations as they were when saved, so a later edit or deletion of the conversation does
-- not change a brief that was downloaded or shared.
CREATE TABLE saved_research (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    message_id  bigint REFERENCES assistant_message (id) ON DELETE SET NULL,
    title       text NOT NULL CONSTRAINT ck_saved_research_title CHECK (length(title) BETWEEN 1 AND 200),
    note        text CONSTRAINT ck_saved_research_note CHECK (note IS NULL OR length(note) <= 4000),
    question    text NOT NULL,
    mode        text,
    language    text NOT NULL CONSTRAINT ck_saved_research_language CHECK (language IN ('en', 'ar')),
    data_mode   data_mode NOT NULL,
    snapshot    jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_saved_research_user ON saved_research (user_id, created_at DESC);
-- The same reply is saved once per user.
CREATE UNIQUE INDEX uq_saved_research_message ON saved_research (user_id, message_id) WHERE message_id IS NOT NULL;

-- ================================================================== watchlists
CREATE TABLE watchlist_item (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    indicator_code  text NOT NULL REFERENCES indicator (code),
    area_code       text NOT NULL REFERENCES area (code),
    period_kind     text NOT NULL CONSTRAINT ck_watchlist_period_kind
                        CHECK (period_kind IN ('annual', 'year_to_date', 'quarterly', 'monthly', 'statement')),
    data_mode       data_mode NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_watchlist_item UNIQUE (user_id, indicator_code, area_code, period_kind, data_mode)
);

-- ================================================================== alerts
-- new_data: any newly published value of the watched series.
-- above / below: a newly published value beyond the threshold (in the series' unit).
CREATE TABLE alert_rule (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    watchlist_item_id  bigint NOT NULL REFERENCES watchlist_item (id) ON DELETE CASCADE,
    kind               text NOT NULL CONSTRAINT ck_alert_rule_kind CHECK (kind IN ('new_data', 'above', 'below')),
    threshold          numeric,
    CONSTRAINT ck_alert_rule_threshold CHECK ((kind = 'new_data') = (threshold IS NULL)),
    enabled            boolean NOT NULL DEFAULT true,
    channel            text NOT NULL DEFAULT 'in_app' CONSTRAINT ck_alert_rule_channel CHECK (channel IN ('in_app', 'email')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_triggered_at  timestamptz
);
CREATE INDEX ix_alert_rule_item ON alert_rule (watchlist_item_id) WHERE enabled;

CREATE TABLE alert_event (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id             bigint NOT NULL REFERENCES alert_rule (id) ON DELETE CASCADE,
    user_id             uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    dataset_version_id  uuid REFERENCES dataset_version (id) ON DELETE SET NULL,
    kind                text NOT NULL,
    indicator_code      text NOT NULL,
    area_code           text NOT NULL,
    value               numeric,                -- NULL when the source reports the value as missing
    unit                text,
    period_start        date NOT NULL,
    period_end          date NOT NULL,
    threshold           numeric,
    message_en          text NOT NULL,
    message_ar          text NOT NULL,
    delivery            text NOT NULL DEFAULT 'in_app'
                            CONSTRAINT ck_alert_event_delivery
                            CHECK (delivery IN ('in_app', 'email_pending', 'email_sent', 'email_failed', 'email_unavailable')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    read_at             timestamptz,
    -- One event per rule and published observation, however often evaluation runs.
    CONSTRAINT uq_alert_event UNIQUE (rule_id, dataset_version_id, period_start, period_end)
);
CREATE INDEX ix_alert_event_user ON alert_event (user_id, created_at DESC);
