-- 0022: official statistics feeds and their synchronisation.
--
-- 1. source_feed: the registry of official publication series OSRIP follows (for example
--    NCSI's Monthly Statistical Bulletin), how each is reached (a public listing with an
--    official workbook, or a portal that needs access OSRIP does not have), and the check
--    schedule an administrator controls. Checks run in the separate sync worker, never in
--    the web server or the browser.
-- 2. source_release: each publication found in a feed, with the publisher's own dates, the
--    official file and its digest, and what became of it (new and changed figures staged
--    as an ordinary import; nothing published without the import workflow's validation).
-- 3. source_sync_run: one row per check, successful or not, for the synchronisation log.
--
-- A successful check is not a new publication: last_success_at, the latest release's
-- published_at and the latest observation period are kept apart.

CREATE TABLE source_feed (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                  text NOT NULL UNIQUE CHECK (code ~ '^[a-z0-9][a-z0-9_-]{1,40}$'),
    publisher             text NOT NULL CHECK (length(publisher) BETWEEN 1 AND 200),
    title_en              text NOT NULL CHECK (length(title_en) BETWEEN 1 AND 200),
    title_ar              text NOT NULL CHECK (length(title_ar) BETWEEN 1 AND 200),
    -- public_listing: a public list of publications with an official file to download;
    -- requires_access: an API or download that needs an account or key OSRIP does not hold.
    access                text NOT NULL CHECK (access IN ('public_listing', 'requires_access')),
    enabled               boolean NOT NULL DEFAULT false,
    check_interval_hours  integer NOT NULL DEFAULT 24 CHECK (check_interval_hours BETWEEN 6 AND 720),
    -- Staged imports wait for a data manager's approval unless this is switched on.
    auto_publish          boolean NOT NULL DEFAULT false,
    next_check_at         timestamptz,
    last_checked_at       timestamptz,
    last_success_at       timestamptz,
    last_status           text CHECK (last_status IS NULL OR last_status IN (
                              'no_new_release', 'new_release', 'staged', 'published', 'unchanged',
                              'failed', 'not_accessible')),
    last_error            text CHECK (last_error IS NULL OR length(last_error) <= 500),
    consecutive_failures  integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    updated_by            uuid REFERENCES app_user (id) ON DELETE SET NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_feed_access_enabled CHECK (access = 'public_listing' OR NOT enabled)
);

CREATE TABLE source_release (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_id             uuid NOT NULL REFERENCES source_feed (id) ON DELETE CASCADE,
    external_id         text NOT NULL CHECK (length(external_id) BETWEEN 1 AND 100),
    title_en            text NOT NULL CHECK (length(title_en) BETWEEN 1 AND 300),
    title_ar            text CHECK (title_ar IS NULL OR length(title_ar) <= 300),
    -- The publisher's own dates (as listed), never the time OSRIP checked.
    published_at        timestamptz,
    source_updated_at   timestamptz,
    file_url            text CHECK (file_url IS NULL OR file_url ~ '^https://'),
    file_sha256         text CHECK (file_sha256 IS NULL OR file_sha256 ~ '^[0-9a-f]{64}$'),
    file_bytes          integer CHECK (file_bytes IS NULL OR file_bytes >= 0),
    status              text NOT NULL CHECK (status IN (
                            'detected', 'no_file', 'unchanged', 'staged', 'published', 'failed')),
    rows_read           integer NOT NULL DEFAULT 0 CHECK (rows_read >= 0),
    rows_new            integer NOT NULL DEFAULT 0 CHECK (rows_new >= 0),
    rows_revised        integer NOT NULL DEFAULT 0 CHECK (rows_revised >= 0),
    rows_unchanged      integer NOT NULL DEFAULT 0 CHECK (rows_unchanged >= 0),
    import_job_id       uuid REFERENCES import_job (id) ON DELETE SET NULL,
    message             text CHECK (message IS NULL OR length(message) <= 500),
    detected_at         timestamptz NOT NULL DEFAULT now(),
    processed_at        timestamptz,
    -- The same publication with the same file is processed once.
    CONSTRAINT uq_source_release UNIQUE NULLS NOT DISTINCT (feed_id, external_id, file_sha256)
);
CREATE INDEX ix_source_release_feed ON source_release (feed_id, published_at DESC);

CREATE TABLE source_sync_run (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_id       uuid NOT NULL REFERENCES source_feed (id) ON DELETE CASCADE,
    trigger       text NOT NULL CHECK (trigger IN ('schedule', 'manual', 'upload')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text NOT NULL CHECK (status IN (
                      'running', 'no_new_release', 'new_release', 'staged', 'published',
                      'unchanged', 'failed', 'not_accessible')),
    attempts      integer NOT NULL DEFAULT 1 CHECK (attempts BETWEEN 1 AND 10),
    http_status   integer CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    releases_seen integer NOT NULL DEFAULT 0 CHECK (releases_seen >= 0),
    release_id    uuid REFERENCES source_release (id) ON DELETE SET NULL,
    message       text CHECK (message IS NULL OR length(message) <= 500),
    requested_by  uuid REFERENCES app_user (id) ON DELETE SET NULL
);
CREATE INDEX ix_source_sync_run_feed ON source_sync_run (feed_id, started_at DESC);

-- The registry's starting rows. Checks are off until an administrator switches them on (or
-- OSRIP_SOURCE_SYNC_DEFAULT_ON is set when the worker starts); the schedule is a daily check.
INSERT INTO source_feed (code, publisher, title_en, title_ar, access, enabled, check_interval_hours)
VALUES
    ('ncsi-monthly-bulletin', 'National Centre for Statistics and Information (NCSI)',
     'Monthly Statistical Bulletin (official Excel workbook)',
     'النشرة الإحصائية الشهرية (مصنف Excel الرسمي)', 'public_listing', false, 24),
    ('ncsi-data-portal', 'National Centre for Statistics and Information (NCSI)',
     'NCSI data portal API (data.gov.om)',
     'الواجهة البرمجية لبوابة بيانات المركز (data.gov.om)', 'requires_access', false, 24);
