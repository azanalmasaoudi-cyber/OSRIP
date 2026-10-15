-- OSRIP migration 0008: registration and sign-in by phone (SMS verification), and
-- verified linking of an e-mail address to an existing account.

-- ================================================================== accounts
-- An account is identified by a verified e-mail address, a verified phone number, or
-- both. Phone-only accounts have no e-mail address and no password (they sign in with
-- an SMS code); they can add an e-mail address later, after proving they own it.
ALTER TABLE app_user ALTER COLUMN email DROP NOT NULL;
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_email_normalized;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_email_normalized
    CHECK (email IS NULL OR (email = lower(btrim(email)) AND email LIKE '_%@_%'));

-- E.164: "+", country code, subscriber number; 8 to 15 digits in total.
ALTER TABLE app_user ADD COLUMN phone_e164 text
    CONSTRAINT ck_app_user_phone_e164 CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$');
ALTER TABLE app_user ADD COLUMN phone_verified_at timestamptz;
CREATE UNIQUE INDEX uq_app_user_phone ON app_user (phone_e164) WHERE phone_e164 IS NOT NULL;
-- A number is stored on an account only once it has been verified.
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_phone_verified
    CHECK ((phone_e164 IS NULL) = (phone_verified_at IS NULL));
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_has_identifier
    CHECK (is_service_account OR email IS NOT NULL OR phone_e164 IS NOT NULL);

ALTER TABLE app_user DROP CONSTRAINT ck_app_user_created_via;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_created_via
    CHECK (created_via IN ('administrator', 'self_registration', 'google', 'microsoft', 'cli', 'phone'));

-- ================================================================== SMS challenges
-- One verification attempt series for one number. The code itself is never stored:
-- the provider holds it (provider_ref identifies the provider's verification).
-- The challenge id returned to the browser is opaque and says nothing about the code.
CREATE TABLE phone_challenge (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_e164    text NOT NULL CONSTRAINT ck_phone_challenge_phone CHECK (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    purpose       text NOT NULL CONSTRAINT ck_phone_challenge_purpose CHECK (purpose IN ('sign_in', 'link')),
    user_id       uuid REFERENCES app_user (id) ON DELETE CASCADE,
    provider      text NOT NULL,
    provider_ref  text NOT NULL,
    client_hash   char(64) NOT NULL,
    attempts      integer NOT NULL DEFAULT 0 CONSTRAINT ck_phone_challenge_attempts CHECK (attempts >= 0),
    max_attempts  integer NOT NULL CONSTRAINT ck_phone_challenge_max CHECK (max_attempts BETWEEN 1 AND 10),
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    consumed_at   timestamptz,
    CONSTRAINT ck_phone_challenge_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_phone_challenge_link_user CHECK (purpose <> 'link' OR user_id IS NOT NULL),
    CONSTRAINT ck_phone_challenge_attempt_cap CHECK (attempts <= max_attempts)
);
CREATE INDEX ix_phone_challenge_phone ON phone_challenge (phone_e164, created_at DESC);
CREATE INDEX ix_phone_challenge_client ON phone_challenge (client_hash, created_at DESC);

-- A consumed challenge can never be used again, and its identity fields never change.
CREATE FUNCTION phone_challenge_single_use() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.consumed_at IS NOT NULL THEN
        RAISE EXCEPTION 'phone challenge already used'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_phone_challenge_single_use';
    END IF;
    IF NEW.phone_e164 IS DISTINCT FROM OLD.phone_e164 OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.provider_ref IS DISTINCT FROM OLD.provider_ref
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.max_attempts IS DISTINCT FROM OLD.max_attempts
       OR NEW.attempts < OLD.attempts THEN
        RAISE EXCEPTION 'phone challenge fields are immutable'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_phone_challenge_single_use';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_phone_challenge_single_use
    BEFORE UPDATE ON phone_challenge
    FOR EACH ROW EXECUTE FUNCTION phone_challenge_single_use();

-- ================================================================== e-mail linking
-- A signed-in account (for example a phone-only one) adds an e-mail address: the
-- address is stored on the token and copied to the account only when the link sent to
-- that address is opened.
ALTER TABLE auth_token ADD COLUMN email text;
ALTER TABLE auth_token DROP CONSTRAINT ck_auth_token_purpose;
ALTER TABLE auth_token ADD CONSTRAINT ck_auth_token_purpose
    CHECK (purpose IN ('verify_email', 'reset_password', 'magic_link', 'link_email'));
ALTER TABLE auth_token ADD CONSTRAINT ck_auth_token_link_email
    CHECK ((purpose = 'link_email') = (email IS NOT NULL));

CREATE OR REPLACE FUNCTION auth_token_single_use() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.used_at IS NOT NULL THEN
        RAISE EXCEPTION 'auth token already used'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_auth_token_single_use';
    END IF;
    IF NEW.token_hash IS DISTINCT FROM OLD.token_hash OR NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
       OR NEW.email IS DISTINCT FROM OLD.email THEN
        RAISE EXCEPTION 'auth token fields are immutable'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_auth_token_single_use';
    END IF;
    RETURN NEW;
END;
$$;
