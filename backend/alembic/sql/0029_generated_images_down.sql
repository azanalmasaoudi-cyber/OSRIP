-- 0029 down: the generated images and their metering rows go with the capability.
DELETE FROM provider_call WHERE capability IN ('image', 'test_image');
ALTER TABLE provider_call DROP CONSTRAINT provider_call_capability_check;
ALTER TABLE provider_call ADD CONSTRAINT provider_call_capability_check CHECK (
    capability IN ('answer', 'search', 'retrieve', 'test_answer', 'test_search', 'test_retrieve')
);
DROP TABLE generated_image;
-- Quick answers were internet answers: kept, as Research answers.
UPDATE assistant_message SET mode = 'research' WHERE mode = 'quick';
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_mode;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_mode
    CHECK (mode IS NULL OR mode IN ('ask', 'analyze', 'research', 'compare', 'scenario'));
