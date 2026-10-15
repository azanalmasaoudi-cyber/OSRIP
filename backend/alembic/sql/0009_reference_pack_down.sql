-- Reverses 0009. Observations that only 0009 can represent (statements), and every
-- observation of the reference-pack indicators, units, partners and areas, are removed
-- with their dataset versions' reference rows. The enum values stay (PostgreSQL cannot
-- drop them) but nothing uses them.
ALTER TABLE observation DISABLE TRIGGER trg_observation_immutable;
DELETE FROM observation o
USING indicator i
WHERE o.indicator_id = i.id AND (i.parent_code IS NOT NULL OR i.code IN (
    'ELEC_GROSS_GENERATION', 'ELEC_NET_GENERATION', 'ELEC_DISTRIBUTION', 'ELEC_CONNECTIONS', 'WATER_DISTRIBUTION',
    'WATER_CONNECTIONS', 'AGRI_CROP_PRODUCTION', 'AGRI_CULTIVATED_AREA', 'LIVESTOCK_CATTLE', 'LIVESTOCK_CAMELS',
    'LIVESTOCK_SHEEP', 'LIVESTOCK_GOATS', 'FISH_CAPTURE_LANDINGS', 'FISH_VALUE_INCL_AQUACULTURE', 'AGRI_FISH_PRODUCTION_TOTAL',
    'SELF_SUFFICIENCY_FISH', 'SELF_SUFFICIENCY_DATES', 'SELF_SUFFICIENCY_VEGETABLES', 'SELF_SUFFICIENCY_EGGS',
    'SELF_SUFFICIENCY_MILK', 'SELF_SUFFICIENCY_WHITE_MEAT', 'SELF_SUFFICIENCY_RED_MEAT', 'SELF_SUFFICIENCY_FRUIT_EXCL_DATES',
    'TRADE_MERCH_EXPORTS', 'TRADE_MERCH_IMPORTS', 'TRADE_BALANCE_REPORTED'));
DELETE FROM observation WHERE frequency::text = 'statement' OR record_ref IS NOT NULL;
ALTER TABLE observation ENABLE TRIGGER trg_observation_immutable;

DROP TABLE IF EXISTS data_quality_note;
DROP TABLE IF EXISTS reference_pack_source;
DROP TABLE IF EXISTS reference_pack;

DELETE FROM indicator WHERE parent_code IS NOT NULL;
DELETE FROM indicator WHERE code IN (
    'ELEC_GROSS_GENERATION', 'ELEC_NET_GENERATION', 'ELEC_DISTRIBUTION', 'ELEC_CONNECTIONS', 'WATER_DISTRIBUTION',
    'WATER_CONNECTIONS', 'AGRI_CROP_PRODUCTION', 'AGRI_CULTIVATED_AREA', 'LIVESTOCK_CATTLE', 'LIVESTOCK_CAMELS',
    'LIVESTOCK_SHEEP', 'LIVESTOCK_GOATS', 'FISH_CAPTURE_LANDINGS', 'FISH_VALUE_INCL_AQUACULTURE', 'AGRI_FISH_PRODUCTION_TOTAL',
    'SELF_SUFFICIENCY_FISH', 'SELF_SUFFICIENCY_DATES', 'SELF_SUFFICIENCY_VEGETABLES', 'SELF_SUFFICIENCY_EGGS',
    'SELF_SUFFICIENCY_MILK', 'SELF_SUFFICIENCY_WHITE_MEAT', 'SELF_SUFFICIENCY_RED_MEAT', 'SELF_SUFFICIENCY_FRUIT_EXCL_DATES',
    'TRADE_MERCH_EXPORTS', 'TRADE_MERCH_IMPORTS', 'TRADE_BALANCE_REPORTED');
ALTER TABLE indicator DROP COLUMN IF EXISTS display_unit_code;
ALTER TABLE indicator DROP COLUMN IF EXISTS parent_code;

DROP TABLE IF EXISTS unit_conversion;
DROP FUNCTION IF EXISTS unit_conversion_same_dimension();
DELETE FROM unit WHERE code IN ('thousand_m3', 'thousand_tonnes', 'million_tonnes', 'thousand_OMR', 'million_OMR',
    'thousand_connections', 'thousand_head', 'feddan');
DELETE FROM partner WHERE code IN ('ARE', 'SAU', 'IND', 'USA', 'KOR', 'IRN', 'HKG', 'GBR', 'CHN', 'TUR');

DROP TABLE IF EXISTS area_group_member;
DELETE FROM area WHERE level::text = 'reporting_group';
ALTER TABLE area DROP COLUMN IF EXISTS members_stated;

ALTER TABLE source DROP COLUMN IF EXISTS source_role;
ALTER TABLE source DROP COLUMN IF EXISTS source_code;
ALTER TABLE source DROP CONSTRAINT ck_source_verified_locator;
ALTER TABLE source ADD CONSTRAINT ck_source_verified_locator
    CHECK (data_mode <> 'verified_source' OR locator_kind IN ('direct_file', 'statistical_table'));
ALTER TABLE source DROP CONSTRAINT ck_source_locator_kind;
ALTER TABLE source ADD CONSTRAINT ck_source_locator_kind
    CHECK (locator_kind IN ('direct_file', 'statistical_table', 'catalogue_page'));

DROP INDEX IF EXISTS ix_observation_record_ref;
ALTER TABLE observation DROP CONSTRAINT ck_observation_frequency_period;
ALTER TABLE observation ADD CONSTRAINT ck_observation_frequency_period CHECK (
    extract(day FROM period_start) = 1
    AND period_end <= (period_start + CASE frequency
            WHEN 'annual' THEN interval '12 months'
            WHEN 'quarterly' THEN interval '3 months'
            ELSE interval '1 month' END - interval '1 day')::date
    AND (NOT period_complete OR period_end = (period_start + CASE frequency
            WHEN 'annual' THEN interval '12 months'
            WHEN 'quarterly' THEN interval '3 months'
            ELSE interval '1 month' END - interval '1 day')::date)
);
ALTER TABLE observation DROP COLUMN IF EXISTS note;
ALTER TABLE observation DROP COLUMN IF EXISTS statement_date;
ALTER TABLE observation DROP COLUMN IF EXISTS value_operator;
ALTER TABLE observation DROP COLUMN IF EXISTS revision_status;
ALTER TABLE observation DROP COLUMN IF EXISTS source_locator;
ALTER TABLE observation DROP COLUMN IF EXISTS record_ref;
