-- Reverses 0008. Phone-only accounts cannot exist without an e-mail address, so they
-- are removed; link_email tokens are removed with the purpose.
DELETE FROM auth_token WHERE purpose = 'link_email';
CREATE OR REPLACE FUNCTION auth_token_single_use() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.used_at IS NOT NULL THEN
        RAISE EXCEPTION 'auth token already used'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_auth_token_single_use';
    END IF;
    IF NEW.token_hash IS DISTINCT FROM OLD.token_hash OR NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose OR NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
        RAISE EXCEPTION 'auth token fields are immutable'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_auth_token_single_use';
    END IF;
    RETURN NEW;
END;
$$;
ALTER TABLE auth_token DROP CONSTRAINT IF EXISTS ck_auth_token_link_email;
ALTER TABLE auth_token DROP CONSTRAINT IF EXISTS ck_auth_token_purpose;
ALTER TABLE auth_token ADD CONSTRAINT ck_auth_token_purpose
    CHECK (purpose IN ('verify_email', 'reset_password', 'magic_link'));
ALTER TABLE auth_token DROP COLUMN IF EXISTS email;

DROP TABLE IF EXISTS phone_challenge;
DROP FUNCTION IF EXISTS phone_challenge_single_use();

DELETE FROM app_user WHERE email IS NULL AND NOT is_service_account;
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_has_identifier;
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_phone_verified;
DROP INDEX IF EXISTS uq_app_user_phone;
ALTER TABLE app_user DROP COLUMN IF EXISTS phone_verified_at;
ALTER TABLE app_user DROP COLUMN IF EXISTS phone_e164;
UPDATE app_user SET created_via = 'self_registration' WHERE created_via = 'phone';
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_created_via;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_created_via
    CHECK (created_via IN ('administrator', 'self_registration', 'google', 'microsoft', 'cli'));
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_email_normalized;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_email_normalized
    CHECK (email = lower(btrim(email)) AND email LIKE '_%@_%');
ALTER TABLE app_user ALTER COLUMN email SET NOT NULL;
