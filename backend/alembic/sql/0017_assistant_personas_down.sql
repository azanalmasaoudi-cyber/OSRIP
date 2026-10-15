-- Reverse 0017 without deleting messages or accounts: the persona choice and the persona of
-- each reply are removed with their columns (replies keep their text). Profile version 2
-- becomes active again and version 3 is removed (the immutability trigger is paused for this
-- downgrade only).

ALTER TABLE assistant_message DROP COLUMN persona;
ALTER TABLE app_user DROP COLUMN assistant_persona;

ALTER TABLE assistant_profile DISABLE TRIGGER trg_assistant_profile_immutable;
UPDATE assistant_profile SET status = 'retired', retired_at = now() WHERE status = 'active';
DELETE FROM assistant_profile WHERE version >= 3;
UPDATE assistant_profile SET status = 'active', activated_at = now(), retired_at = NULL WHERE version = 2;
ALTER TABLE assistant_profile ENABLE TRIGGER trg_assistant_profile_immutable;
