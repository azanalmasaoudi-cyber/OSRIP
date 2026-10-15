-- OSRIP migration 0005: sourced administrative registry, forecast predictions.
-- Booklet 3.11 (areas as reference entities; forecasts with horizon, predicted value
-- and supported interval), 3.14 (maps show only records whose coverage is known),
-- 2.4 and 4.6 (chronological forecast evaluation against a last-value baseline).
--
-- The registry holds identities, names and parent relationships only. It holds no
-- coordinates, centroids or boundary geometry (none has been sourced under a
-- suitable licence; see docs/SPEC_CONFLICTS.md C8, C13).

-- ================================================================== registry references
CREATE TABLE geo_reference (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code             text NOT NULL UNIQUE,
    publisher        text NOT NULL,
    title            text NOT NULL,
    url              text NOT NULL,
    language         text NOT NULL CONSTRAINT ck_geo_reference_language CHECK (language IN ('en', 'ar')),
    published_on     date,                 -- date the item was issued, when the page states it
    page_updated_on  date,                 -- "last updated" date shown on the page, when stated
    accessed_on      date NOT NULL,
    supports         text NOT NULL         -- what this reference is used to establish
);

ALTER TABLE area ADD COLUMN iso_3166_2 text UNIQUE
    CONSTRAINT ck_area_iso_3166_2 CHECK (iso_3166_2 ~ '^OM-[A-Z]{2}$');
-- 'iso_3166_2': the code is the ISO 3166-2 subdivision code; 'osrip': assigned by
-- this project, stable, never reused or renumbered, and not an official identifier.
ALTER TABLE area ADD COLUMN code_authority text NOT NULL DEFAULT 'osrip'
    CONSTRAINT ck_area_code_authority CHECK (code_authority IN ('osrip', 'iso_3166_2'));
ALTER TABLE area ADD COLUMN verified_on date;
ALTER TABLE area ADD COLUMN registry_note_en text;
ALTER TABLE area ADD COLUMN registry_note_ar text;
ALTER TABLE area ADD CONSTRAINT ck_area_iso_code_matches
    CHECK (code_authority <> 'iso_3166_2' OR code = iso_3166_2);
ALTER TABLE area ADD CONSTRAINT ck_area_admin_level_is_verified
    CHECK (level NOT IN ('governorate', 'wilayat') OR verified_on IS NOT NULL);

-- Which reference supports which registry entry, and for what.
CREATE TABLE area_reference (
    area_id           uuid NOT NULL REFERENCES area (id),
    geo_reference_id  uuid NOT NULL REFERENCES geo_reference (id),
    supports          text[] NOT NULL CONSTRAINT ck_area_reference_supports CHECK (
        cardinality(supports) > 0
        AND supports <@ ARRAY['existence', 'name_en', 'name_ar', 'parent', 'iso_code']::text[]
    ),
    PRIMARY KEY (area_id, geo_reference_id)
);

-- Parent levels: governorate -> national, wilayat -> governorate. A service area may
-- sit under any administrative area or none (service areas need not follow them).
CREATE FUNCTION area_hierarchy_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_level area_level;
BEGIN
    IF NEW.parent_id IS NOT NULL THEN
        SELECT level INTO parent_level FROM area WHERE id = NEW.parent_id;
    END IF;
    IF (NEW.level = 'governorate' AND parent_level IS DISTINCT FROM 'national')
       OR (NEW.level = 'wilayat' AND parent_level IS DISTINCT FROM 'governorate') THEN
        RAISE EXCEPTION 'area % (%) has a parent of level %', NEW.code, NEW.level, parent_level
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_area_hierarchy';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_area_hierarchy
    BEFORE INSERT OR UPDATE ON area
    FOR EACH ROW EXECUTE FUNCTION area_hierarchy_check();

-- Completeness checks of the registry against a stated authoritative count.
CREATE TABLE area_registry_verification (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    verified_on            date NOT NULL,
    expected_governorates  integer NOT NULL,
    expected_wilayats      integer NOT NULL,
    basis_en               text NOT NULL,
    basis_ar               text NOT NULL,
    reference_codes        text[] NOT NULL
);

CREATE TRIGGER trg_area_registry_verification_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON area_registry_verification
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete();

