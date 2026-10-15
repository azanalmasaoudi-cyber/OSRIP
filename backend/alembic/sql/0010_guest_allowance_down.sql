-- Reverses 0010. Guest conversations (and their messages) are removed; account
-- conversations are kept.
DROP TABLE IF EXISTS assistant_request;

DELETE FROM assistant_conversation WHERE guest_session_id IS NOT NULL;
ALTER TABLE assistant_conversation DROP CONSTRAINT IF EXISTS ck_assistant_conversation_owner;
DROP INDEX IF EXISTS ix_assistant_conversation_guest;
ALTER TABLE assistant_conversation DROP COLUMN IF EXISTS guest_session_id;
ALTER TABLE assistant_conversation ALTER COLUMN user_id SET NOT NULL;

DELETE FROM assistant_message WHERE status = 'lookup';
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN ('answered', 'clarification', 'no_evidence', 'unverified', 'unavailable')
);

DROP TABLE IF EXISTS guest_session;
