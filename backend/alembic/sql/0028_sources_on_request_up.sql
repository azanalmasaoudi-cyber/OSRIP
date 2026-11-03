-- 0028: sources on request. Answers no longer list their sources; asking for them ("Show
-- sources", "اعرض المصادر") gets a reply listing the previous answer's sources from its stored
-- evidence (status 'sources': no model call, never charged).

ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN (
        'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup',
        'profile', 'cancelled', 'data_report', 'sources'
    )
);
