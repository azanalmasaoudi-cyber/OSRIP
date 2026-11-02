-- OSRIP migration 0026: custom roles and user groups.
--
-- Roles: the four built-in roles keep the permissions the migrations give them; an
-- administrator may add custom roles with any set of existing permissions. Groups: a group
-- gives its members roles and permissions. A user's permissions are those of their own
-- roles, of their groups' roles, of their groups' permissions and their explicit grants;
-- every check stays on the server (app.services.accounts.load_principal).

ALTER TABLE role ADD COLUMN builtin boolean NOT NULL DEFAULT false;
UPDATE role SET builtin = true WHERE code IN ('viewer', 'analyst', 'data_manager', 'administrator');
ALTER TABLE role ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE role ADD COLUMN created_by uuid REFERENCES app_user (id) ON DELETE SET NULL;
ALTER TABLE role ADD CONSTRAINT ck_role_code CHECK (code ~ '^[a-z][a-z0-9_]{2,39}$');
ALTER TABLE role ADD CONSTRAINT ck_role_description CHECK (length(description) BETWEEN 1 AND 300);

CREATE TABLE user_group (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text NOT NULL CONSTRAINT ck_user_group_name CHECK (length(btrim(name)) BETWEEN 1 AND 80),
    description  text NOT NULL DEFAULT ''
                     CONSTRAINT ck_user_group_description CHECK (length(description) <= 500),
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid REFERENCES app_user (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_user_group_name ON user_group (lower(btrim(name)));

CREATE TABLE group_member (
    group_id  uuid NOT NULL REFERENCES user_group (id) ON DELETE CASCADE,
    user_id   uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    added_by  uuid REFERENCES app_user (id) ON DELETE SET NULL,
    added_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
);
CREATE INDEX ix_group_member_user ON group_member (user_id);

CREATE TABLE group_role (
    group_id   uuid NOT NULL REFERENCES user_group (id) ON DELETE CASCADE,
    role_code  text NOT NULL REFERENCES role (code),
    PRIMARY KEY (group_id, role_code)
);

CREATE TABLE group_permission (
    group_id         uuid NOT NULL REFERENCES user_group (id) ON DELETE CASCADE,
    permission_code  text NOT NULL REFERENCES permission (code),
    PRIMARY KEY (group_id, permission_code)
);
