-- OSRIP migration 0034: web figures proposed for review follow the platform's statistical scope,
-- which starts on 2021-01-01 (STATISTICAL_SCOPE_START in app/services/imports/validation.py;
-- research.queue_candidates and the assistant's instructions use the same date).
--
-- The check added in 0011 still said 2022. An internet answer that found a 2021 figure therefore
-- could not be saved at all: the insert of the research candidate failed, the whole answer was
-- rolled back and the visitor saw an error. Only the date changes; no row or column is touched.
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_scope;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_scope
    CHECK (period_end IS NULL OR period_end >= DATE '2021-01-01');
