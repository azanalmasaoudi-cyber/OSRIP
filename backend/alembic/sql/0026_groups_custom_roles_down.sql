DROP TABLE IF EXISTS group_permission;
DROP TABLE IF EXISTS group_role;
DROP TABLE IF EXISTS group_member;
DROP TABLE IF EXISTS user_group;
-- Custom roles go with the feature (their assignments first).
DELETE FROM role_permission WHERE role_code IN (SELECT code FROM role WHERE NOT builtin);
DELETE FROM user_role WHERE role_code IN (SELECT code FROM role WHERE NOT builtin);
DELETE FROM role WHERE NOT builtin;
ALTER TABLE role DROP CONSTRAINT IF EXISTS ck_role_description;
ALTER TABLE role DROP CONSTRAINT IF EXISTS ck_role_code;
ALTER TABLE role DROP COLUMN IF EXISTS created_by;
ALTER TABLE role DROP COLUMN IF EXISTS created_at;
ALTER TABLE role DROP COLUMN IF EXISTS builtin;
