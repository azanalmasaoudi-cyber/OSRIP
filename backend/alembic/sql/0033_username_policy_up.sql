-- OSRIP migration 0033: usernames of 1 to 10 Arabic or English letters and digits, and a
-- comparison key for uniqueness and sign-in (app/services/usernames.py applies the same rule).
--
-- Usernames that accounts already have are kept exactly as they are and keep working: the
-- rule is checked by a trigger only when a username is set or changed, never on other
-- updates of an existing account (a password change, a role, the last sign-in). No account
-- is renamed and no column is removed; e-mail addresses and phone numbers stay as records.

-- The old rule (3-32 English letters, digits, '.', '_' or '-') moves into the trigger.
ALTER TABLE app_user DROP CONSTRAINT ck_app_user_username;

-- The key: lower case, with Arabic look-alike letters folded (set by the application). For
-- the existing English usernames it is simply lower(username).
ALTER TABLE app_user ADD COLUMN username_key text;
UPDATE app_user SET username_key = lower(username) WHERE username IS NOT NULL;
ALTER TABLE app_user ADD CONSTRAINT ck_app_user_username_key
    CHECK ((username IS NULL) = (username_key IS NULL));
CREATE UNIQUE INDEX uq_app_user_username_key ON app_user (username_key)
    WHERE username_key IS NOT NULL;

CREATE FUNCTION app_user_username_policy() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.username IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.username IS DISTINCT FROM OLD.username) THEN
        IF char_length(NEW.username) NOT BETWEEN 1 AND 10
           OR NEW.username !~ '^([A-Za-z][A-Za-z0-9_.-]*|[ء-غف-يٮٯٱ-ۓ][ء-غف-يٮٯٱ-ۓ0-9_.-]*)$'
        THEN
            RAISE EXCEPTION 'username breaks the username rule (1-10 Arabic or English letters and digits)'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_app_user_username';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_app_user_username_policy
    BEFORE INSERT OR UPDATE OF username ON app_user
    FOR EACH ROW EXECUTE FUNCTION app_user_username_policy();
