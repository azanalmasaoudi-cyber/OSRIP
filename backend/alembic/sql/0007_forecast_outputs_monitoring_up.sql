-- OSRIP migration 0007: future estimates of forecast runs, and captured application errors.

-- Model estimates beyond the last observation, from the model selected by backtesting.
-- They are estimates, never observations: they live apart from `observation`.
CREATE TABLE forecast_output (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_run_id   uuid NOT NULL,
    data_mode         data_mode NOT NULL,
    model             text NOT NULL CONSTRAINT ck_forecast_output_model
        CHECK (model IN ('baseline_last_value', 'candidate_linear_trend', 'candidate_seasonal_naive')),
    step              integer NOT NULL CONSTRAINT ck_forecast_output_step CHECK (step >= 1),
    period_start      date NOT NULL,
    period_end        date NOT NULL,
    estimate          numeric NOT NULL,
    lower80           numeric,
    upper80           numeric,
    lower95           numeric,
    upper95           numeric,
    interval_method   text NOT NULL,
    CONSTRAINT fk_forecast_output_run FOREIGN KEY (analysis_run_id, data_mode)
        REFERENCES analysis_run (id, data_mode),
    CONSTRAINT ck_forecast_output_period CHECK (period_end >= period_start),
    CONSTRAINT ck_forecast_output_interval CHECK (
        (lower80 IS NULL) = (upper80 IS NULL) AND (lower95 IS NULL) = (upper95 IS NULL)
        AND (lower95 IS NULL OR (lower95 <= lower80 AND lower80 <= estimate AND estimate <= upper80 AND upper80 <= upper95))
    ),
    CONSTRAINT uq_forecast_output UNIQUE (analysis_run_id, step)
);

CREATE TRIGGER trg_forecast_output_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON forecast_output
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete();

-- The existing prediction table also accepts the seasonal-naive candidate.
ALTER TABLE forecast_prediction DROP CONSTRAINT ck_forecast_prediction_model;
ALTER TABLE forecast_prediction ADD CONSTRAINT ck_forecast_prediction_model
    CHECK (model IN ('baseline_last_value', 'candidate_linear_trend', 'candidate_seasonal_naive'));

-- Application errors (server exceptions and browser errors). No request bodies, no
-- cookies, no query strings, no user identifiers.
CREATE TABLE app_error (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    source       text NOT NULL CONSTRAINT ck_app_error_source CHECK (source IN ('server', 'client')),
    kind         text NOT NULL,
    message      text NOT NULL,
    location     text,
    request_id   text,
    fingerprint  char(64) NOT NULL,
    release      text
);
CREATE INDEX ix_app_error_time ON app_error (occurred_at DESC);
CREATE INDEX ix_app_error_fingerprint ON app_error (fingerprint, occurred_at DESC);
