-- OSRIP migration 0036: a utility's own reporting scope, its two operational water measures, and
-- the official outlook (forecasts, targets, plans) kept apart from observations.
-- Definitions and structure only, NOT figures: observations come through the reviewed import
-- workflow, outlook items through their own review (pending until approved), never from a migration.

-- Nama Water Services reports for all its operations except Dhofar Governorate (annual report
-- 2025, p. 4). Its figures are never the national NCSI water measures.
INSERT INTO area (code, level, parent_id, name_en, name_ar, code_authority, registry_note_en, registry_note_ar, members_stated)
SELECT 'OM-GRP-NWS', 'reporting_group', (SELECT id FROM area WHERE code = 'OM'),
       'Nama Water Services operations (all governorates except Dhofar)',
       'عمليات نماء لخدمات المياه (جميع المحافظات عدا ظفار)', 'osrip',
       'The utility''s own reporting scope: all its operations except Dhofar Governorate (Nama Water Services annual report 2025). Its figures are operational measures, never the national NCSI water production or distribution.',
       'نطاق الإبلاغ الخاص بالمرفق: جميع عملياته عدا محافظة ظفار (التقرير السنوي لنماء لخدمات المياه 2025). أرقامه مقاييس تشغيلية وليست إنتاج المياه أو توزيعها الوطني لدى المركز الوطني للإحصاء.',
       true;

INSERT INTO area_group_member (group_area_id, member_area_id)
SELECT g.id, m.id FROM area g JOIN area m
  ON m.code = ANY (ARRAY['OM-MA', 'OM-MU', 'OM-BU', 'OM-DA', 'OM-BS', 'OM-BJ', 'OM-SJ', 'OM-SS', 'OM-ZA', 'OM-WU'])
WHERE g.code = 'OM-GRP-NWS';

INSERT INTO indicator (code, section, measure, dimension, value_type, requires_commodity, requires_partner, requires_flow,
                       name_en, name_ar, definition_en, definition_ar, limitation_en, limitation_ar, parent_code) VALUES
('WATER_SUPPLY_UTILITY', 'water', 'supply', 'volume', 'period_total', false, false, false,
 'Water supplied (utility operations)', 'إمدادات المياه (عمليات المرفق)',
 'Water supplied into a water utility''s network during the year, as the utility reports it for its own operations.',
 'المياه الموردة إلى شبكة مرفق المياه خلال العام، كما يبلغ عنها المرفق لعملياته.',
 'An operational measure of one utility''s service area; not NCSI water production. Never compared with national figures as if it were the same measure.',
 'مقياس تشغيلي لنطاق خدمة مرفق واحد؛ ليس إنتاج المياه لدى المركز الوطني للإحصاء. لا يُقارن بالأرقام الوطنية كأنه المقياس نفسه.', NULL),
('WATER_DELIVERED_UTILITY', 'water', 'delivery', 'volume', 'period_total', false, false, false,
 'Water delivered (utility operations)', 'المياه المسلّمة (عمليات المرفق)',
 'Water delivered to customers during the year, as a water utility reports it for its own operations.',
 'المياه المسلّمة إلى المشتركين خلال العام، كما يبلغ عنها مرفق المياه لعملياته.',
 'An operational measure of one utility''s service area; not NCSI water distributed. Supplied minus delivered is not reported here as losses.',
 'مقياس تشغيلي لنطاق خدمة مرفق واحد؛ ليس المياه الموزعة لدى المركز الوطني للإحصاء. لا يُعرض الفرق بين الموردة والمسلّمة هنا على أنه فاقد.', NULL);

-- The official outlook: each item keeps what kind of evidence it is.
CREATE TYPE outlook_class AS ENUM ('observed', 'estimate', 'forecast', 'policy_target', 'planned', 'under_consideration');
CREATE TYPE outlook_review AS ENUM ('pending', 'approved', 'rejected');

CREATE TABLE outlook_item (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section          section_code NOT NULL,
    metric_code      text NOT NULL,
    metric_en        text NOT NULL,
    metric_ar        text NOT NULL,
    year             integer NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    value            numeric NULL,
    unit             text NOT NULL CHECK (unit IN ('MW', 'percent', 'm3_per_day', 'thousand_m3_per_day', 'event')),
    scope_en         text NOT NULL,
    scope_ar         text NOT NULL,
    evidence_class   outlook_class NOT NULL,
    status_note_en   text NULL,
    status_note_ar   text NULL,
    source_title     text NOT NULL,
    source_publisher text NOT NULL,
    source_url       text NOT NULL CHECK (source_url LIKE 'https://%'),
    source_locator   text NOT NULL,
    source_sha256    text NULL CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'),
    retrieved_on     date NOT NULL,
    issue_year       integer NOT NULL,
    batch_label      text NOT NULL,
    review_status    outlook_review NOT NULL DEFAULT 'pending',
    reviewed_by      uuid NULL REFERENCES app_user (id),
    reviewed_at      timestamptz NULL,
    review_note      text NULL,
    created_by       uuid NULL REFERENCES app_user (id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    -- Only an event (a date such as a commercial operation year) may have no value.
    CONSTRAINT outlook_value_or_event CHECK (value IS NOT NULL OR unit = 'event'),
    -- Nothing in or after the year the statement was issued can be an observation or estimate.
    CONSTRAINT outlook_observed_before_issue CHECK (evidence_class NOT IN ('observed', 'estimate') OR year < issue_year),
    -- A decided item records who decided and when.
    CONSTRAINT outlook_review_recorded CHECK (review_status = 'pending' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    CONSTRAINT outlook_item_once UNIQUE (source_url, metric_code, year, scope_en)
);
CREATE INDEX outlook_item_section ON outlook_item (section, review_status);
