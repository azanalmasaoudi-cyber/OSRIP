-- 0014: replies from Al Mulhim's approved profile (status 'profile': greetings and questions
-- about the assistant, never charged) and requests that the user cancelled ('cancelled').
-- Profile version 2 (short hello and thanks replies) is published by the migration script.

ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN (
        'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup',
        'profile', 'cancelled'
    )
);
