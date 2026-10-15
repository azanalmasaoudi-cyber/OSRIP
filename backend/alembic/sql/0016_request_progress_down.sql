-- Reverse 0016. Cancelled requests become 'released' (the earlier name for a request that
-- was not answered and not charged); the stored replies and messages are kept. The progress
-- trail and cancel time were added by 0016 and are removed with their columns.

UPDATE assistant_request SET state = 'released' WHERE state = 'cancelled';

ALTER TABLE assistant_request DROP CONSTRAINT ck_assistant_request_state;
ALTER TABLE assistant_request ADD CONSTRAINT ck_assistant_request_state
    CHECK (state IN ('reserved', 'completed', 'released'));

ALTER TABLE assistant_request
    DROP COLUMN cancel_requested_at,
    DROP COLUMN progress;
