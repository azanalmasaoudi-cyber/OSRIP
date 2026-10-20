-- 0020 down: stored shortage and surplus analyses are removed (the earlier schema cannot hold
-- them), then the original constraints are restored.

DELETE FROM study_run WHERE kind = 'supply_balance';

ALTER TABLE study_run DROP CONSTRAINT study_run_schema_version_check;
ALTER TABLE study_run ADD CONSTRAINT study_run_schema_version_check CHECK (
    schema_version = 'osrip.study/1');

ALTER TABLE study_run DROP CONSTRAINT study_run_kind_check;
ALTER TABLE study_run ADD CONSTRAINT study_run_kind_check CHECK (kind IN (
    'trend', 'growth', 'compare_regions', 'seasonal_profile',
    'import_dependence', 'partner_concentration', 'data_quality',
    'scenario', 'forecast_eligibility', 'programme_assessment'));
