-- 0019: the live study event log. While the assistant researches a question, each real step
-- is written here as one validated event (stage reached, source retrieved, search outcome,
-- validated dataset, partial failure, completion with findings and narration), so the person
-- asking can follow it as a stream and later return to the same study by replaying it.
--
-- Events belong to the request (and so to its user or guest session) and to its conversation:
-- deleting the conversation, the account or the guest session removes them. Payloads hold
-- what the reply itself holds (evidence, validated tables, findings); never credentials.

CREATE TABLE study_event (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id       bigint NOT NULL REFERENCES assistant_request (id) ON DELETE CASCADE,
    conversation_id  uuid REFERENCES assistant_conversation (id) ON DELETE CASCADE,
    -- The study is the request's idempotency key (the client's request id).
    study_id         uuid NOT NULL,
    seq              integer NOT NULL CHECK (seq >= 1),
    type             text NOT NULL CHECK (type IN (
                         'study.started', 'stage', 'search', 'evidence', 'dataset', 'warning',
                         'study.completed', 'study.cancelled', 'study.failed')),
    result_version   integer NOT NULL DEFAULT 0 CHECK (result_version >= 0),
    payload          jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_study_event_seq UNIQUE (request_id, seq)
);

CREATE INDEX ix_study_event_study ON study_event (study_id, seq);
