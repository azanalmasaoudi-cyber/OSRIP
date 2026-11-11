-- Reverse 0030: profile version 3 (Al Mulhim and Ilham) becomes active again and version 4 is
-- removed (the immutability trigger is paused for this downgrade only). No message or account
-- is changed.

ALTER TABLE assistant_profile DISABLE TRIGGER trg_assistant_profile_immutable;
UPDATE assistant_profile SET status = 'retired', retired_at = now() WHERE status = 'active';
DELETE FROM assistant_profile WHERE version >= 4;
UPDATE assistant_profile SET status = 'active', activated_at = now(), retired_at = NULL WHERE version = 3;
ALTER TABLE assistant_profile ENABLE TRIGGER trg_assistant_profile_immutable;
