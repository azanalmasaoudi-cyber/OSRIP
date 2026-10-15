-- 0013: Al Mulhim's versioned identity and approved project knowledge.
-- Each reviewed version is stored once with its SHA-256; its content can never be changed
-- or deleted (trigger). Exactly one version is active. Version 1 is inserted by the
-- migration from backend/app/knowledge/assistant_profile_v1.json.

CREATE TABLE assistant_profile (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version         integer NOT NULL UNIQUE CHECK (version >= 1),
    status          text NOT NULL CHECK (status IN ('active', 'retired')),
    profile         jsonb NOT NULL,
    content_sha256  text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at      timestamptz NOT NULL DEFAULT now(),
    activated_at    timestamptz,
    retired_at      timestamptz,
    CONSTRAINT ck_assistant_profile_document CHECK (
        jsonb_typeof(profile) = 'object'
        AND profile ->> 'schema' = 'osrip.assistant_profile/1'
        AND (profile ->> 'version')::integer = version
    ),
    -- Active means activated and not retired; a retired row was never activated or has a
    -- retirement time.
    CONSTRAINT ck_assistant_profile_dates CHECK (
        (status = 'active') = (activated_at IS NOT NULL AND retired_at IS NULL)
    )
);

-- At most one active version.
CREATE UNIQUE INDEX uq_assistant_profile_active ON assistant_profile ((true)) WHERE status = 'active';

CREATE FUNCTION assistant_profile_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'assistant_profile versions are kept; activate another version instead';
    END IF;
    IF NEW.version IS DISTINCT FROM OLD.version
       OR NEW.profile IS DISTINCT FROM OLD.profile
       OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'assistant_profile content is immutable; publish a new version';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_assistant_profile_immutable
    BEFORE UPDATE OR DELETE ON assistant_profile
    FOR EACH ROW EXECUTE FUNCTION assistant_profile_immutable();
