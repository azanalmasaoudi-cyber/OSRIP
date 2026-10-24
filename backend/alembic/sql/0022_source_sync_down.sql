-- Reverses 0022. The synchronisation log and the release list are removed with their tables;
-- the imports a sync staged or published are ordinary imports and stay as they are.
DROP TABLE source_sync_run;
DROP TABLE source_release;
DROP TABLE source_feed;
