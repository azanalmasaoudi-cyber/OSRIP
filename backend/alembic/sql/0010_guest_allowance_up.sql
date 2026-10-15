-- Five-answer guest allowance, idempotent assistant requests and the non-AI lookup reply
-- (booklet 3.35, Table 3.8). Anonymous identity is a random cookie value, stored only as
-- a SHA-256 digest; no fingerprinting data is kept.

CREATE TABLE guest_session (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash        text NOT NULL UNIQUE,        -- digest of the HttpOnly cookie value
    csrf_hash         text NOT NULL,               -- digest of the guest CSRF token
    policy_version    integer NOT NULL DEFAULT 1,
    answer_limit      integer NOT NULL CONSTRAINT ck_guest_session_limit CHECK (answer_limit >= 0),
    answers_used      integer NOT NULL DEFAULT 0 CONSTRAINT ck_guest_session_used CHECK (answers_used >= 0),
    answers_reserved  integer NOT NULL DEFAULT 0 CONSTRAINT ck_guest_session_reserved CHECK (answers_reserved >= 0),
    -- The database itself refuses more completed plus in-flight answers than the limit,
    -- so no interleaving of concurrent requests can exceed it.
    CONSTRAINT ck_guest_session_allowance CHECK (answers_used + answers_reserved <= answer_limit),
    client_hash       text,                        -- keyed digest of the creating address (abuse limits only)
    created_at        timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    linked_user_id    uuid REFERENCES app_user (id) ON DELETE SET NULL,
    linked_at         timestamptz,
    CONSTRAINT ck_guest_session_link CHECK ((linked_user_id IS NULL) = (linked_at IS NULL))
);
CREATE INDEX ix_guest_session_client ON guest_session (client_hash, created_at);
CREATE INDEX ix_guest_session_expires ON guest_session (expires_at);

-- A conversation belongs to exactly one account or one guest session.
ALTER TABLE assistant_conversation ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE assistant_conversation
    ADD COLUMN guest_session_id uuid REFERENCES guest_session (id) ON DELETE CASCADE;
ALTER TABLE assistant_conversation ADD CONSTRAINT ck_assistant_conversation_owner
    CHECK ((user_id IS NULL) <> (guest_session_id IS NULL));
CREATE INDEX ix_assistant_conversation_guest
    ON assistant_conversation (guest_session_id, updated_at DESC) WHERE guest_session_id IS NOT NULL;

-- 'lookup': the labelled non-AI fallback that lists published records when no provider
-- is configured. It never counts as an AI answer.
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN ('answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup')
);

-- One row per logical question (idempotency key). A reservation holds one allowance slot
-- while the provider runs; completion charges it, a failure releases it, and a replay
-- of a completed key returns the stored reply without another charge.
CREATE TABLE assistant_request (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guest_session_id     uuid REFERENCES guest_session (id) ON DELETE CASCADE,
    user_id              uuid REFERENCES app_user (id) ON DELETE CASCADE,
    CONSTRAINT ck_assistant_request_owner CHECK ((guest_session_id IS NULL) <> (user_id IS NULL)),
    idempotency_key      uuid NOT NULL,
    question_digest      text NOT NULL,            -- detects a key reused for another question
    language             text NOT NULL CONSTRAINT ck_assistant_request_language CHECK (language IN ('en', 'ar')),
    state                text NOT NULL CONSTRAINT ck_assistant_request_state
                             CHECK (state IN ('reserved', 'completed', 'released')),
    charged              boolean NOT NULL DEFAULT false,
    outcome              text,
    conversation_id      uuid REFERENCES assistant_conversation (id) ON DELETE SET NULL,
    response_message_id  bigint REFERENCES assistant_message (id) ON DELETE SET NULL,
    attempts             integer NOT NULL DEFAULT 1,
    reserved_until       timestamptz NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    completed_at         timestamptz,
    CONSTRAINT ck_assistant_request_charge CHECK (NOT charged OR state = 'completed')
);
CREATE UNIQUE INDEX ux_assistant_request_guest_key
    ON assistant_request (guest_session_id, idempotency_key) WHERE guest_session_id IS NOT NULL;
CREATE UNIQUE INDEX ux_assistant_request_user_key
    ON assistant_request (user_id, idempotency_key) WHERE user_id IS NOT NULL;
CREATE INDEX ix_assistant_request_reserved ON assistant_request (reserved_until) WHERE state = 'reserved';
CREATE INDEX ix_assistant_request_user_time ON assistant_request (user_id, created_at) WHERE user_id IS NOT NULL;
