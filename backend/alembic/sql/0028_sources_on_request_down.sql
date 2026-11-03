-- 0028 down: the replies listing sources are removed with the status.
DELETE FROM assistant_message WHERE status = 'sources';
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN (
        'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup',
        'profile', 'cancelled', 'data_report'
    )
);
