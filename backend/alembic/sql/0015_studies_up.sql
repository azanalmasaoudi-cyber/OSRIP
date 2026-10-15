-- 0015: stored study runs (booklet 3.31 analysis_runs / study_results). Each row keeps the
-- validated parameters and the full study result with its SHA-256, so the same table,
-- chart and export can be shown again and the run reproduced against current data.
-- Studies contain only approved, published observations and calculations.

CREATE TABLE study_run (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind              text NOT NULL CHECK (kind IN (
                          'trend', 'growth', 'compare_regions', 'seasonal_profile',
                          'import_dependence', 'partner_concentration', 'data_quality',
                          'scenario', 'forecast_eligibility', 'programme_assessment')),
    schema_version    text NOT NULL CHECK (schema_version = 'osrip.study/1'),
    params            jsonb NOT NULL CHECK (jsonb_typeof(params) = 'object'),
    data_mode         text NOT NULL CHECK (data_mode IN ('verified_source', 'synthetic')),
    dataset_versions  text[] NOT NULL DEFAULT '{}',
    result            jsonb NOT NULL CHECK (
                          jsonb_typeof(result) = 'object'
                          AND result ->> 'kind' = kind
                          AND result ->> 'data_mode' = data_mode),
    result_sha256     text NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
    user_id           uuid REFERENCES app_user (id) ON DELETE CASCADE,
    guest_session_id  uuid REFERENCES guest_session (id) ON DELETE CASCADE,
    message_id        bigint REFERENCES assistant_message (id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_study_run_user ON study_run (user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX ix_study_run_message ON study_run (message_id) WHERE message_id IS NOT NULL;
