-- OSRIP migration 0003: accounts and authorization, the import workflow, derived
-- outputs (analysis runs, recommendations, review history, reports) and audit.
-- Booklet 3.2, 3.3, 3.9, 3.11 (Table 3.3), 3.12, 3.13, 3.15.
--
-- Requires 0001-0002. Must run before any observation exists: it adds a NOT NULL
-- frequency column to observation without a default (no frequency is guessed).

-- ================================================================== observations
CREATE TYPE observation_frequency AS ENUM ('annual', 'quarterly', 'monthly');

ALTER TABLE observation ADD COLUMN frequency observation_frequency NOT NULL;
-- Valuation basis of monetary trade values (e.g. CIF, FOB), preserved as supplied.
ALTER TABLE observation ADD COLUMN valuation_basis text;

-- Periods start on the first of a month and never exceed their frequency; a
-- complete period covers the whole frequency span (Table 3.4: "known frequency").
ALTER TABLE observation ADD CONSTRAINT ck_observation_frequency_period CHECK (
    extract(day FROM period_start) = 1
    AND period_end <= (period_start + CASE frequency
            WHEN 'annual' THEN interval '12 months'
            WHEN 'quarterly' THEN interval '3 months'
            ELSE interval '1 month' END - interval '1 day')::date
    AND (NOT period_complete OR period_end = (period_start + CASE frequency
            WHEN 'annual' THEN interval '12 months'
            WHEN 'quarterly' THEN interval '3 months'
            ELSE interval '1 month' END - interval '1 day')::date)
);

-- ================================================================== reference data
-- Invented commodities used only by synthetic fixtures.
ALTER TABLE commodity ADD COLUMN synthetic_only boolean NOT NULL DEFAULT false;

INSERT INTO commodity (code, name_en, name_ar, product_form, quantity_unit_id, mapping_status, synthetic_only)
SELECT 'SYNTH_COMMODITY', 'Synthetic demonstration commodity', 'سلعة تجريبية افتراضية',
       'synthetic (not a real product)', u.id, 'provisional', true
FROM unit u WHERE u.code = 'tonne';

-- Domain checks now also keep verified-source rows away from invented entities.
CREATE OR REPLACE FUNCTION observation_domain_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    ind  indicator%ROWTYPE;
    udim physical_dimension;
    fictional boolean;
    synth_only boolean;
BEGIN
    SELECT * INTO ind FROM indicator WHERE id = NEW.indicator_id;
    SELECT dimension INTO udim FROM unit WHERE id = NEW.unit_id;

    IF udim IS DISTINCT FROM ind.dimension THEN
        RAISE EXCEPTION 'unit dimension % does not match indicator % dimension %', udim, ind.code, ind.dimension
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_unit_dimension';
    END IF;
    IF ind.requires_commodity AND NEW.commodity_id IS NULL THEN
        RAISE EXCEPTION 'indicator % requires a commodity', ind.code
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_commodity_required';
    END IF;
    IF ind.requires_flow AND NEW.flow IS NULL THEN
        RAISE EXCEPTION 'indicator % requires a trade flow', ind.code
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_flow_required';
    END IF;
    IF NEW.partner_id IS NOT NULL THEN
        SELECT is_fictional INTO fictional FROM partner WHERE id = NEW.partner_id;
        IF NEW.data_mode = 'synthetic' AND NOT fictional THEN
            RAISE EXCEPTION 'synthetic observations may reference fictional partners only'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_synthetic_partner';
        END IF;
        IF NEW.data_mode = 'verified_source' AND fictional THEN
            RAISE EXCEPTION 'verified-source observations may not reference fictional partners'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_verified_partner';
        END IF;
    END IF;
    IF NEW.commodity_id IS NOT NULL AND NEW.data_mode = 'verified_source' THEN
        SELECT synthetic_only INTO synth_only FROM commodity WHERE id = NEW.commodity_id;
        IF synth_only THEN
            RAISE EXCEPTION 'verified-source observations may not reference a synthetic-only commodity'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_verified_commodity';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

-- ================================================================== provenance
-- A catalogue or landing page does not verify a particular numerical observation,
-- so verified sources must point at the direct file or the statistical table.
ALTER TABLE source ADD COLUMN locator_kind text
    CONSTRAINT ck_source_locator_kind CHECK (locator_kind IN ('direct_file', 'statistical_table', 'catalogue_page'));
