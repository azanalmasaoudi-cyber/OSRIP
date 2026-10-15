-- OSRIP migration 0006: self-service accounts (e-mail verification, password recovery,
-- magic links), external identities (Google, Microsoft), a development mail outbox,
-- and the evidence-grounded assistant (conversations, messages, usage for limits).

-- ================================================================== accounts
-- NULL = address not yet proven. Accounts created by administrators before this
-- migration were created by a trusted operator and count as verified.
ALTER TABLE app_user ADD COLUMN email_verified_at timestamptz;
UPDATE app_user SET email_verified_at = created_at WHERE NOT is_service_account;
-- Self-registered accounts record how they were created.
ALTER TABLE app_user ADD COLUMN created_via text NOT NULL DEFAULT 'administrator'
    CONSTRAINT ck_app_user_created_via CHECK (created_via IN ('administrator', 'self_registration', 'google', 'microsoft', 'cli'));

-- Single-use, expiring tokens sent by e-mail. Only SHA-256 digests are stored.
CREATE TABLE auth_token (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    purpose      text NOT NULL CONSTRAINT ck_auth_token_purpose
        CHECK (purpose IN ('verify_email', 'reset_password', 'magic_link')),
    token_hash   char(64) NOT NULL UNIQUE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    used_at      timestamptz,
    CONSTRAINT ck_auth_token_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_auth_token_used CHECK (used_at IS NULL OR used_at >= created_at)
);
CREATE INDEX ix_auth_token_user_purpose ON auth_token (user_id, purpose, created_at);

-- A token is spent exactly once; a used token can never be made usable again.
CREATE FUNCTION auth_token_single_use() RETURNS trigger
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
CREATE TRIGGER trg_auth_token_single_use
    BEFORE UPDATE ON auth_token
    FOR EACH ROW EXECUTE FUNCTION auth_token_single_use();

-- External identities. (provider, subject) is the identity; the e-mail is informational
-- and is never used to merge accounts.
CREATE TABLE external_identity (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    provider        text NOT NULL CONSTRAINT ck_external_identity_provider CHECK (provider IN ('google', 'microsoft')),
    subject         text NOT NULL,
    issuer          text NOT NULL,
    email           text,
    email_verified  boolean NOT NULL DEFAULT false,
    linked_at       timestamptz NOT NULL DEFAULT now(),
    last_used_at    timestamptz,
    CONSTRAINT uq_external_identity UNIQUE (provider, subject)
);
CREATE INDEX ix_external_identity_user ON external_identity (user_id);

-- OpenID Connect authorization requests in flight: state, nonce, PKCE verifier and a
-- browser-binding digest. Single use, short-lived.
CREATE TABLE oidc_request (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider        text NOT NULL CONSTRAINT ck_oidc_request_provider CHECK (provider IN ('google', 'microsoft')),
    state_hash      char(64) NOT NULL UNIQUE,
    browser_hash    char(64) NOT NULL,
    nonce           text NOT NULL,
    code_verifier   text NOT NULL,
    intent          text NOT NULL CONSTRAINT ck_oidc_request_intent CHECK (intent IN ('sign_in', 'link')),
    user_id         uuid REFERENCES app_user (id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    used_at         timestamptz,
    CONSTRAINT ck_oidc_request_link_user CHECK (intent <> 'link' OR user_id IS NOT NULL)
);

-- Development-only mail sink: messages are stored instead of sent. The SMTP backend
-- never writes message bodies here.
CREATE TABLE email_outbox (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_address  text NOT NULL,
    subject     text NOT NULL,
    body_text   text NOT NULL,
    purpose     text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ================================================================== permissions
INSERT INTO permission (code, description) VALUES
    ('assistant.use', 'Ask the evidence-grounded assistant about published statistics');
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('viewer', 'assistant.use'),
    ('analyst', 'assistant.use'),
    ('data_manager', 'assistant.use'),
    ('administrator', 'assistant.use');

-- ================================================================== assistant
CREATE TABLE assistant_conversation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    title       text NOT NULL,
    language    text NOT NULL CONSTRAINT ck_assistant_conversation_language CHECK (language IN ('en', 'ar')),
    data_mode   data_mode NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_assistant_conversation_user ON assistant_conversation (user_id, updated_at DESC);

CREATE TABLE assistant_message (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id  uuid NOT NULL REFERENCES assistant_conversation (id) ON DELETE CASCADE,
    role             text NOT NULL CONSTRAINT ck_assistant_message_role CHECK (role IN ('user', 'assistant')),
    content          text NOT NULL,
    -- answered | clarification | no_evidence | unverified | unavailable (assistant only)
    status           text CONSTRAINT ck_assistant_message_status
        CHECK (status IS NULL OR status IN ('answered', 'clarification', 'no_evidence', 'unverified', 'unavailable')),
    evidence         jsonb NOT NULL DEFAULT '[]',
    calculations     jsonb NOT NULL DEFAULT '[]',
    citations        jsonb NOT NULL DEFAULT '[]',
    suggestions      jsonb NOT NULL DEFAULT '[]',
    model            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_assistant_message_status_role CHECK ((role = 'assistant') = (status IS NOT NULL))
);
CREATE INDEX ix_assistant_message_conversation ON assistant_message (conversation_id, id);

-- Usage records for request limits. Kept when a conversation is deleted, and hold
-- no message text.
CREATE TABLE assistant_usage (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    outcome     text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_assistant_usage_user_time ON assistant_usage (user_id, created_at);
