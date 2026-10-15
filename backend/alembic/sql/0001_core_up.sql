-- OSRIP migration 0001: reference entities, sources, dataset versions, observations.
-- Booklet 3.11, Tables 3.3 and 3.4. Requires PostgreSQL 15+ (NULLS NOT DISTINCT).
-- Users/roles, analysis runs, recommendations, reports and audit events arrive in
-- later migrations together with the features and tests that use them.

-- gen_random_uuid() is built in on PostgreSQL 13+; no extension needed.

-- ------------------------------------------------------------------ vocabularies
CREATE TYPE data_mode AS ENUM ('verified_source', 'synthetic');
CREATE TYPE physical_dimension AS ENUM ('energy', 'power', 'volume', 'mass', 'currency', 'count', 'ratio');
CREATE TYPE value_type AS ENUM ('period_total', 'average', 'maximum', 'end_of_period', 'cumulative_to_date');
CREATE TYPE section_code AS ENUM ('electricity', 'water', 'food_security', 'trade');
CREATE TYPE trade_flow AS ENUM ('import', 'domestic_export', 're_export');
CREATE TYPE quality_status AS ENUM ('accepted', 'warning', 'withheld');
CREATE TYPE dataset_version_status AS ENUM ('draft', 'validated', 'approved', 'published', 'superseded', 'rejected');
CREATE TYPE area_level AS ENUM ('national', 'governorate', 'wilayat', 'service_area');

-- ------------------------------------------------------------------ reference entities
CREATE TABLE unit (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,
    dimension   physical_dimension NOT NULL,
    label_en    text NOT NULL,
    label_ar    text NOT NULL
);

CREATE TABLE indicator (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                text NOT NULL UNIQUE,
    section             section_code NOT NULL,
    measure             text NOT NULL,          -- generation, consumption, installed_capacity, ...
    dimension           physical_dimension NOT NULL,
    value_type          value_type NOT NULL,
    requires_commodity  boolean NOT NULL DEFAULT false,
    requires_partner    boolean NOT NULL DEFAULT false,
    requires_flow       boolean NOT NULL DEFAULT false,
    name_en             text NOT NULL,
    name_ar             text NOT NULL,
    definition_en       text NOT NULL,
    definition_ar       text NOT NULL,
    CONSTRAINT ck_indicator_partner_needs_flow CHECK (NOT requires_partner OR requires_flow)
);

CREATE TABLE area (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,
    level       area_level NOT NULL,
    parent_id   uuid REFERENCES area (id),
    name_en     text NOT NULL,
    name_ar     text NOT NULL,
    valid_from  date,
    valid_to    date,
    CONSTRAINT ck_area_validity CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_area_national_has_no_parent CHECK (level <> 'national' OR parent_id IS NULL)
);

CREATE TABLE commodity (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                    text NOT NULL UNIQUE,
    name_en                 text NOT NULL,
    name_ar                 text NOT NULL,
    product_form            text NOT NULL,       -- e.g. unprocessed grain, milled grain, fresh
    classification_system   text,                -- e.g. HS; null until mapping is reviewed
    classification_version  text,
    trade_codes             text[] NOT NULL DEFAULT '{}',
    quantity_unit_id        uuid NOT NULL REFERENCES unit (id),
    mapping_status          text NOT NULL DEFAULT 'provisional'
        CONSTRAINT ck_commodity_mapping_status CHECK (mapping_status IN ('provisional', 'reviewed', 'withdrawn')),
    CONSTRAINT ck_commodity_reviewed_has_classification CHECK (
        mapping_status <> 'reviewed'
        OR (classification_system IS NOT NULL AND classification_version IS NOT NULL AND cardinality(trade_codes) > 0)
    )
);

CREATE TABLE partner (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code         text NOT NULL UNIQUE,
    name_en      text NOT NULL,
    name_ar      text NOT NULL,
    is_fictional boolean NOT NULL           -- synthetic data may reference fictional partners only
);

-- ------------------------------------------------------------------ provenance
CREATE TABLE source (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    data_mode             data_mode NOT NULL,
    publisher             text,
    dataset_title         text NOT NULL,
    url                   text,
    access_date           date,
    publication_date      date,
    reference_period      text,
    geographic_coverage   text NOT NULL,
    definition_note       text,
    reuse_conditions      text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    -- 3.4: "No official publisher is assigned to a synthetic observation."
    CONSTRAINT ck_source_synthetic_has_no_publisher CHECK (data_mode <> 'synthetic' OR publisher IS NULL),
    -- 3.2: verified sources must be traceable.
    CONSTRAINT ck_source_verified_is_traceable CHECK (
        data_mode <> 'verified_source' OR (publisher IS NOT NULL AND url IS NOT NULL AND access_date IS NOT NULL)
    ),
    CONSTRAINT uq_source_id_mode UNIQUE (id, data_mode)
);

