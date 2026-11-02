-- OSRIP migration 0025: public registration by username and password, and recovery codes.
-- An account registered with a username has no verified e-mail address or phone number,
-- so a lost password is recovered with a one-time recovery code shown once at
-- registration (or later from the account page), or by an administrator's reset to a
-- temporary password that must be changed. Only an Argon2id hash of the code is kept.
ALTER TABLE app_user ADD COLUMN recovery_code_hash text
    CONSTRAINT ck_app_user_recovery_code_hash
    CHECK (recovery_code_hash IS NULL OR recovery_code_hash LIKE '$argon2id$%');
ALTER TABLE app_user ADD COLUMN recovery_code_created_at timestamptz;