-- ------------------------------------------------------------------ references (accessed 2026-09-25)
INSERT INTO geo_reference (code, publisher, title, url, language, published_on, page_updated_on, accessed_on, supports) VALUES
    ('MOF_REGIONS_EN', 'Ministry of Finance, Sultanate of Oman', 'Oman by Region',
     'https://www.fm.gov.om/en/about-oman/state/oman-by-region/', 'en', NULL, '2026-09-21', '2026-09-25',
     'English names of the 11 governorates and 61 wilayats, and the governorate of each wilayat.'),
    ('MOF_REGIONS_AR', 'وزارة المالية، سلطنة عُمان', 'عُمان حسب المحافظات',
     'https://www.fm.gov.om/ar/about-oman/state/oman-by-region/', 'ar', NULL, '2026-04-29', '2026-09-25',
     'Arabic names of the 11 governorates and 61 wilayats, and the governorate of each wilayat.'),
    ('MOI_2022_NEW_WILAYATS', 'وزارة الداخلية، سلطنة عُمان',
     'وزير الداخلية يصدر بياناً بتمثيل ولايتي الجبل الأخضر وسناو في مجلس الشورى',
     'https://www.moi.gov.om/ar-om/news/%D9%88%D8%B2%D9%8A%D8%B1-%D8%A7%D9%84%D8%AF%D8%A7%D8%AE%D9%84%D9%8A%D8%A9-%D9%8A%D8%B5%D8%AF%D8%B1-%D8%A8%D9%8A%D8%A7%D9%86%D8%A7%D9%8B-%D8%A8%D8%AA%D9%85%D8%AB%D9%8A%D9%84-%D9%88%D9%84%D8%A7%D9%8A%D8%AA%D9%8A-%D8%A7%D9%84%D8%AC%D8%A8%D9%84-%D8%A7%D9%84%D8%A3%D8%AE%D8%B6%D8%B1-%D9%88-%E2%80%8E%D8%B3%D9%86%D8%A7%D9%88-%D9%81%D9%8A-%D9%85%D8%AC%D9%84%D8%B3-%D8%A7%D9%84%D8%B4%D9%88%D8%B1%D9%89-20220619151047327',
     'ar', '2022-06-19', NULL, '2026-09-25',
     'Existence, Arabic names and governorates of the wilayats of Al Jabal Al Akhdar (A''Dakhiliya) and Sinaw (A''Sharqiyah North).'),
    ('ONA_2022_NEW_WILAYATS', 'Oman News Agency', 'Al Jabal Al Akhdar and Sinaw given wilayat status',
     'https://omannews.gov.om/topics/en/79/show/110798', 'en', '2022-11-16', NULL, '2026-09-25',
     'English names of Al Jabal Al Akhdar and Sinaw, and the national total of 63 wilayats after the change.'),
    ('ISO_3166_2_OM_SECONDARY', 'Wikipedia (transcription of the ISO 3166 Online Browsing Platform)',
     'ISO 3166-2:OM', 'https://en.wikipedia.org/wiki/ISO_3166-2:OM', 'en', NULL, NULL, '2026-09-25',
     'ISO 3166-2 codes of the 11 governorates (last ISO change stated as 2015-11-27). Secondary source: the ISO platform itself requires accepting its terms of use and was not consulted.');

-- ------------------------------------------------------------------ governorates
INSERT INTO area (code, level, parent_id, name_en, name_ar, iso_3166_2, code_authority, verified_on)
SELECT g.code, 'governorate', om.id, g.name_en, g.name_ar, g.code, 'iso_3166_2', DATE '2026-09-25'
FROM (VALUES
    ('OM-MU', 'Musandam', 'مسندم'),
    ('OM-BU', 'Al Buraimi', 'البريمي'),
    ('OM-BS', 'Al Batinah North', 'شمال الباطنة'),
    ('OM-BJ', 'Al Batinah South', 'جنوب الباطنة'),
    ('OM-MA', 'Muscat', 'مسقط'),
    ('OM-ZA', 'A''Dhahirah', 'الظاهرة'),
    ('OM-DA', 'A''Dakhiliya', 'الداخلية'),
    ('OM-SS', 'A''Sharqiyah North', 'شمال الشرقية'),
    ('OM-SJ', 'A''Sharqiyah South', 'جنوب الشرقية'),
    ('OM-WU', 'Al Wusta', 'الوسطى'),
    ('OM-ZU', 'Dhofar', 'ظفار')
) AS g(code, name_en, name_ar)
CROSS JOIN (SELECT id FROM area WHERE code = 'OM') AS om;

