-- Reverts 0034. The 2022 rule comes back NOT VALID: candidates for 2021 saved under 0034 stay
-- (they are not deleted), while new ones must end in 2022 or later.
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_scope;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_scope
    CHECK (period_end IS NULL OR period_end >= DATE '2022-01-01') NOT VALID;
