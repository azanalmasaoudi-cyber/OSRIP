-- 0031: the answer as it is written. Checked sentences of the answer are written to the live
-- study as 'answer.segment' events while the model writes (assistant/streaming.py), and
-- 'answer.reset' when an attempt is replaced, so the conversation shows the text as it arrives.
-- The stored reply, checked as a whole, still replaces the streamed text at the end.

ALTER TABLE study_event DROP CONSTRAINT study_event_type_check;
ALTER TABLE study_event ADD CONSTRAINT study_event_type_check CHECK (type IN (
    'study.started', 'stage', 'search', 'evidence', 'dataset', 'warning',
    'answer.segment', 'answer.reset',
    'study.completed', 'study.cancelled', 'study.failed'
));