-- ------------------------------------------------------------------ wilayats
-- Codes OM-<governorate>-NN are assigned by OSRIP in the order of the Ministry of
-- Finance listing; wilayats established later take the next free number.
INSERT INTO area (code, level, parent_id, name_en, name_ar, code_authority, verified_on)
SELECT w.code, 'wilayat', gov.id, w.name_en, w.name_ar, 'osrip', DATE '2026-09-25'
FROM (VALUES
    ('OM-MU', 'OM-MU-01', 'Khasab', 'خصب'),
    ('OM-MU', 'OM-MU-02', 'Bukha', 'بخا'),
    ('OM-MU', 'OM-MU-03', 'Dibba', 'دبا'),
    ('OM-MU', 'OM-MU-04', 'Madha', 'مدحاء'),
    ('OM-BU', 'OM-BU-01', 'Al Buraimi', 'البريمي'),
    ('OM-BU', 'OM-BU-02', 'Al Sunaynah', 'السنينة'),
    ('OM-BU', 'OM-BU-03', 'Mahdah', 'محضة'),
    ('OM-BS', 'OM-BS-01', 'Sohar', 'صحار'),
    ('OM-BS', 'OM-BS-02', 'Al Khabourah', 'الخابورة'),
    ('OM-BS', 'OM-BS-03', 'Al Suwaiq', 'السويق'),
    ('OM-BS', 'OM-BS-04', 'Liwa', 'ليوا'),
    ('OM-BS', 'OM-BS-05', 'Saham', 'صحم'),
    ('OM-BS', 'OM-BS-06', 'Shinas', 'شناص'),
    ('OM-BJ', 'OM-BJ-01', 'Al Rustaq', 'الرستاق'),
    ('OM-BJ', 'OM-BJ-02', 'Al Awabi', 'العوابي'),
    ('OM-BJ', 'OM-BJ-03', 'Al Musannah', 'المصنعة'),
    ('OM-BJ', 'OM-BJ-04', 'Barka', 'بركاء'),
    ('OM-BJ', 'OM-BJ-05', 'Nakhal', 'نخل'),
    ('OM-BJ', 'OM-BJ-06', 'Wadi Al Ma''awil', 'وادي المعاول'),
    ('OM-MA', 'OM-MA-01', 'Muscat', 'مسقط'),
    ('OM-MA', 'OM-MA-02', 'Al Amirat', 'العامرات'),
    ('OM-MA', 'OM-MA-03', 'A''Seeb', 'السيب'),
    ('OM-MA', 'OM-MA-04', 'Boushar', 'بوشر'),
    ('OM-MA', 'OM-MA-05', 'Matrah', 'مطرح'),
    ('OM-MA', 'OM-MA-06', 'Qurayyat', 'قريات'),
    ('OM-ZA', 'OM-ZA-01', 'Ibri', 'عبري'),
    ('OM-ZA', 'OM-ZA-02', 'Dhank', 'ضنك'),
    ('OM-ZA', 'OM-ZA-03', 'Yankul', 'ينقل'),
    ('OM-DA', 'OM-DA-01', 'Nizwa', 'نزوى'),
    ('OM-DA', 'OM-DA-02', 'Adam', 'أدم'),
    ('OM-DA', 'OM-DA-03', 'Al Hamra', 'الحمراء'),
    ('OM-DA', 'OM-DA-04', 'Bahla', 'بهلا'),
    ('OM-DA', 'OM-DA-05', 'Bid Bid', 'بدبد'),
    ('OM-DA', 'OM-DA-06', 'Izki', 'إزكي'),
    ('OM-DA', 'OM-DA-07', 'Manah', 'منح'),
    ('OM-DA', 'OM-DA-08', 'Samail', 'سمائل'),
    ('OM-DA', 'OM-DA-09', 'Al Jabal Al Akhdar', 'الجبل الأخضر'),
    ('OM-SS', 'OM-SS-01', 'Ibra', 'إبرا'),
    ('OM-SS', 'OM-SS-02', 'Bidiya', 'بدية'),
    ('OM-SS', 'OM-SS-03', 'Al Kabil', 'القابل'),
    ('OM-SS', 'OM-SS-04', 'Al Mudhaibi', 'المضيبي'),
    ('OM-SS', 'OM-SS-05', 'Dima W''attayeen', 'دما والطايين'),
    ('OM-SS', 'OM-SS-06', 'Wadi Bani Khalid', 'وادي بني خالد'),
    ('OM-SS', 'OM-SS-07', 'Sinaw', 'سناو'),
    ('OM-SJ', 'OM-SJ-01', 'Sur', 'صور'),
    ('OM-SJ', 'OM-SJ-02', 'Al Kamil W''al Wafi', 'الكامل والوافي'),
    ('OM-SJ', 'OM-SJ-03', 'Jaalan Bani Bu Ali', 'جعلان بني بوعلي'),
    ('OM-SJ', 'OM-SJ-04', 'Jaalan Bani Bu Hassan', 'جعلان بني بوحسن'),
    ('OM-SJ', 'OM-SJ-05', 'Masirah', 'مصيرة'),
    ('OM-WU', 'OM-WU-01', 'Haima', 'هيما'),
    ('OM-WU', 'OM-WU-02', 'Al Jazer', 'الجازر'),
    ('OM-WU', 'OM-WU-03', 'Duqm', 'الدقم'),
    ('OM-WU', 'OM-WU-04', 'Mahout', 'محوت'),
    ('OM-ZU', 'OM-ZU-01', 'Salalah', 'صلالة'),
    ('OM-ZU', 'OM-ZU-02', 'Al Mazyona', 'المزيونة'),
    ('OM-ZU', 'OM-ZU-03', 'Dhalkut', 'ضلكوت'),
    ('OM-ZU', 'OM-ZU-04', 'Mirbat', 'مرباط'),
    ('OM-ZU', 'OM-ZU-05', 'Muqshin', 'مقشن'),
    ('OM-ZU', 'OM-ZU-06', 'Rakhyut', 'رخيوت'),
    ('OM-ZU', 'OM-ZU-07', 'Sadah', 'سدح'),
    ('OM-ZU', 'OM-ZU-08', 'Shalim and the Hallaniyat Islands', 'جزر شليم والحلانيات'),
    ('OM-ZU', 'OM-ZU-09', 'Taqah', 'طاقة'),
    ('OM-ZU', 'OM-ZU-10', 'Thumrait', 'ثمريت')
) AS w(gov_code, code, name_en, name_ar)
JOIN area gov ON gov.code = w.gov_code;

