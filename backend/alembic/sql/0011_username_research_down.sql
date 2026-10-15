DROP TABLE IF EXISTS research_candidate;
DELETE FROM user_permission_grant WHERE permission_code = 'research.review';
DELETE FROM role_permission WHERE permission_code = 'research.review';
DELETE FROM permission WHERE code = 'research.review';

ALTER TABLE app_user DROP COLUMN IF EXISTS password_change_required;
-- Accounts identified only by a username cannot exist without this migration.
DELETE FROM app_user WHERE email IS NULL AND phone_e164 IS NULL AND NOT is_service_account;
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_has_identifier;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_has_identifier
    CHECK (is_service_account OR email IS NOT NULL OR phone_e164 IS NOT NULL);
DROP INDEX IF EXISTS uq_app_user_username;
ALTER TABLE app_user DROP COLUMN IF EXISTS username;
