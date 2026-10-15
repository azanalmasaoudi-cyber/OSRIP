DROP TABLE IF EXISTS app_error;
DROP TABLE IF EXISTS forecast_output;
ALTER TABLE forecast_prediction DROP CONSTRAINT IF EXISTS ck_forecast_prediction_model;
ALTER TABLE forecast_prediction ADD CONSTRAINT ck_forecast_prediction_model
    CHECK (model IN ('baseline_last_value', 'candidate_linear_trend'));