UPDATE area SET
    registry_note_en = 'Established as a wilayat in 2022 (Ministry of Interior, Oman News Agency). Not in the Ministry of Finance listing consulted. Its establishment date is not recorded here because the decree was not consulted.',
    registry_note_ar = 'أُنشئت ولايةً في عام 2022 (وزارة الداخلية، وكالة الأنباء العُمانية). لم ترد في قائمة وزارة المالية المرجوع إليها. لا يُسجَّل هنا تاريخ إنشائها لعدم الرجوع إلى المرسوم.'
WHERE code IN ('OM-DA-09', 'OM-SS-07');

-- ------------------------------------------------------------------ area references
INSERT INTO area_reference (area_id, geo_reference_id, supports)
SELECT a.id, r.id, ARRAY['existence', 'name_en', 'parent']
FROM area a CROSS JOIN geo_reference r
WHERE r.code = 'MOF_REGIONS_EN' AND a.level IN ('governorate', 'wilayat') AND a.code NOT IN ('OM-DA-09', 'OM-SS-07');

INSERT INTO area_reference (area_id, geo_reference_id, supports)
SELECT a.id, r.id, ARRAY['existence', 'name_ar', 'parent']
FROM area a CROSS JOIN geo_reference r
WHERE r.code = 'MOF_REGIONS_AR' AND a.level IN ('governorate', 'wilayat') AND a.code NOT IN ('OM-DA-09', 'OM-SS-07');

