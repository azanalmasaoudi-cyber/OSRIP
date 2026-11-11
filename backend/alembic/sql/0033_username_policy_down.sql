-- Reverts 0033. The old rule comes back NOT VALID: Arabic or one- and two-letter usernames
-- created under 0033 stay as they are (they are not renamed), while new ones must follow it.
DROP TRIGGER trg_app_user_username_policy ON app_user;
DROP FUNCTION app_user_username_policy();
DROP INDEX uq_app_user_username_key;
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_username_key;
ALTER TABLE app_user DROP COLUMN username_key;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_username
    CHECK (username IS NULL OR username ~ '^[A-Za-z][A-Za-z0-9_.-]{2,31}$') NOT VALID;
