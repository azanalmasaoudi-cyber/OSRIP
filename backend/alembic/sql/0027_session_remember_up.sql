-- Remember me: a session the person chose to keep on this device. Its cookie persists and
-- the server keeps it for session_remember_days (default 14) instead of 8 hours with a
-- 30-minute idle limit. Existing sessions are not persistent.
ALTER TABLE user_session ADD COLUMN persistent boolean NOT NULL DEFAULT false;
