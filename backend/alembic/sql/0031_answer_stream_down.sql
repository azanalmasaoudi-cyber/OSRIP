-- 0031 down: the streamed answer segments go (the stored replies keep their text).
DELETE FROM study_event WHERE type IN ('answer.segment', 'answer.reset');
ALTER TABLE study_event DROP CONSTRAINT study_event_type_check;
ALTER TABLE study_event ADD CONSTRAINT study_event_type_check CHECK (type IN (
    'study.started', 'stage', 'search', 'evidence', 'dataset', 'warning',
    'study.completed', 'study.cancelled', 'study.failed'
));