ALTER TABLE source ADD CONSTRAINT ck_source_verified_locator CHECK (
    data_mode <> 'verified_source' OR locator_kind IN ('direct_file', 'statistical_table')
);
ALTER TABLE source ADD CONSTRAINT ck_source_verified_reuse CHECK (
    data_mode <> 'verified_source' OR reuse_conditions IS NOT NULL
);
ALTER TABLE source ADD COLUMN created_by uuid;  -- FK added below, after app_user exists

-- One upload of the same bytes per source (booklet 3.3: checksum detects repeated
-- uploads). A rejected version does not block a corrected re-upload.
CREATE UNIQUE INDEX uq_dataset_version_source_checksum
    ON dataset_version (source_id, checksum_sha256) WHERE status <> 'rejected';

ALTER TABLE dataset_version ADD COLUMN superseded_at timestamptz;

-- ================================================================== accounts
CREATE TYPE account_status AS ENUM ('active', 'suspended');

CREATE TABLE app_user (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email                text NOT NULL,
    display_name         text NOT NULL,
    -- Argon2id PHC string, or '!' for service accounts that cannot sign in.
    password_hash        text NOT NULL,
    status               account_status NOT NULL DEFAULT 'active',
    is_service_account   boolean NOT NULL DEFAULT false,
    created_at           timestamptz NOT NULL DEFAULT now(),
    password_changed_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_app_user_email_normalized CHECK (email = lower(btrim(email)) AND email LIKE '_%@_%'),
    CONSTRAINT ck_app_user_password_hash CHECK (password_hash = '!' OR password_hash LIKE '$argon2id$%'),
    CONSTRAINT ck_app_user_service_no_password CHECK (NOT is_service_account OR password_hash = '!')
);
CREATE UNIQUE INDEX uq_app_user_email ON app_user (email);

ALTER TABLE source ADD CONSTRAINT fk_source_created_by FOREIGN KEY (created_by) REFERENCES app_user (id);

CREATE TABLE role (
    code         text PRIMARY KEY,
    description  text NOT NULL
);

CREATE TABLE permission (
    code         text PRIMARY KEY,
    description  text NOT NULL
);

-- Permissions a role carries by default.
CREATE TABLE role_permission (
    role_code        text NOT NULL REFERENCES role (code),
    permission_code  text NOT NULL REFERENCES permission (code),
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE user_role (
    user_id     uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    role_code   text NOT NULL REFERENCES role (code),
    granted_by  uuid REFERENCES app_user (id),
    granted_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_code)
);

-- Explicit per-user grants for permissions no role implies (import.approve,
-- import.publish: SPEC_CONFLICTS C6).
CREATE TABLE user_permission_grant (
    user_id          uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    permission_code  text NOT NULL REFERENCES permission (code),
    granted_by       uuid REFERENCES app_user (id),
    granted_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, permission_code)
);

