-- Reverses 0021 without deleting messages: data-based reports become 'unavailable' replies
-- (their text and evidence are kept), so the earlier status rule can be restored. Study jobs,
-- their retrieved documents and the report schedules are removed with their tables; page
-- retrieval calls are removed from the provider call log (a log only).
DROP TABLE research_document;
DROP TABLE research_job;
DROP TABLE report_schedule;

DELETE FROM provider_call WHERE capability IN ('retrieve', 'test_retrieve');
ALTER TABLE provider_call DROP COLUMN credits;
ALTER TABLE provider_call DROP CONSTRAINT provider_call_capability_check;
ALTER TABLE provider_call ADD CONSTRAINT provider_call_capability_check CHECK (
    capability IN ('answer', 'search', 'test_answer', 'test_search')
);

UPDATE assistant_message SET status = 'unavailable' WHERE status = 'data_report';
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN (
        'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup',
        'profile', 'cancelled'
    )
);
