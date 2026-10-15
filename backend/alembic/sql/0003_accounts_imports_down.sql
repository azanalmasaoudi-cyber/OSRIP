DROP TABLE IF EXISTS audit_event;
DROP TABLE IF EXISTS report_input;
DROP TABLE IF EXISTS report;
DROP TABLE IF EXISTS recommendation_review;
DROP TABLE IF EXISTS recommendation;
DROP TABLE IF EXISTS analysis_run_input;
DROP TABLE IF EXISTS analysis_run;
DROP FUNCTION IF EXISTS forbid_update_delete();
DROP TABLE IF EXISTS import_row;
DROP FUNCTION IF EXISTS import_row_frozen_after_approval();
DROP TABLE IF EXISTS import_job;
DROP TABLE IF EXISTS login_attempt;
DROP TABLE IF EXISTS user_session;
DROP TABLE IF EXISTS user_permission_grant;
DROP TABLE IF EXISTS user_role;
DROP TABLE IF EXISTS role_permission;
DROP TABLE IF EXISTS permission;
DROP TABLE IF EXISTS role;
ALTER TABLE source DROP CONSTRAINT IF EXISTS fk_source_created_by;
DROP TABLE IF EXISTS app_user;
DROP TYPE IF EXISTS report_visibility;
DROP TYPE IF EXISTS review_status;
DROP TYPE IF EXISTS analysis_status;
DROP TYPE IF EXISTS analysis_kind;
DROP TYPE IF EXISTS account_status;

ALTER TABLE dataset_version DROP COLUMN IF EXISTS superseded_at;
DROP INDEX IF EXISTS uq_dataset_version_source_checksum;
ALTER TABLE source DROP COLUMN IF EXISTS created_by;
ALTER TABLE source DROP CONSTRAINT IF EXISTS ck_source_verified_reuse;
ALTER TABLE source DROP CONSTRAINT IF EXISTS ck_source_verified_locator;
ALTER TABLE source DROP COLUMN IF EXISTS locator_kind;

-- Restore the 0001 domain check (no verified-side rules).
CREATE OR REPLACE FUNCTION observation_domain_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    ind  indicator%ROWTYPE;
    udim physical_dimension;
    fictional boolean;
BEGIN
    SELECT * INTO ind FROM indicator WHERE id = NEW.indicator_id;
    SELECT dimension INTO udim FROM unit WHERE id = NEW.unit_id;

    IF udim IS DISTINCT FROM ind.dimension THEN
        RAISE EXCEPTION 'unit dimension % does not match indicator % dimension %', udim, ind.code, ind.dimension
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_unit_dimension';
    END IF;
    IF ind.requires_commodity AND NEW.commodity_id IS NULL THEN
        RAISE EXCEPTION 'indicator % requires a commodity', ind.code
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_commodity_required';
    END IF;
    IF ind.requires_flow AND NEW.flow IS NULL THEN
        RAISE EXCEPTION 'indicator % requires a trade flow', ind.code
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_flow_required';
    END IF;
    IF NEW.partner_id IS NOT NULL AND NEW.data_mode = 'synthetic' THEN
        SELECT is_fictional INTO fictional FROM partner WHERE id = NEW.partner_id;
        IF NOT fictional THEN
            RAISE EXCEPTION 'synthetic observations may reference fictional partners only'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_synthetic_partner';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DELETE FROM commodity WHERE code = 'SYNTH_COMMODITY';
ALTER TABLE commodity DROP COLUMN IF EXISTS synthetic_only;

ALTER TABLE observation DROP CONSTRAINT IF EXISTS ck_observation_frequency_period;
ALTER TABLE observation DROP COLUMN IF EXISTS valuation_basis;
ALTER TABLE observation DROP COLUMN IF EXISTS frequency;
DROP TYPE IF EXISTS observation_frequency;
