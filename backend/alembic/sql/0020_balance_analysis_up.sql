-- 0020: shortage and surplus analyses are stored as study runs of kind 'supply_balance', each
-- with its own document schema (osrip.balance/1). Every other kind keeps osrip.study/1.

ALTER TABLE study_run DROP CONSTRAINT study_run_kind_check;
ALTER TABLE study_run ADD CONSTRAINT study_run_kind_check CHECK (kind IN (
    'trend', 'growth', 'compare_regions', 'seasonal_profile',
    'import_dependence', 'partner_concentration', 'data_quality',
    'scenario', 'forecast_eligibility', 'programme_assessment', 'supply_balance'));

ALTER TABLE study_run DROP CONSTRAINT study_run_schema_version_check;
ALTER TABLE study_run ADD CONSTRAINT study_run_schema_version_check CHECK (
    (kind = 'supply_balance' AND schema_version = 'osrip.balance/1')
    OR (kind <> 'supply_balance' AND schema_version = 'osrip.study/1'));
