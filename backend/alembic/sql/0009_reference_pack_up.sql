-- OSRIP migration 0009: the curated Oman reference pack (research cutoff 2026-09-27).
-- Adds the provenance the pack carries for every record, dated statements without a
-- reference period, published regional groupings, an indicator hierarchy (parents
-- overlap their components), explicit unit-conversion rules and the pack's
-- documented reconciliation notes. Definitions only: the observations themselves
-- are loaded through the normal import workflow (python -m app.cli import-reference-pack).

-- ================================================================== observations
ALTER TABLE observation ADD COLUMN record_ref text;            -- e.g. OM-0079 (the pack's record id)
ALTER TABLE observation ADD COLUMN source_locator text;        -- e.g. "p. 24"
ALTER TABLE observation ADD COLUMN revision_status text
    CONSTRAINT ck_observation_revision_status CHECK (revision_status IN
        ('reported', 'provisional', 'preliminary', 'estimate', 'official_statement', 'reported_statement', 'revised'));
-- A published inequality ("more than 95 percent") is kept as an inequality.
ALTER TABLE observation ADD COLUMN value_operator text
    CONSTRAINT ck_observation_value_operator CHECK (value_operator IN ('>', '>=', '<', '<=', '~'));
-- The date a statement was made, for records whose reference period is not stated.
ALTER TABLE observation ADD COLUMN statement_date date;
ALTER TABLE observation ADD COLUMN note text;

ALTER TABLE observation DROP CONSTRAINT ck_observation_frequency_period;
ALTER TABLE observation ADD CONSTRAINT ck_observation_frequency_period CHECK (
    (frequency::text = 'statement' AND statement_date IS NOT NULL
        AND period_start = statement_date AND period_end = statement_date)
    OR (frequency::text <> 'statement'
        AND extract(day FROM period_start) = 1
        AND period_end <= (period_start + CASE frequency::text
                WHEN 'annual' THEN interval '12 months'
                WHEN 'quarterly' THEN interval '3 months'
                ELSE interval '1 month' END - interval '1 day')::date
        AND (NOT period_complete OR period_end = (period_start + CASE frequency::text
                WHEN 'annual' THEN interval '12 months'
                WHEN 'quarterly' THEN interval '3 months'
                ELSE interval '1 month' END - interval '1 day')::date))
);
CREATE INDEX ix_observation_record_ref ON observation (record_ref) WHERE record_ref IS NOT NULL;

-- ================================================================== sources
ALTER TABLE source DROP CONSTRAINT ck_source_locator_kind;
ALTER TABLE source ADD CONSTRAINT ck_source_locator_kind
    CHECK (locator_kind IN ('direct_file', 'statistical_table', 'catalogue_page', 'web_page'));
-- A web page (official statement or news report) states the values in its own text.
ALTER TABLE source DROP CONSTRAINT ck_source_verified_locator;
ALTER TABLE source ADD CONSTRAINT ck_source_verified_locator
    CHECK (data_mode <> 'verified_source' OR locator_kind IN ('direct_file', 'statistical_table', 'web_page'));
ALTER TABLE source ADD COLUMN source_code text;                 -- S01 ... S08 within a reference pack
ALTER TABLE source ADD COLUMN source_role text
    CONSTRAINT ck_source_role CHECK (source_role IN
        ('primary', 'official_statement', 'secondary', 'crosscheck', 'superseded_crosscheck'));

-- ================================================================== reference packs
CREATE TABLE reference_pack (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code             text NOT NULL UNIQUE,
    title            text NOT NULL,
    research_cutoff  date NOT NULL,
    record_count     integer NOT NULL CONSTRAINT ck_reference_pack_count CHECK (record_count > 0),
    checksum_sha256  char(64) NOT NULL CONSTRAINT ck_reference_pack_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    document         text NOT NULL,             -- the document the pack was extracted from
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Every reference of the pack, including crosschecks that supply no imported value.
CREATE TABLE reference_pack_source (
    pack_id      uuid NOT NULL REFERENCES reference_pack (id) ON DELETE CASCADE,
    code         text NOT NULL,
    publisher    text NOT NULL,
    title        text NOT NULL,
    publication  text NOT NULL,
    accessed_on  date NOT NULL,
    role         text NOT NULL CONSTRAINT ck_reference_pack_source_role CHECK (role IN
        ('primary', 'official_statement', 'secondary', 'crosscheck', 'superseded_crosscheck')),
    url          text NOT NULL,
    locations    text,
    source_id    uuid REFERENCES source (id),   -- set when the source supplies imported records
    PRIMARY KEY (pack_id, code)
);

-- Documented conflicts, revisions and limitations (Q01 ...). Shown, never resolved silently.
CREATE TABLE data_quality_note (
    pack_id        uuid NOT NULL REFERENCES reference_pack (id) ON DELETE CASCADE,
    code           text NOT NULL,
    title_en       text NOT NULL,
    title_ar       text NOT NULL,
    body_en        text NOT NULL,
    body_ar        text NOT NULL,
    source_codes   text[] NOT NULL DEFAULT '{}',
    sections       text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (pack_id, code)
);

-- ================================================================== reporting groups
-- Sources publish some figures for groups of governorates. A group is its own area:
-- its value is never divided among, or mapped onto, its member governorates.
CREATE TABLE area_group_member (
    group_area_id   uuid NOT NULL REFERENCES area (id),
    member_area_id  uuid NOT NULL REFERENCES area (id),
    PRIMARY KEY (group_area_id, member_area_id)
);
ALTER TABLE area ADD COLUMN members_stated boolean NOT NULL DEFAULT true;

INSERT INTO area (code, level, parent_id, name_en, name_ar, code_authority, registry_note_en, registry_note_ar, members_stated)
SELECT v.code, 'reporting_group', (SELECT id FROM area WHERE code = 'OM'), v.name_en, v.name_ar, 'osrip', v.note_en, v.note_ar, v.stated
FROM (VALUES
    ('OM-GRP-BATINAH-DHAHIRAH', 'North & South Al Batinah + Adh Dhahirah', 'شمال وجنوب الباطنة والظاهرة',
     'Published as one group (electricity). Never split among the three governorates.',
     'تُنشر كمجموعة واحدة (الكهرباء). لا تُقسَّم على المحافظات الثلاث.', true),
    ('OM-GRP-SHARQIYAH', 'North & South Ash Sharqiyah', 'شمال وجنوب الشرقية',
     'Published as one group (electricity). Never split between the two governorates.',
     'تُنشر كمجموعة واحدة (الكهرباء). لا تُقسَّم على المحافظتين.', true),
    ('OM-GRP-BATINAH', 'North & South Al Batinah', 'شمال وجنوب الباطنة',
     'Published as one group (fisheries). Never split between the two governorates.',
     'تُنشر كمجموعة واحدة (الثروة السمكية). لا تُقسَّم على المحافظتين.', true),
    ('OM-GRP-OTHER-ELEC', 'Other governorates (electricity table)', 'المحافظات الأخرى (جدول الكهرباء)',
     'The source does not list which governorates this group contains.',
     'لا يذكر المصدر المحافظات التي تضمها هذه المجموعة.', false),
    ('OM-GRP-OTHER-WATER', 'Other governorates (water table)', 'المحافظات الأخرى (جدول المياه)',
     'All governorates except Muscat and Dhofar, as published in the water production table.',
     'جميع المحافظات عدا مسقط وظفار، كما وردت في جدول إنتاج المياه.', true)
) AS v(code, name_en, name_ar, note_en, note_ar, stated);

INSERT INTO area_group_member (group_area_id, member_area_id)
SELECT g.id, m.id FROM area g JOIN area m ON m.code = ANY (CASE g.code
    WHEN 'OM-GRP-BATINAH-DHAHIRAH' THEN ARRAY['OM-BJ', 'OM-BS', 'OM-ZA']
    WHEN 'OM-GRP-SHARQIYAH' THEN ARRAY['OM-SJ', 'OM-SS']
    WHEN 'OM-GRP-BATINAH' THEN ARRAY['OM-BJ', 'OM-BS']
    WHEN 'OM-GRP-OTHER-WATER' THEN ARRAY['OM-BJ', 'OM-BS', 'OM-BU', 'OM-DA', 'OM-MU', 'OM-SJ', 'OM-SS', 'OM-WU', 'OM-ZA']
    ELSE ARRAY[]::text[] END)
WHERE g.level = 'reporting_group';

-- ================================================================== partners (real countries)
INSERT INTO partner (code, name_en, name_ar, is_fictional) VALUES
    ('ARE', 'United Arab Emirates', 'الإمارات العربية المتحدة', false),
    ('SAU', 'Saudi Arabia', 'المملكة العربية السعودية', false),
    ('IND', 'India', 'الهند', false),
    ('USA', 'United States', 'الولايات المتحدة', false),
    ('KOR', 'South Korea', 'كوريا الجنوبية', false),
    ('IRN', 'Iran', 'إيران', false),
    ('HKG', 'Hong Kong', 'هونغ كونغ', false),
    ('GBR', 'United Kingdom', 'المملكة المتحدة', false),
    ('CHN', 'China', 'الصين', false),
    ('TUR', 'Turkey', 'تركيا', false);

-- ================================================================== units and conversions
INSERT INTO unit (code, dimension, label_en, label_ar) VALUES
    ('thousand_m3',          'volume',   'thousand cubic metres', 'ألف متر مكعب'),
    ('thousand_tonnes',      'mass',     'thousand tonnes',       'ألف طن'),
    ('million_tonnes',       'mass',     'million tonnes',        'مليون طن'),
    ('thousand_OMR',         'currency', 'thousand Omani rials',  'ألف ريال عماني'),
    ('million_OMR',          'currency', 'million Omani rials',   'مليون ريال عماني'),
    ('thousand_connections', 'count',    'thousand connections',  'ألف توصيلة'),
    ('thousand_head',        'count',    'thousand head',         'ألف رأس'),
    ('feddan',               'area',     'feddan',                'فدان');

-- Conversions are applied only through these explicit rules; stored values keep the
-- unit in which they were published.
CREATE TABLE unit_conversion (
    from_unit_id  uuid NOT NULL REFERENCES unit (id),
    to_unit_id    uuid NOT NULL REFERENCES unit (id),
    factor        numeric NOT NULL CONSTRAINT ck_unit_conversion_factor CHECK (factor > 0),
    basis         text NOT NULL,
    PRIMARY KEY (from_unit_id, to_unit_id),
    CONSTRAINT ck_unit_conversion_distinct CHECK (from_unit_id <> to_unit_id)
);
CREATE FUNCTION unit_conversion_same_dimension() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT dimension FROM unit WHERE id = NEW.from_unit_id) IS DISTINCT FROM
       (SELECT dimension FROM unit WHERE id = NEW.to_unit_id) THEN
        RAISE EXCEPTION 'a unit conversion must stay within one physical dimension'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_unit_conversion_dimension';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_unit_conversion_same_dimension
    BEFORE INSERT OR UPDATE ON unit_conversion
    FOR EACH ROW EXECUTE FUNCTION unit_conversion_same_dimension();

INSERT INTO unit_conversion (from_unit_id, to_unit_id, factor, basis)
SELECT f.id, t.id, v.factor, v.basis
FROM (VALUES
    ('thousand_m3', 'million_m3', 0.001, 'One thousand m³ = 1,000 m³; one million m³ = 1,000,000 m³.'),
    ('million_m3', 'thousand_m3', 1000, 'One million m³ = 1,000 thousand m³.'),
    ('thousand_tonnes', 'tonne', 1000, 'One thousand tonnes = 1,000 tonnes.'),
    ('million_tonnes', 'tonne', 1000000, 'One million tonnes = 1,000,000 tonnes.'),
    ('thousand_OMR', 'million_OMR', 0.001, 'One thousand OMR = 0.001 million OMR.'),
    ('million_OMR', 'thousand_OMR', 1000, 'One million OMR = 1,000 thousand OMR.'),
    ('thousand_OMR', 'OMR', 1000, 'One thousand OMR = 1,000 OMR.'),
    ('million_OMR', 'OMR', 1000000, 'One million OMR = 1,000,000 OMR.')
) AS v(from_code, to_code, factor, basis)
JOIN unit f ON f.code = v.from_code JOIN unit t ON t.code = v.to_code;

-- ================================================================== indicator hierarchy
-- A parent category overlaps its components: the two are never added together.
ALTER TABLE indicator ADD COLUMN parent_code text REFERENCES indicator (code);
-- Unit in which values are shown when an indicator is published in several units of
-- one dimension; conversion goes only through unit_conversion, originals are kept.
ALTER TABLE indicator ADD COLUMN display_unit_code text REFERENCES unit (code);

INSERT INTO indicator (code, section, measure, dimension, value_type, requires_commodity, requires_partner, requires_flow,
                       name_en, name_ar, definition_en, definition_ar, limitation_en, limitation_ar, parent_code) VALUES
-- ---------------------------------------------------------------- electricity
('ELEC_GROSS_GENERATION', 'electricity', 'gross_generation', 'energy', 'period_total', false, false, false,
 'Gross electricity generation', 'إجمالي توليد الكهرباء',
 'Electrical energy produced by generating plants during the period, before the plants'' own use.',
 'الطاقة الكهربائية المنتجة في محطات التوليد خلال الفترة قبل الاستهلاك الذاتي للمحطات.',
 'Gross minus net generation is mainly station use; it is not automatically network losses.',
 'الفرق بين إجمالي التوليد وصافيه هو في الغالب استهلاك المحطات، وليس بالضرورة فاقد الشبكة.', NULL),
('ELEC_NET_GENERATION', 'electricity', 'net_generation', 'energy', 'period_total', false, false, false,
 'Net electricity generation', 'صافي توليد الكهرباء',
 'Electrical energy sent out by generating plants during the period, after the plants'' own use.',
 'الطاقة الكهربائية المرسلة من محطات التوليد خلال الفترة بعد الاستهلاك الذاتي للمحطات.',
 'Not consumption: transmission and distribution come after net generation.',
 'ليس استهلاكاً: يأتي النقل والتوزيع بعد صافي التوليد.', NULL),
('ELEC_DISTRIBUTION', 'electricity', 'distribution', 'energy', 'period_total', false, false, false,
 'Electricity distributed', 'الكهرباء الموزعة',
 'Electrical energy distributed to customers during the period, as defined by the source.',
 'الطاقة الكهربائية الموزعة على المشتركين خلال الفترة وفق تعريف المصدر.',
 'Distribution and consumption may be defined differently by the source; they are shown separately.',
 'قد يختلف تعريف التوزيع عن الاستهلاك في المصدر؛ لذا يُعرضان منفصلين.', NULL),
('ELEC_CONSUMPTION_RESIDENTIAL', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
 'Electricity consumption: residential', 'استهلاك الكهرباء: القطاع السكني',
 'Electricity consumed by residential customers during the period.', 'الكهرباء التي استهلكها المشتركون السكنيون خلال الفترة.',
 'A component of total consumption; never added to the total.', 'جزء من إجمالي الاستهلاك؛ لا يُضاف إلى الإجمالي.', 'ELEC_CONSUMPTION'),
('ELEC_CONSUMPTION_COMMERCIAL', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
 'Electricity consumption: commercial', 'استهلاك الكهرباء: القطاع التجاري',
 'Electricity consumed by commercial customers during the period.', 'الكهرباء التي استهلكها المشتركون التجاريون خلال الفترة.',
 'A component of total consumption; never added to the total.', 'جزء من إجمالي الاستهلاك؛ لا يُضاف إلى الإجمالي.', 'ELEC_CONSUMPTION'),
('ELEC_CONSUMPTION_INDUSTRIAL', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
 'Electricity consumption: industrial', 'استهلاك الكهرباء: القطاع الصناعي',
 'Electricity consumed by industrial customers during the period.', 'الكهرباء التي استهلكها المشتركون الصناعيون خلال الفترة.',
 'A component of total consumption; never added to the total.', 'جزء من إجمالي الاستهلاك؛ لا يُضاف إلى الإجمالي.', 'ELEC_CONSUMPTION'),
('ELEC_CONSUMPTION_GOVERNMENT', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
 'Electricity consumption: government', 'استهلاك الكهرباء: القطاع الحكومي',
 'Electricity consumed by government customers during the period.', 'الكهرباء التي استهلكتها الجهات الحكومية خلال الفترة.',
 'A component of total consumption; never added to the total.', 'جزء من إجمالي الاستهلاك؛ لا يُضاف إلى الإجمالي.', 'ELEC_CONSUMPTION'),
('ELEC_CONSUMPTION_OTHER', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
 'Electricity consumption: other', 'استهلاك الكهرباء: قطاعات أخرى',
 'Electricity consumed by other customer categories during the period.', 'الكهرباء التي استهلكتها فئات المشتركين الأخرى خلال الفترة.',
 'A component of total consumption; never added to the total.', 'جزء من إجمالي الاستهلاك؛ لا يُضاف إلى الإجمالي.', 'ELEC_CONSUMPTION'),
('ELEC_CONNECTIONS', 'electricity', 'connections', 'count', 'end_of_period', false, false, false,
 'Electricity connections', 'توصيلات الكهرباء',
 'Electricity service connections at the end of the period, as defined by the source.',
 'توصيلات خدمة الكهرباء في نهاية الفترة وفق تعريف المصدر.',
 'Connections are not households or people.', 'التوصيلات ليست أسراً ولا أفراداً.', NULL),
-- ---------------------------------------------------------------- water
('WATER_DISTRIBUTION', 'water', 'distribution', 'volume', 'period_total', false, false, false,
 'Water distributed', 'المياه الموزعة',
 'Water distributed through the network during the period, as defined by the source.',
 'المياه الموزعة عبر الشبكة خلال الفترة وفق تعريف المصدر.',
 'Production minus distribution or consumption is not leakage or a shortage: coverage and definitions differ.',
 'الفرق بين الإنتاج والتوزيع أو الاستهلاك ليس تسرباً ولا عجزاً؛ فالتغطية والتعريفات مختلفة.', NULL),
('WATER_CONNECTIONS', 'water', 'connections', 'count', 'end_of_period', false, false, false,
 'Water connections', 'توصيلات المياه',
 'Water service connections at the end of the period, as defined by the source.',
 'توصيلات خدمة المياه في نهاية الفترة وفق تعريف المصدر.',
 'Connections are not households or people.', 'التوصيلات ليست أسراً ولا أفراداً.', NULL),
-- ---------------------------------------------------------------- food security: crops
('AGRI_CROP_PRODUCTION', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Crop production (including fodder)', 'إنتاج المحاصيل (يشمل الأعلاف)',
 'Total crop production in the year: vegetables, field crops, fodder and fruit.',
 'إجمالي إنتاج المحاصيل في السنة: الخضروات والمحاصيل الحقلية والأعلاف والفواكه.',
 'Includes fodder. Production tonnage is not dietary adequacy or availability for people.',
 'يشمل الأعلاف. كمية الإنتاج ليست كفاية غذائية ولا توافراً للسكان.', NULL),
('AGRI_CULTIVATED_AREA', 'food_security', 'cultivated_area', 'area', 'end_of_period', false, false, false,
 'Cultivated area', 'المساحة المزروعة',
 'Area under cultivation in the year, as estimated by the source.', 'المساحة المزروعة في السنة وفق تقدير المصدر.',
 'An area, not an output; the 2022 figure is rounded by the source.', 'مساحة وليست إنتاجاً؛ رقم 2022 مقرّب في المصدر.', NULL),
('AGRI_PROD_VEGETABLES', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Vegetable production', 'إنتاج الخضروات', 'Production of all vegetables in the year.', 'إنتاج جميع الخضروات في السنة.',
 'A component of crop production; never added to the total.', 'جزء من إنتاج المحاصيل؛ لا يُضاف إلى الإجمالي.', 'AGRI_CROP_PRODUCTION'),
('AGRI_PROD_TOMATOES', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Tomato production', 'إنتاج الطماطم', 'Production of tomatoes in the year.', 'إنتاج الطماطم في السنة.',
 'A component of vegetable production.', 'جزء من إنتاج الخضروات.', 'AGRI_PROD_VEGETABLES'),
('AGRI_PROD_CUCUMBERS', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Cucumber production', 'إنتاج الخيار', 'Production of cucumbers in the year.', 'إنتاج الخيار في السنة.',
 'A component of vegetable production.', 'جزء من إنتاج الخضروات.', 'AGRI_PROD_VEGETABLES'),
('AGRI_PROD_POTATOES', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Potato production', 'إنتاج البطاطس', 'Production of potatoes in the year.', 'إنتاج البطاطس في السنة.',
 'A component of vegetable production.', 'جزء من إنتاج الخضروات.', 'AGRI_PROD_VEGETABLES'),
('AGRI_PROD_ONIONS', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Onion production', 'إنتاج البصل', 'Production of onions in the year.', 'إنتاج البصل في السنة.',
 'A component of vegetable production.', 'جزء من إنتاج الخضروات.', 'AGRI_PROD_VEGETABLES'),
('AGRI_PROD_GARLIC', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Garlic production', 'إنتاج الثوم', 'Production of garlic in the year.', 'إنتاج الثوم في السنة.',
 'A component of vegetable production.', 'جزء من إنتاج الخضروات.', 'AGRI_PROD_VEGETABLES'),
('AGRI_PROD_FIELD_CROPS', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Field-crop production', 'إنتاج المحاصيل الحقلية', 'Production of field crops in the year.', 'إنتاج المحاصيل الحقلية في السنة.',
 'A component of crop production; never added to the total.', 'جزء من إنتاج المحاصيل؛ لا يُضاف إلى الإجمالي.', 'AGRI_CROP_PRODUCTION'),
('AGRI_PROD_WHEAT', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Wheat production', 'إنتاج القمح', 'Production of wheat in the year.', 'إنتاج القمح في السنة.',
 'A component of field-crop production.', 'جزء من إنتاج المحاصيل الحقلية.', 'AGRI_PROD_FIELD_CROPS'),
('AGRI_PROD_FODDER', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Fodder production', 'إنتاج الأعلاف', 'Production of fodder crops in the year.', 'إنتاج محاصيل الأعلاف في السنة.',
 'Animal feed, not food for people. A component of crop production.', 'علف للحيوانات وليس غذاءً للسكان. جزء من إنتاج المحاصيل.', 'AGRI_CROP_PRODUCTION'),
('AGRI_PROD_FRUIT', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Fruit production', 'إنتاج الفواكه', 'Production of fruit, including dates, in the year.', 'إنتاج الفواكه بما فيها التمور في السنة.',
 'A component of crop production; never added to the total.', 'جزء من إنتاج المحاصيل؛ لا يُضاف إلى الإجمالي.', 'AGRI_CROP_PRODUCTION'),
('AGRI_PROD_DATES', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Date production', 'إنتاج التمور', 'Production of dates in the year.', 'إنتاج التمور في السنة.',
 'A component of fruit production.', 'جزء من إنتاج الفواكه.', 'AGRI_PROD_FRUIT'),
('AGRI_PROD_MANGO', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Mango production', 'إنتاج المانجو', 'Production of mangoes in the year.', 'إنتاج المانجو في السنة.',
 'A component of fruit production.', 'جزء من إنتاج الفواكه.', 'AGRI_PROD_FRUIT'),
('AGRI_PROD_BANANA', 'food_security', 'crop_production', 'mass', 'period_total', false, false, false,
 'Banana production', 'إنتاج الموز', 'Production of bananas in the year.', 'إنتاج الموز في السنة.',
 'A component of fruit production.', 'جزء من إنتاج الفواكه.', 'AGRI_PROD_FRUIT'),
-- ---------------------------------------------------------------- food security: livestock and fish
('LIVESTOCK_CATTLE', 'food_security', 'livestock', 'count', 'end_of_period', false, false, false,
 'Cattle', 'الأبقار', 'Number of cattle, as estimated by the source.', 'عدد الأبقار وفق تقدير المصدر.',
 'Head of livestock, not meat production.', 'عدد رؤوس الماشية وليس إنتاج اللحوم.', NULL),
('LIVESTOCK_CAMELS', 'food_security', 'livestock', 'count', 'end_of_period', false, false, false,
 'Camels', 'الإبل', 'Number of camels, as estimated by the source.', 'عدد الإبل وفق تقدير المصدر.',
 'Head of livestock, not meat production.', 'عدد رؤوس الماشية وليس إنتاج اللحوم.', NULL),
('LIVESTOCK_SHEEP', 'food_security', 'livestock', 'count', 'end_of_period', false, false, false,
 'Sheep', 'الأغنام', 'Number of sheep, as estimated by the source.', 'عدد الأغنام وفق تقدير المصدر.',
 'Head of livestock, not meat production.', 'عدد رؤوس الماشية وليس إنتاج اللحوم.', NULL),
('LIVESTOCK_GOATS', 'food_security', 'livestock', 'count', 'end_of_period', false, false, false,
 'Goats', 'الماعز', 'Number of goats, as estimated by the source.', 'عدد الماعز وفق تقدير المصدر.',
 'Head of livestock, not meat production.', 'عدد رؤوس الماشية وليس إنتاج اللحوم.', NULL),
('FISH_CAPTURE_LANDINGS', 'food_security', 'fish_landings', 'mass', 'period_total', false, false, false,
 'Capture fish landings', 'إنزال الأسماك المصيدة',
 'Fish landed by traditional, coastal and commercial fishing during the period.',
 'الأسماك المنزلة من الصيد التقليدي والساحلي والتجاري خلال الفترة.',
 'Capture only: excludes aquaculture. Tonnage landed is not consumption or dietary adequacy.',
 'الصيد فقط دون الاستزراع السمكي. الكمية المنزلة ليست استهلاكاً ولا كفاية غذائية.', NULL),
('FISH_LANDINGS_TRADITIONAL', 'food_security', 'fish_landings', 'mass', 'period_total', false, false, false,
 'Fish landings: traditional fishing', 'إنزال الأسماك: الصيد التقليدي', 'Fish landed by traditional fishing during the period.',
 'الأسماك المنزلة من الصيد التقليدي خلال الفترة.', 'A component of capture landings.', 'جزء من إنزال الأسماك المصيدة.', 'FISH_CAPTURE_LANDINGS'),
('FISH_LANDINGS_COASTAL', 'food_security', 'fish_landings', 'mass', 'period_total', false, false, false,
 'Fish landings: coastal fishing', 'إنزال الأسماك: الصيد الساحلي', 'Fish landed by coastal fishing during the period.',
 'الأسماك المنزلة من الصيد الساحلي خلال الفترة.', 'A component of capture landings.', 'جزء من إنزال الأسماك المصيدة.', 'FISH_CAPTURE_LANDINGS'),
('FISH_LANDINGS_COMMERCIAL', 'food_security', 'fish_landings', 'mass', 'period_total', false, false, false,
 'Fish landings: commercial fishing', 'إنزال الأسماك: الصيد التجاري', 'Fish landed by commercial fishing during the period.',
 'الأسماك المنزلة من الصيد التجاري خلال الفترة.', 'A component of capture landings.', 'جزء من إنزال الأسماك المصيدة.', 'FISH_CAPTURE_LANDINGS'),
('FISH_VALUE_INCL_AQUACULTURE', 'food_security', 'fish_value', 'currency', 'period_total', false, false, false,
 'Fish value (including aquaculture)', 'قيمة الأسماك (تشمل الاستزراع السمكي)',
 'Value of fish production during the period, including aquaculture.', 'قيمة إنتاج الأسماك خلال الفترة بما فيها الاستزراع السمكي.',
 'Covers aquaculture while capture landings do not: never divide one by the other as a price.',
 'تشمل الاستزراع السمكي بينما لا تشمله كميات الصيد؛ فلا يُقسم أحدهما على الآخر كسعر.', NULL),
('AGRI_FISH_PRODUCTION_TOTAL', 'food_security', 'production_statement', 'mass', 'period_total', false, false, false,
 'Agriculture and fisheries production (reported)', 'إنتاج الزراعة والثروة السمكية (مُعلن)',
 'Combined agriculture and fisheries production as stated in a ministerial statement.',
 'إنتاج الزراعة والثروة السمكية مجتمعين كما ورد في تصريح وزاري.',
 'A rounded reported statement, not a table value; not comparable with the crop or fish tables.',
 'تصريح مُعلن مقرّب وليس قيمة جدولية؛ لا يُقارن بجداول المحاصيل أو الأسماك.', NULL),
-- ---------------------------------------------------------------- food security: self-sufficiency
('SELF_SUFFICIENCY_FISH', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: fish', 'الاكتفاء الذاتي: الأسماك', 'Self-sufficiency ratio for fish as stated by the source.', 'نسبة الاكتفاء الذاتي من الأسماك كما يذكرها المصدر.',
 'A dated statement; a later statement does not by itself revise an annual series.', 'تصريح مؤرخ؛ التصريح اللاحق لا يعدّل السلسلة السنوية تلقائياً.', NULL),
('SELF_SUFFICIENCY_DATES', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: dates', 'الاكتفاء الذاتي: التمور', 'Self-sufficiency ratio for dates as stated by the source.', 'نسبة الاكتفاء الذاتي من التمور كما يذكرها المصدر.',
 'A dated statement; a later statement does not by itself revise an annual series.', 'تصريح مؤرخ؛ التصريح اللاحق لا يعدّل السلسلة السنوية تلقائياً.', NULL),
('SELF_SUFFICIENCY_VEGETABLES', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: vegetables', 'الاكتفاء الذاتي: الخضروات', 'Self-sufficiency ratio for vegetables as stated by the source.', 'نسبة الاكتفاء الذاتي من الخضروات كما يذكرها المصدر.',
 'A dated statement; a later statement does not by itself revise an annual series.', 'تصريح مؤرخ؛ التصريح اللاحق لا يعدّل السلسلة السنوية تلقائياً.', NULL),
('SELF_SUFFICIENCY_EGGS', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: eggs', 'الاكتفاء الذاتي: البيض', 'Self-sufficiency ratio for eggs as stated by the source.', 'نسبة الاكتفاء الذاتي من البيض كما يذكرها المصدر.',
 'One source states "more than 95 percent": the inequality is kept, not replaced by a point value.', 'أحد المصادر يذكر "أكثر من 95%": يُحتفظ بالمتباينة ولا تُستبدل بقيمة محددة.', NULL),
('SELF_SUFFICIENCY_MILK', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: milk', 'الاكتفاء الذاتي: الحليب', 'Self-sufficiency ratio for milk as stated by the source.', 'نسبة الاكتفاء الذاتي من الحليب كما يذكرها المصدر.',
 'A dated statement without a stated reference year.', 'تصريح مؤرخ دون سنة مرجعية مذكورة.', NULL),
('SELF_SUFFICIENCY_WHITE_MEAT', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: white meat', 'الاكتفاء الذاتي: اللحوم البيضاء', 'Self-sufficiency ratio for white meat as stated by the source.', 'نسبة الاكتفاء الذاتي من اللحوم البيضاء كما يذكرها المصدر.',
 'A dated statement without a stated reference year.', 'تصريح مؤرخ دون سنة مرجعية مذكورة.', NULL),
('SELF_SUFFICIENCY_RED_MEAT', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: red meat', 'الاكتفاء الذاتي: اللحوم الحمراء', 'Self-sufficiency ratio for red meat as stated by the source.', 'نسبة الاكتفاء الذاتي من اللحوم الحمراء كما يذكرها المصدر.',
 'A dated statement without a stated reference year.', 'تصريح مؤرخ دون سنة مرجعية مذكورة.', NULL),
('SELF_SUFFICIENCY_FRUIT_EXCL_DATES', 'food_security', 'self_sufficiency', 'ratio', 'average', false, false, false,
 'Self-sufficiency: fruit excluding dates', 'الاكتفاء الذاتي: الفواكه عدا التمور', 'Self-sufficiency ratio for fruit other than dates as stated by the source.', 'نسبة الاكتفاء الذاتي من الفواكه عدا التمور كما يذكرها المصدر.',
 'A dated statement without a stated reference year.', 'تصريح مؤرخ دون سنة مرجعية مذكورة.', NULL),
-- ---------------------------------------------------------------- trade
('TRADE_MERCH_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Merchandise exports', 'الصادرات السلعية',
 'Value of goods exported: oil and gas exports, non-oil exports and re-exports.',
 'قيمة السلع المصدرة: صادرات النفط والغاز والصادرات غير النفطية وإعادة التصدير.',
 'Goods only (no services). Nominal Omani rials. Re-exports are already included: never add them again.',
 'السلع فقط دون الخدمات، بالريال العماني الاسمي. إعادة التصدير مشمولة؛ لا تُضاف مرة أخرى.', NULL),
('TRADE_OIL_GAS_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Oil and gas exports', 'صادرات النفط والغاز', 'Value of crude oil, refined oil and LNG exports.', 'قيمة صادرات النفط الخام والنفط المكرر والغاز الطبيعي المسال.',
 'A component of merchandise exports.', 'جزء من الصادرات السلعية.', 'TRADE_MERCH_EXPORTS'),
('TRADE_CRUDE_OIL_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Crude oil exports', 'صادرات النفط الخام', 'Value of crude oil exports.', 'قيمة صادرات النفط الخام.',
 'A component of oil and gas exports.', 'جزء من صادرات النفط والغاز.', 'TRADE_OIL_GAS_EXPORTS'),
('TRADE_REFINED_OIL_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Refined oil exports', 'صادرات النفط المكرر', 'Value of refined oil product exports.', 'قيمة صادرات المنتجات النفطية المكررة.',
 'A component of oil and gas exports.', 'جزء من صادرات النفط والغاز.', 'TRADE_OIL_GAS_EXPORTS'),
('TRADE_LNG_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'LNG exports', 'صادرات الغاز الطبيعي المسال', 'Value of liquefied natural gas exports.', 'قيمة صادرات الغاز الطبيعي المسال.',
 'A component of oil and gas exports.', 'جزء من صادرات النفط والغاز.', 'TRADE_OIL_GAS_EXPORTS'),
('TRADE_NON_OIL_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, true,
 'Non-oil exports', 'الصادرات غير النفطية', 'Value of domestically produced goods exported other than oil and gas.',
 'قيمة السلع المنتجة محلياً والمصدّرة عدا النفط والغاز.',
 'A component of merchandise exports. Partner values are slices of the total, not additional trade.',
 'جزء من الصادرات السلعية. قيم الشركاء أجزاء من الإجمالي وليست تجارة إضافية.', 'TRADE_MERCH_EXPORTS'),
('TRADE_NONOIL_BASE_METALS_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Non-oil exports: base metals', 'الصادرات غير النفطية: المعادن الأساسية', 'Value of non-oil exports of base metals and their articles.', 'قيمة الصادرات غير النفطية من المعادن الأساسية ومصنوعاتها.',
 'A component of non-oil exports.', 'جزء من الصادرات غير النفطية.', 'TRADE_NON_OIL_EXPORTS'),
('TRADE_NONOIL_CHEMICAL_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Non-oil exports: chemical products', 'الصادرات غير النفطية: المنتجات الكيميائية', 'Value of non-oil exports of chemical products.', 'قيمة الصادرات غير النفطية من المنتجات الكيميائية.',
 'A component of non-oil exports.', 'جزء من الصادرات غير النفطية.', 'TRADE_NON_OIL_EXPORTS'),
('TRADE_NONOIL_PLASTICS_RUBBER_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Non-oil exports: plastics and rubber', 'الصادرات غير النفطية: اللدائن والمطاط', 'Value of non-oil exports of plastics and rubber.', 'قيمة الصادرات غير النفطية من اللدائن والمطاط.',
 'A component of non-oil exports.', 'جزء من الصادرات غير النفطية.', 'TRADE_NON_OIL_EXPORTS'),
('TRADE_NONOIL_MINERAL_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Non-oil exports: mineral products', 'الصادرات غير النفطية: المنتجات المعدنية', 'Value of non-oil exports of mineral products.', 'قيمة الصادرات غير النفطية من المنتجات المعدنية.',
 'A component of non-oil exports.', 'جزء من الصادرات غير النفطية.', 'TRADE_NON_OIL_EXPORTS'),
('TRADE_NONOIL_PRECIOUS_EXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, false,
 'Non-oil exports: precious metals and stones', 'الصادرات غير النفطية: المعادن والأحجار الكريمة', 'Value of non-oil exports of precious metals and stones.', 'قيمة الصادرات غير النفطية من المعادن والأحجار الكريمة.',
 'A component of non-oil exports.', 'جزء من الصادرات غير النفطية.', 'TRADE_NON_OIL_EXPORTS'),
('TRADE_REEXPORTS', 'trade', 'merchandise_exports', 'currency', 'period_total', false, false, true,
 'Re-exports', 'إعادة التصدير', 'Value of imported goods exported again without substantial transformation.',
 'قيمة السلع المستوردة التي يعاد تصديرها دون تحويل جوهري.',
 'Already part of merchandise exports: never counted twice. Partner values are slices of the total.',
 'جزء من الصادرات السلعية؛ لا تُحسب مرتين. قيم الشركاء أجزاء من الإجمالي.', 'TRADE_MERCH_EXPORTS'),
('TRADE_MERCH_IMPORTS', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, true,
 'Recorded merchandise imports', 'الواردات السلعية المسجلة', 'Value of goods imported, as recorded by the source.',
 'قيمة السلع المستوردة كما يسجلها المصدر.',
 'Goods only (no services). Partner values are slices of the total, not additional trade.',
 'السلع فقط دون الخدمات. قيم الشركاء أجزاء من الإجمالي وليست تجارة إضافية.', NULL),
('TRADE_IMPORTS_ELECTRICAL_MACHINERY', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, false,
 'Imports: machinery and electrical equipment', 'الواردات: الآلات والمعدات الكهربائية', 'Value of imports of machinery and electrical equipment.', 'قيمة واردات الآلات والمعدات الكهربائية.',
 'A component of recorded imports.', 'جزء من الواردات السلعية المسجلة.', 'TRADE_MERCH_IMPORTS'),
('TRADE_IMPORTS_MINERAL', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, false,
 'Imports: mineral products', 'الواردات: المنتجات المعدنية', 'Value of imports of mineral products.', 'قيمة واردات المنتجات المعدنية.',
 'A component of recorded imports.', 'جزء من الواردات السلعية المسجلة.', 'TRADE_MERCH_IMPORTS'),
('TRADE_IMPORTS_BASE_METALS', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, false,
 'Imports: base metals', 'الواردات: المعادن الأساسية', 'Value of imports of base metals and their articles.', 'قيمة واردات المعادن الأساسية ومصنوعاتها.',
 'A component of recorded imports.', 'جزء من الواردات السلعية المسجلة.', 'TRADE_MERCH_IMPORTS'),
('TRADE_IMPORTS_PRECIOUS', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, false,
 'Imports: precious metals and stones', 'الواردات: المعادن والأحجار الكريمة', 'Value of imports of precious metals and stones.', 'قيمة واردات المعادن والأحجار الكريمة.',
 'A component of recorded imports.', 'جزء من الواردات السلعية المسجلة.', 'TRADE_MERCH_IMPORTS'),
('TRADE_IMPORTS_TRANSPORT_EQUIPMENT', 'trade', 'merchandise_imports', 'currency', 'period_total', false, false, false,
 'Imports: transport equipment', 'الواردات: معدات النقل', 'Value of imports of transport equipment.', 'قيمة واردات معدات النقل.',
 'A component of recorded imports.', 'جزء من الواردات السلعية المسجلة.', 'TRADE_MERCH_IMPORTS'),
('TRADE_BALANCE_REPORTED', 'trade', 'balance', 'currency', 'period_total', false, false, false,
 'Merchandise trade balance (as published)', 'الميزان التجاري السلعي (كما نُشر)',
 'Merchandise trade balance as published by the source.', 'الميزان التجاري السلعي كما نشره المصدر.',
 'Published values only. A balance the application calculates is labelled as derived and kept separate.',
 'القيم المنشورة فقط. الميزان الذي يحسبه التطبيق يُوسم بأنه مشتق ويُعرض منفصلاً.', NULL);

UPDATE indicator SET display_unit_code = 'million_m3' WHERE code IN ('WATER_PRODUCTION', 'WATER_DISTRIBUTION', 'WATER_CONSUMPTION');
UPDATE indicator SET display_unit_code = 'tonne' WHERE code = 'AGRI_CROP_PRODUCTION';
