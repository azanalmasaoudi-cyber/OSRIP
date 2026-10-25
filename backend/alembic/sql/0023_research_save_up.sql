-- 0023: research that reads original sources and saves verified figures.
--
-- 1. research_search: every web search made through the configured route (for example
--    DeepSeek Search), with the results it returned. It is the search log and the cache: the
--    same query is answered from here for OSRIP_RESEARCH_CACHE_HOURS, and when a search fails
--    the last successful results are shown with their own date, never as newly retrieved.
-- 2. research_document: documents read in a conversation or a data update, not only in a
--    study (job_id may be NULL), with the bounded text that was read (text_content) so a
--    saved figure can be checked against its document again, and how it was read
--    (retriever: deepseek, direct, firecrawl).
-- 3. research_candidate: the observation proposed from a read document, mapped to platform
--    codes (indicator, area, unit, kind of period), the backend validation's result and the
--    history of decisions. Statuses: pending (waits for a reviewer), approved (saved by
--    validation or a reviewer, with the observation and dataset version it became),
--    duplicate (already published), conflict (differs from a published figure: never written
--    over, waits for a reviewer), rejected, accepted (reviewed before 0023, not saved).
-- 4. research_job.kind and report_schedule.kind: 'study' (the existing studies) or
--    'data_update' (a background run that searches, reads and saves verified figures).
-- 5. research.submit: who may submit figures for validation (analysts, data managers and
--    administrators, or a per-user grant). Guests never can.

CREATE TABLE research_search (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider      text NOT NULL CHECK (provider ~ '^[a-z0-9-]{1,40}$'),
    query         text NOT NULL CHECK (length(query) BETWEEN 1 AND 300),
    language      text NOT NULL CHECK (language IN ('en', 'ar')),
    status        text NOT NULL CHECK (status IN ('ok', 'no_results', 'failed')),
    error         text CHECK (error IS NULL OR length(error) <= 200),
    results       jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(results) = 'array'),
    result_count  integer NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    job_id        uuid REFERENCES research_job (id) ON DELETE SET NULL,
    retrieved_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_research_search_cache ON research_search (provider, language, query, retrieved_at DESC);

ALTER TABLE research_document ALTER COLUMN job_id DROP NOT NULL;
ALTER TABLE research_document DROP CONSTRAINT research_document_retriever_check;
ALTER TABLE research_document ADD CONSTRAINT research_document_retriever_check
    CHECK (retriever IN ('firecrawl', 'direct', 'deepseek', 'fake'));
ALTER TABLE research_document ADD COLUMN text_content text
    CHECK (text_content IS NULL OR length(text_content) <= 300000);

ALTER TABLE research_job ADD COLUMN kind text NOT NULL DEFAULT 'study'
    CHECK (kind IN ('study', 'data_update'));
ALTER TABLE report_schedule ADD COLUMN kind text NOT NULL DEFAULT 'study'
    CHECK (kind IN ('study', 'data_update'));

ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_status;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_status CHECK (status IN (
    'pending', 'approved', 'duplicate', 'conflict', 'rejected', 'accepted'));
-- Decided rows carry who and when; pending and conflict rows wait for a reviewer.
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_review;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_review
    CHECK ((status IN ('pending', 'conflict')) = (reviewed_at IS NULL));
ALTER TABLE research_candidate
    ADD COLUMN job_id              uuid REFERENCES research_job (id) ON DELETE SET NULL,
    ADD COLUMN document_id         uuid REFERENCES research_document (id) ON DELETE SET NULL,
    ADD COLUMN area_code           text REFERENCES area (code),
    ADD COLUMN unit_code           text REFERENCES unit (code),
    ADD COLUMN period_kind         text CHECK (period_kind IS NULL OR period_kind IN (
                                       'monthly', 'quarterly', 'annual', 'year_to_date')),
    -- The scale the source states for the value (e.g. "million"), kept as written.
    ADD COLUMN scale               text CHECK (scale IS NULL OR scale IN (
                                       'one', 'thousand', 'million', 'billion')),
    ADD COLUMN validation          jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN history             jsonb NOT NULL DEFAULT '[]'::jsonb
                                       CHECK (jsonb_typeof(history) = 'array'),
    ADD COLUMN decided_by          text CHECK (decided_by IS NULL OR decided_by IN (
                                       'validation', 'reviewer')),
    ADD COLUMN import_job_id       uuid REFERENCES import_job (id) ON DELETE SET NULL,
    ADD COLUMN dataset_version_id  uuid REFERENCES dataset_version (id),
    ADD COLUMN observation_id      uuid REFERENCES observation (id);
-- "Saved" only with the published observation it became.
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_saved CHECK (
    status <> 'approved'
    OR (observation_id IS NOT NULL AND dataset_version_id IS NOT NULL AND decided_by IS NOT NULL));
-- The same figure for the same series, period and document is submitted once (idempotent).
CREATE UNIQUE INDEX uq_research_candidate_observation ON research_candidate (
    source_url, indicator_code, area_code, period_kind, period_start, period_end, value)
    WHERE indicator_code IS NOT NULL AND area_code IS NOT NULL;
CREATE INDEX ix_research_candidate_job ON research_candidate (job_id) WHERE job_id IS NOT NULL;
CREATE INDEX ix_research_candidate_series ON research_candidate (
    indicator_code, area_code, period_start) WHERE indicator_code IS NOT NULL;

INSERT INTO permission (code, description) VALUES
    ('research.submit', 'Submit figures read from official documents for validation and saving');
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('analyst', 'research.submit'),
    ('data_manager', 'research.submit'),
    ('administrator', 'research.submit');
