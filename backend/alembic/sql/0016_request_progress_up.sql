-- Visible progress and cancellation for one assistant request (booklet 3.33, 3.35).
-- progress: the stages actually reached, in order ([{"stage", "at", "detail"?}]), written
-- while the answer is prepared so the person asking can see what is happening.
-- cancel_requested_at: set when the person stops the question; the answer loop checks it
-- between steps. A cancelled request is never charged.

ALTER TABLE assistant_request
    ADD COLUMN progress jsonb NOT NULL DEFAULT '[]'::jsonb
        CONSTRAINT ck_assistant_request_progress CHECK (jsonb_typeof(progress) = 'array'),
    ADD COLUMN cancel_requested_at timestamptz;

ALTER TABLE assistant_request DROP CONSTRAINT ck_assistant_request_state;
ALTER TABLE assistant_request ADD CONSTRAINT ck_assistant_request_state
    CHECK (state IN ('reserved', 'completed', 'released', 'cancelled'));
