-- Reverses 0023. Figures already saved stay published (they are ordinary imports); their
-- candidates return to the earlier statuses: approved -> accepted, conflict -> pending.
-- Documents read outside a study and the search log are removed with what refers to them.
DELETE FROM role_permission WHERE permission_code = 'research.submit';
DELETE FROM user_permission_grant WHERE permission_code = 'research.submit';
DELETE FROM permission WHERE code = 'research.submit';

DROP INDEX ix_research_candidate_series;
DROP INDEX ix_research_candidate_job;
DROP INDEX uq_research_candidate_observation;
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_saved;
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_review;
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_status;
UPDATE research_candidate SET status = 'accepted' WHERE status = 'approved';
UPDATE research_candidate SET status = 'pending' WHERE status = 'conflict';
ALTER TABLE research_candidate
    DROP COLUMN observation_id,
    DROP COLUMN dataset_version_id,
    DROP COLUMN import_job_id,
    DROP COLUMN decided_by,
    DROP COLUMN history,
    DROP COLUMN validation,
    DROP COLUMN scale,
    DROP COLUMN period_kind,
    DROP COLUMN unit_code,
    DROP COLUMN area_code,
    DROP COLUMN document_id,
    DROP COLUMN job_id;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_status
    CHECK (status IN ('pending', 'accepted', 'rejected', 'duplicate'));
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_review
    CHECK ((status = 'pending') = (reviewed_at IS NULL));

DELETE FROM research_job WHERE kind <> 'study';
ALTER TABLE research_job DROP COLUMN kind;
DELETE FROM report_schedule WHERE kind <> 'study';
ALTER TABLE report_schedule DROP COLUMN kind;

ALTER TABLE research_document DROP COLUMN text_content;
DELETE FROM research_document WHERE job_id IS NULL OR retriever = 'deepseek';
ALTER TABLE research_document DROP CONSTRAINT research_document_retriever_check;
ALTER TABLE research_document ADD CONSTRAINT research_document_retriever_check
    CHECK (retriever IN ('firecrawl', 'direct', 'fake'));
ALTER TABLE research_document ALTER COLUMN job_id SET NOT NULL;

DROP TABLE research_search;