CREATE TABLE dataset_version (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        uuid NOT NULL,
    data_mode        data_mode NOT NULL,
    version_label    text NOT NULL,
    checksum_sha256  char(64) NOT NULL CONSTRAINT ck_dataset_version_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    status           dataset_version_status NOT NULL DEFAULT 'draft',
    created_at       timestamptz NOT NULL DEFAULT now(),
    approved_at      timestamptz,
    published_at     timestamptz,
    -- data_mode is inherited from the source and cannot diverge (composite FK).
    CONSTRAINT fk_dataset_version_source_mode FOREIGN KEY (source_id, data_mode) REFERENCES source (id, data_mode),
    CONSTRAINT uq_dataset_version_label UNIQUE (source_id, version_label),
    CONSTRAINT uq_dataset_version_id_mode UNIQUE (id, data_mode),
    CONSTRAINT ck_dataset_version_published_has_time CHECK (status <> 'published' OR published_at IS NOT NULL)
);

-- One designated published snapshot per source (booklet 3.11, T05).
CREATE UNIQUE INDEX uq_dataset_version_one_published
    ON dataset_version (source_id) WHERE status = 'published';

-- ------------------------------------------------------------------ observations
CREATE TABLE observation (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id  uuid NOT NULL,
    data_mode           data_mode NOT NULL,
    indicator_id        uuid NOT NULL REFERENCES indicator (id),
    area_id             uuid NOT NULL REFERENCES area (id),      -- explicit national area, never null geography
    period_start        date NOT NULL,
    period_end          date NOT NULL,
    period_complete     boolean NOT NULL DEFAULT true,
    value               numeric,                                  -- NULL means missing; never coerced to 0
    unit_id             uuid NOT NULL REFERENCES unit (id),
    commodity_id        uuid REFERENCES commodity (id),
    partner_id          uuid REFERENCES partner (id),
    flow                trade_flow,
    quality_status      quality_status NOT NULL DEFAULT 'accepted',
    source_row          text NOT NULL,
    CONSTRAINT fk_observation_version_mode FOREIGN KEY (dataset_version_id, data_mode)
        REFERENCES dataset_version (id, data_mode),
    CONSTRAINT ck_observation_period_order CHECK (period_end >= period_start),
    CONSTRAINT ck_observation_partner_needs_flow CHECK (partner_id IS NULL OR flow IS NOT NULL),
    -- Natural key (3.3, T04). NULLS NOT DISTINCT so repeated null dimensions still collide.
    CONSTRAINT uq_observation_natural_key UNIQUE NULLS NOT DISTINCT
        (dataset_version_id, indicator_id, area_id, period_start, period_end, commodity_id, partner_id, flow)
);

CREATE INDEX ix_observation_lookup ON observation (indicator_id, area_id, period_start);

-- Cross-table domain checks that a CHECK constraint cannot express.
CREATE FUNCTION observation_domain_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    ind  indicator%ROWTYPE;
    udim physical_dimension;
    fictional boolean;
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
    IF NEW.partner_id IS NOT NULL AND NEW.data_mode = 'synthetic' THEN
        SELECT is_fictional INTO fictional FROM partner WHERE id = NEW.partner_id;
        IF NOT fictional THEN
            RAISE EXCEPTION 'synthetic observations may reference fictional partners only'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_synthetic_partner';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_observation_domain_check
    BEFORE INSERT OR UPDATE ON observation
    FOR EACH ROW EXECUTE FUNCTION observation_domain_check();

-- Observations of a published version are immutable (revisions create a new version).
CREATE FUNCTION observation_immutable_when_published() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    st dataset_version_status;
BEGIN
    SELECT status INTO st FROM dataset_version WHERE id = OLD.dataset_version_id;
    IF st IN ('published', 'superseded') THEN
        RAISE EXCEPTION 'observations of a % dataset version are immutable', st
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_observation_immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_observation_immutable
    BEFORE UPDATE OR DELETE ON observation
    FOR EACH ROW EXECUTE FUNCTION observation_immutable_when_published();