INSERT INTO area_reference (area_id, geo_reference_id, supports)
SELECT a.id, r.id, ARRAY['existence', 'name_ar', 'parent']
FROM area a CROSS JOIN geo_reference r
WHERE r.code = 'MOI_2022_NEW_WILAYATS' AND a.code IN ('OM-DA-09', 'OM-SS-07');

INSERT INTO area_reference (area_id, geo_reference_id, supports)
SELECT a.id, r.id, ARRAY['existence', 'name_en']
FROM area a CROSS JOIN geo_reference r
WHERE r.code = 'ONA_2022_NEW_WILAYATS' AND a.code IN ('OM-DA-09', 'OM-SS-07');

INSERT INTO area_reference (area_id, geo_reference_id, supports)
SELECT a.id, r.id, ARRAY['iso_code']
FROM area a CROSS JOIN geo_reference r
WHERE r.code = 'ISO_3166_2_OM_SECONDARY' AND a.level = 'governorate';

INSERT INTO area_registry_verification
    (verified_on, expected_governorates, expected_wilayats, basis_en, basis_ar, reference_codes)
VALUES ('2026-09-25', 11, 63,
    'The Ministry of Finance listing (English and Arabic) names 11 governorates and 61 wilayats. The Ministry of Interior (19 June 2022) placed the new wilayats of Al Jabal Al Akhdar in A''Dakhiliya and Sinaw in A''Sharqiyah North, and the Oman News Agency (16 November 2022) states that this raised the total to 63 wilayats. 61 + 2 = 63.',
    'تذكر قائمة وزارة المالية (بالعربية والإنجليزية) 11 محافظة و61 ولاية. ووضعت وزارة الداخلية (19 يونيو 2022) ولاية الجبل الأخضر في محافظة الداخلية وولاية سناو في محافظة شمال الشرقية، وذكرت وكالة الأنباء العُمانية (16 نوفمبر 2022) أن ذلك رفع العدد إلى 63 ولاية. 61 + 2 = 63.',
    ARRAY['MOF_REGIONS_EN', 'MOF_REGIONS_AR', 'MOI_2022_NEW_WILAYATS', 'ONA_2022_NEW_WILAYATS']);

-- ================================================================== forecast predictions
-- One row per model and held-out date of a forecast analysis_run. The experiment
-- definition (target, horizon, splits, baseline, candidate, interval method) is the
-- run's parameters, written in the same transaction before any prediction row.
CREATE TABLE forecast_prediction (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_run_id      uuid NOT NULL,
    data_mode            data_mode NOT NULL,
    model                text NOT NULL CONSTRAINT ck_forecast_prediction_model
        CHECK (model IN ('baseline_last_value', 'candidate_linear_trend')),
    fold                 integer NOT NULL CONSTRAINT ck_forecast_prediction_fold CHECK (fold >= 1),
    horizon_steps        integer NOT NULL CONSTRAINT ck_forecast_prediction_horizon CHECK (horizon_steps >= 1),
    training_start       date NOT NULL,
    training_end         date NOT NULL,
    training_size        integer NOT NULL CONSTRAINT ck_forecast_prediction_training_size CHECK (training_size >= 1),
    target_period_start  date NOT NULL,
    target_period_end    date NOT NULL,
    predicted            numeric NOT NULL,
    actual               numeric NOT NULL,
    error                numeric NOT NULL,     -- actual - predicted, in the indicator's unit
    interval_lower       numeric,              -- NULL: no interval method is supported (see run parameters)
    interval_upper       numeric,
    CONSTRAINT fk_forecast_prediction_run FOREIGN KEY (analysis_run_id, data_mode)
        REFERENCES analysis_run (id, data_mode),
    CONSTRAINT ck_forecast_prediction_chronology CHECK (training_end < target_period_start),
    CONSTRAINT ck_forecast_prediction_error CHECK (error = actual - predicted),
    CONSTRAINT ck_forecast_prediction_interval CHECK ((interval_lower IS NULL) = (interval_upper IS NULL)),
    CONSTRAINT uq_forecast_prediction UNIQUE (analysis_run_id, model, target_period_start)
);

CREATE TRIGGER trg_forecast_prediction_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON forecast_prediction
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete();

CREATE INDEX ix_area_parent ON area (parent_id);
CREATE INDEX ix_observation_area ON observation (area_id);
