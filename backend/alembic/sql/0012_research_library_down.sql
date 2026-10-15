-- Reverses 0012. Saved research, watchlists and alerts are removed; research candidates
-- classed as research papers are reclassified as secondary before the old check returns.
DROP TABLE IF EXISTS alert_event;
DROP TABLE IF EXISTS alert_rule;
DROP TABLE IF EXISTS watchlist_item;
DROP TABLE IF EXISTS saved_research;

UPDATE research_candidate SET source_class = 'secondary' WHERE source_class = 'research';
ALTER TABLE research_candidate DROP CONSTRAINT ck_research_candidate_class;
ALTER TABLE research_candidate ADD CONSTRAINT ck_research_candidate_class
    CHECK (source_class IN ('official', 'international', 'secondary'));

ALTER TABLE assistant_message DROP COLUMN IF EXISTS structured;
ALTER TABLE assistant_message DROP COLUMN IF EXISTS mode;
