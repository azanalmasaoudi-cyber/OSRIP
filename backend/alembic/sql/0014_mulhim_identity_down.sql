-- Reverses 0014 without deleting messages: approved-profile replies become labelled non-AI
-- replies ('lookup') and cancelled ones 'unavailable', so the earlier status rule can be
-- restored. Profile version 1 becomes active again and version 2 is removed (the
-- immutability trigger is paused for this downgrade only).
UPDATE assistant_message SET status = 'lookup' WHERE status = 'profile';
UPDATE assistant_message SET status = 'unavailable' WHERE status = 'cancelled';
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_status;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_status CHECK (
    status IS NULL OR status IN ('answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup')
);

ALTER TABLE assistant_profile DISABLE TRIGGER trg_assistant_profile_immutable;
UPDATE assistant_profile SET status = 'retired', retired_at = now() WHERE status = 'active';
DELETE FROM assistant_profile WHERE version >= 2;
UPDATE assistant_profile SET status = 'active', activated_at = now(), retired_at = NULL WHERE version = 1;
ALTER TABLE assistant_profile ENABLE TRIGGER trg_assistant_profile_immutable;