-- Server-side sessions. Only SHA-256 hashes of the bearer and CSRF tokens are stored.
CREATE TABLE user_session (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    token_hash       char(64) NOT NULL UNIQUE,
    csrf_token_hash  char(64) NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at     timestamptz NOT NULL DEFAULT now(),
    expires_at       timestamptz NOT NULL,
    revoked_at       timestamptz,
    CONSTRAINT ck_user_session_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_user_session_user ON user_session (user_id);

-- Login throttling. The client address is stored only as a keyed hash.
CREATE TABLE login_attempt (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         text NOT NULL,
    client_hash   char(64) NOT NULL,
    succeeded     boolean NOT NULL,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_login_attempt_email_time ON login_attempt (email, attempted_at);
CREATE INDEX ix_login_attempt_client_time ON login_attempt (client_hash, attempted_at);

INSERT INTO role (code, description) VALUES
    ('viewer',        'Reads published observations and their sources (same as the public).'),
    ('analyst',       'Saves filters, generates reports, runs rules and reviews recommendations.'),
    ('data_manager',  'Registers sources, uploads and validates datasets.'),
    ('administrator', 'Controls accounts, role assignment and permission grants.');

INSERT INTO permission (code, description) VALUES
    ('source.register',       'Register a data source and its provenance'),
    ('import.create',         'Upload a private CSV file for a registered source'),
    ('import.read',           'Read private imports, mappings and validation reports'),
    ('import.validate',       'Map columns and run validation on own imports'),
    ('import.manage_any',     'Map and validate imports created by other users'),
    ('import.approve',        'Approve a validated import after reviewing its errors (explicit grant)'),
    ('import.publish',        'Publish an approved dataset version (explicit grant)'),
    ('import.reject',         'Reject an import so it can never be published'),
    ('analysis.run',          'Run an eligible rule or model'),
    ('report.create',         'Freeze filters and generate a report'),
    ('recommendation.review', 'Append a review to a recommendation'),
    ('user.manage',           'Create accounts, suspend them, assign roles and grant permissions'),
    ('audit.read',            'Read audit events');

INSERT INTO role_permission (role_code, permission_code) VALUES
    ('analyst',       'analysis.run'),
    ('analyst',       'report.create'),
    ('analyst',       'recommendation.review'),
    ('data_manager',  'source.register'),
    ('data_manager',  'import.create'),
    ('data_manager',  'import.read'),
    ('data_manager',  'import.validate'),
    ('data_manager',  'import.reject'),
    ('administrator', 'user.manage'),
    ('administrator', 'audit.read');
-- 'viewer' has no permissions beyond public reads. import.approve, import.publish
-- and import.manage_any are never granted through a role.

-- ================================================================== import workflow
-- One import per dataset version. The dataset_version.status column is the single
-- lifecycle: draft (uploaded) -> validated -> approved -> published -> superseded,
-- or rejected. The raw file stays here, private; only published observations are public.
CREATE TABLE import_job (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id         uuid NOT NULL UNIQUE,
    data_mode                  data_mode NOT NULL,
    original_filename          text NOT NULL,
    file_bytes                 bytea NOT NULL,
    file_size                  integer NOT NULL CONSTRAINT ck_import_job_file_size CHECK (file_size BETWEEN 1 AND 5242880),
    header                     text[] NOT NULL,
    column_mapping             jsonb,
    row_count                  integer,
    valid_row_count            integer,
    warning_row_count          integer,
    rejected_row_count         integer,
    created_by                 uuid NOT NULL REFERENCES app_user (id),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    validated_by               uuid REFERENCES app_user (id),
    validated_at               timestamptz,
    approved_by                uuid REFERENCES app_user (id),
    approval_note              text,
    acknowledged_rejected_rows integer,
    published_by               uuid REFERENCES app_user (id),
    rejected_by                uuid REFERENCES app_user (id),
    rejection_reason           text,
    last_error_code            text,
    last_error_at              timestamptz,
    CONSTRAINT fk_import_job_version_mode FOREIGN KEY (dataset_version_id, data_mode)
        REFERENCES dataset_version (id, data_mode),
    CONSTRAINT ck_import_job_counts CHECK (
        row_count IS NULL OR valid_row_count + warning_row_count + rejected_row_count = row_count
    )
);

-- Row-level validation outcome for every data row, including rejected ones
-- (booklet 3.3: rejected rows remain with row number, original value and reason).
CREATE TABLE import_row (
    import_job_id  uuid NOT NULL REFERENCES import_job (id) ON DELETE CASCADE,
    row_number     integer NOT NULL CONSTRAINT ck_import_row_number CHECK (row_number >= 2),
    raw            jsonb NOT NULL,          -- original cell values keyed by CSV header
    outcome        text NOT NULL CONSTRAINT ck_import_row_outcome CHECK (outcome IN ('valid', 'warning', 'rejected')),
    issues         jsonb NOT NULL DEFAULT '[]',
    normalized     jsonb,                   -- resolved ids and parsed values; NULL when rejected
    PRIMARY KEY (import_job_id, row_number),
    CONSTRAINT ck_import_row_normalized CHECK ((outcome = 'rejected') = (normalized IS NULL))
);

-- Rows of an approved, published or superseded import are frozen.
CREATE FUNCTION import_row_frozen_after_approval() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    st dataset_version_status;
BEGIN
    SELECT dv.status INTO st
    FROM import_job j JOIN dataset_version dv ON dv.id = j.dataset_version_id
    WHERE j.id = COALESCE(OLD.import_job_id, NEW.import_job_id);
    IF st IN ('approved', 'published', 'superseded') THEN
        RAISE EXCEPTION 'import rows of an % version are frozen', st
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_import_row_frozen';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_import_row_frozen
    BEFORE INSERT OR UPDATE OR DELETE ON import_row
    FOR EACH ROW EXECUTE FUNCTION import_row_frozen_after_approval();

-- ================================================================== derived outputs
CREATE TYPE analysis_kind AS ENUM ('rule', 'forecast');
CREATE TYPE analysis_status AS ENUM ('succeeded', 'withheld', 'failed');

CREATE TABLE analysis_run (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    data_mode        data_mode NOT NULL,
    kind             analysis_kind NOT NULL,
    method_code      text NOT NULL,          -- e.g. R01_DEMAND_GROWTH
    method_version   text NOT NULL,
    parameters       jsonb NOT NULL DEFAULT '{}',
    status           analysis_status NOT NULL,
    status_reason    text,
    requested_by     uuid NOT NULL REFERENCES app_user (id),
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    CONSTRAINT uq_analysis_run_id_mode UNIQUE (id, data_mode),
    CONSTRAINT ck_analysis_run_withheld_reason CHECK (status = 'succeeded' OR status_reason IS NOT NULL)
);

-- Input versions; the composite FKs keep every input in the run's data mode.
CREATE TABLE analysis_run_input (
    analysis_run_id     uuid NOT NULL,
    dataset_version_id  uuid NOT NULL,
    data_mode           data_mode NOT NULL,
    PRIMARY KEY (analysis_run_id, dataset_version_id),
    CONSTRAINT fk_analysis_run_input_run FOREIGN KEY (analysis_run_id, data_mode)
        REFERENCES analysis_run (id, data_mode),
    CONSTRAINT fk_analysis_run_input_version FOREIGN KEY (dataset_version_id, data_mode)
        REFERENCES dataset_version (id, data_mode)
);

CREATE TYPE review_status AS ENUM ('under_review', 'explained', 'dismissed');

CREATE TABLE recommendation (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id  uuid NOT NULL,
    data_mode        data_mode NOT NULL,
    rule_code        text NOT NULL,
    evidence         jsonb NOT NULL,         -- actual values, threshold, input versions
    message_en       text NOT NULL,
    message_ar       text NOT NULL,
    follow_up_en     text NOT NULL,
    follow_up_ar     text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_recommendation_run FOREIGN KEY (analysis_run_id, data_mode)
        REFERENCES analysis_run (id, data_mode)
);

-- Append-only review history (booklet 3.13). Current status = latest review.
CREATE TABLE recommendation_review (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_id  uuid NOT NULL REFERENCES recommendation (id),
    reviewer_id        uuid NOT NULL REFERENCES app_user (id),
    status             review_status NOT NULL,
    reason             text NOT NULL CONSTRAINT ck_recommendation_review_reason CHECK (btrim(reason) <> ''),
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE report_visibility AS ENUM ('private', 'published');

CREATE TABLE report (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL REFERENCES app_user (id),
    data_mode     data_mode NOT NULL,
    title         text NOT NULL,
    filters       jsonb NOT NULL,           -- frozen before generation (booklet 3.12)
    visibility    report_visibility NOT NULL DEFAULT 'private',
    created_at    timestamptz NOT NULL DEFAULT now(),
    generated_at  timestamptz,
    CONSTRAINT uq_report_id_mode UNIQUE (id, data_mode)
);

CREATE TABLE report_input (
    report_id           uuid NOT NULL,
    dataset_version_id  uuid NOT NULL,
    data_mode           data_mode NOT NULL,
    PRIMARY KEY (report_id, dataset_version_id),
    CONSTRAINT fk_report_input_report FOREIGN KEY (report_id, data_mode) REFERENCES report (id, data_mode),
    CONSTRAINT fk_report_input_version FOREIGN KEY (dataset_version_id, data_mode)
        REFERENCES dataset_version (id, data_mode)
);

-- ================================================================== audit
CREATE TABLE audit_event (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    actor_id     uuid REFERENCES app_user (id),
    actor_label  text NOT NULL,             -- 'anonymous' when no session
    action       text NOT NULL,             -- e.g. import.publish
    entity_type  text,
    entity_id    text,
    outcome      text NOT NULL CONSTRAINT ck_audit_event_outcome CHECK (outcome IN ('success', 'denied', 'failed')),
    metadata     jsonb NOT NULL DEFAULT '{}' -- safe metadata only: never passwords or tokens
);
CREATE INDEX ix_audit_event_time ON audit_event (occurred_at);

-- Review history and audit events are append-only. Statement-level triggers refuse
-- every UPDATE, DELETE or TRUNCATE outright, whether or not any row matches.
CREATE FUNCTION forbid_update_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% refused)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

CREATE TRIGGER trg_recommendation_review_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON recommendation_review
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete();

CREATE TRIGGER trg_audit_event_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete();
