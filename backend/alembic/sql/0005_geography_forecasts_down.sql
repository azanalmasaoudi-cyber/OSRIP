-- Reverts 0005. Fails (as it should) if observations reference sub-national areas.
DROP INDEX IF EXISTS ix_observation_area;
DROP INDEX IF EXISTS ix_area_parent;
DROP TABLE IF EXISTS forecast_prediction;
DROP TABLE IF EXISTS area_registry_verification;
DROP TABLE IF EXISTS area_reference;
DROP TRIGGER IF EXISTS trg_area_hierarchy ON area;
DROP FUNCTION IF EXISTS area_hierarchy_check();
DELETE FROM area WHERE level = 'wilayat' AND code_authority = 'osrip' AND verified_on IS NOT NULL;
DELETE FROM area WHERE level = 'governorate' AND code_authority = 'iso_3166_2';
ALTER TABLE area DROP CONSTRAINT IF EXISTS ck_area_admin_level_is_verified;
ALTER TABLE area DROP CONSTRAINT IF EXISTS ck_area_iso_code_matches;
ALTER TABLE area DROP COLUMN IF EXISTS registry_note_ar;
ALTER TABLE area DROP COLUMN IF EXISTS registry_note_en;
ALTER TABLE area DROP COLUMN IF EXISTS verified_on;
ALTER TABLE area DROP COLUMN IF EXISTS code_authority;
ALTER TABLE area DROP COLUMN IF EXISTS iso_3166_2;
DROP TABLE IF EXISTS geo_reference;
