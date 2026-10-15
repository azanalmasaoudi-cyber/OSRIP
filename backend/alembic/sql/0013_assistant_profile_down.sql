-- Reverses 0013. The profile versions are removed with the table (DROP does not fire the
-- row trigger); the reviewed JSON files in backend/app/knowledge remain the source.
DROP TABLE assistant_profile;
DROP FUNCTION assistant_profile_immutable();
