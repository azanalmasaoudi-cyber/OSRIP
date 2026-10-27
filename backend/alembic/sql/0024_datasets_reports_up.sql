-- 0024: datasets people upload to analyse, and research and dataset reports.
--
-- 1. analysis_dataset: a CSV, Excel or JSON file uploaded for analysis, private to its owner.
--    It is never part of the published statistics and never mixed with them. The values are
--    kept as the text the file holds (rows), with the deterministic analysis computed from
--    them at upload (analysis) and optional AI summaries of that analysis (summary), which
--    only state numbers found in the analysis. The same file (by SHA-256) and sheet is
--    stored once per owner.
-- 2. analysis_report: a report frozen at creation from an assistant research answer (its
--    question, verified answer, tables, charts and sources) or from a dataset's analysis.
--    Its content never changes afterwards (trigger); the links back to the dataset or the
--    answer are cleared if those are deleted, and the report stays as it was.
-- 3. dataset.analyze: who may upload and analyse datasets and create reports from them
--    (analysts, data managers and administrators; never guests).

CREATE TABLE analysis_dataset (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    name        text NOT NULL CONSTRAINT ck_analysis_dataset_name
                    CHECK (btrim(name) <> '' AND length(name) <= 200),
    file_type   text NOT NULL CONSTRAINT ck_analysis_dataset_type
                    CHECK (file_type IN ('csv', 'xlsx', 'json')),
    file_size   integer NOT NULL CONSTRAINT ck_analysis_dataset_size
                    CHECK (file_size BETWEEN 1 AND 10485760),
    sha256      text NOT NULL CONSTRAINT ck_analysis_dataset_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    sheet       text,
    columns     jsonb NOT NULL CONSTRAINT ck_analysis_dataset_columns CHECK (jsonb_typeof(columns) = 'array'),
    rows        jsonb NOT NULL CONSTRAINT ck_analysis_dataset_rows CHECK (jsonb_typeof(rows) = 'array'),
    row_count   integer NOT NULL CONSTRAINT ck_analysis_dataset_row_count CHECK (row_count >= 1),
    notes       jsonb NOT NULL DEFAULT '{}'::jsonb,
    analysis    jsonb NOT NULL,
    summary     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_analysis_dataset_file UNIQUE NULLS NOT DISTINCT (owner_id, sha256, sheet)
);
CREATE INDEX ix_analysis_dataset_owner ON analysis_dataset (owner_id, created_at DESC);

CREATE TABLE analysis_report (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    kind        text NOT NULL CONSTRAINT ck_analysis_report_kind CHECK (kind IN ('research', 'dataset')),
    title       text NOT NULL CONSTRAINT ck_analysis_report_title
                    CHECK (btrim(title) <> '' AND length(title) <= 200),
    language    text NOT NULL CONSTRAINT ck_analysis_report_language CHECK (language IN ('en', 'ar')),
    dataset_id  uuid REFERENCES analysis_dataset (id) ON DELETE SET NULL,
    message_id  bigint REFERENCES assistant_message (id) ON DELETE SET NULL,
    content     jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_analysis_report_owner ON analysis_report (owner_id, created_at DESC);

CREATE FUNCTION analysis_report_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.content IS DISTINCT FROM OLD.content
       OR NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.title IS DISTINCT FROM OLD.title
       OR NEW.language IS DISTINCT FROM OLD.language
       OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'analysis_report % is frozen', OLD.id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_analysis_report_frozen
    BEFORE UPDATE ON analysis_report
    FOR EACH ROW EXECUTE FUNCTION analysis_report_frozen();

INSERT INTO permission (code, description) VALUES
    ('dataset.analyze', 'Upload private datasets, analyse them and create reports from them');
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('analyst', 'dataset.analyze'),
    ('data_manager', 'dataset.analyze'),
    ('administrator', 'dataset.analyze');
