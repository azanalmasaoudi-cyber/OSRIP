-- OSRIP migration 0004: indicator limitations, frozen report content.
-- Booklet 3.5-3.8 (interpretation limits), 3.12 (reports freeze their inputs).

-- ------------------------------------------------------------------ indicator limitations
-- What each indicator must NOT be read as. Shown beside every value and export.
ALTER TABLE indicator ADD COLUMN limitation_en text NOT NULL DEFAULT '';
ALTER TABLE indicator ADD COLUMN limitation_ar text NOT NULL DEFAULT '';

UPDATE indicator SET
    limitation_en = CASE code
        WHEN 'ELEC_GENERATION' THEN 'Generation is energy produced (GWh), not consumption. It includes station use and losses and cannot be read as household or sector demand.'
        WHEN 'ELEC_CONSUMPTION' THEN 'Consumption as defined by the source (e.g. billed). It is energy (GWh), not load (MW), and depends on the coverage of the source.'
        WHEN 'ELEC_INSTALLED_CAPACITY' THEN 'Capacity is power (MW) at the end of the period. It is never summed across periods or compared with energy (GWh).'
        WHEN 'ELEC_PEAK_DEMAND' THEN 'Peak demand is the highest load (MW) in the period. It is not summed across periods and is not energy use.'
        WHEN 'ELEC_SUBSCRIBERS' THEN 'Accounts at the end of the period, not people or households. Use per subscriber needs matching coverage and period.'
        WHEN 'WATER_PRODUCTION' THEN 'Water produced for a service area. It is not consumption, and production minus consumption is not leakage.'
        WHEN 'WATER_CONSUMPTION' THEN 'Consumption as defined by the source (e.g. billed). It is not physical delivery, and no leakage estimate can be derived from it.'
        WHEN 'WATER_SUBSCRIBERS' THEN 'Accounts at the end of the period, not people or households. Use per subscriber needs matching coverage and period.'
        WHEN 'FOOD_PRODUCTION' THEN 'Production of one mapped commodity in its registered product form. It is not a complete food-security measure.'
        WHEN 'FOOD_STOCK_INCREASE' THEN 'Change in stocks. Unknown values stay unknown; a zero change is used only as a declared assumption.'
        WHEN 'TRADE_QUANTITY' THEN 'Physical quantity for one commodity and flow. Domestic exports and re-exports are different flows and are not merged.'
        WHEN 'TRADE_VALUE' THEN 'Nominal monetary value. It is not a retail price, a profit or a cost to consumers.'
        ELSE ''
    END,
    limitation_ar = CASE code
        WHEN 'ELEC_GENERATION' THEN 'التوليد طاقة منتجة (جيجاواط ساعة) وليس استهلاكاً. يشمل استهلاك المحطات والفواقد ولا يُقرأ طلباً للأسر أو القطاعات.'
        WHEN 'ELEC_CONSUMPTION' THEN 'الاستهلاك وفق تعريف المصدر (مثل المفوتر). هو طاقة (جيجاواط ساعة) لا حمل (ميجاواط)، ويعتمد على تغطية المصدر.'
        WHEN 'ELEC_INSTALLED_CAPACITY' THEN 'القدرة قوة (ميجاواط) في نهاية الفترة. لا تُجمع عبر الفترات ولا تُقارن بالطاقة (جيجاواط ساعة).'
        WHEN 'ELEC_PEAK_DEMAND' THEN 'ذروة الطلب أعلى حمل (ميجاواط) في الفترة. لا تُجمع عبر الفترات وليست استهلاكاً للطاقة.'
        WHEN 'ELEC_SUBSCRIBERS' THEN 'حسابات في نهاية الفترة، لا أشخاص ولا أسر. يتطلب حساب الاستخدام لكل مشترك تطابق التغطية والفترة.'
        WHEN 'WATER_PRODUCTION' THEN 'مياه منتجة لمنطقة خدمة. ليست استهلاكاً، والفرق بين الإنتاج والاستهلاك ليس تسرباً.'
        WHEN 'WATER_CONSUMPTION' THEN 'الاستهلاك وفق تعريف المصدر (مثل المفوتر). ليس التوصيل الفعلي، ولا يمكن استنتاج التسرب منه.'
        WHEN 'WATER_SUBSCRIBERS' THEN 'حسابات في نهاية الفترة، لا أشخاص ولا أسر. يتطلب حساب الاستخدام لكل مشترك تطابق التغطية والفترة.'
        WHEN 'FOOD_PRODUCTION' THEN 'إنتاج سلعة مطابقة واحدة بشكلها المسجل. ليس مقياساً كاملاً للأمن الغذائي.'
        WHEN 'FOOD_STOCK_INCREASE' THEN 'التغير في المخزون. القيم غير المعروفة تبقى غير معروفة، ولا يُستخدم التغير الصفري إلا افتراضاً معلناً.'
        WHEN 'TRADE_QUANTITY' THEN 'كمية مادية لسلعة واتجاه تجاري واحد. الصادرات المحلية وإعادة التصدير اتجاهان مختلفان لا يُدمجان.'
        WHEN 'TRADE_VALUE' THEN 'قيمة نقدية اسمية. ليست سعر تجزئة ولا ربحاً ولا تكلفة على المستهلك.'
        ELSE ''
    END;

-- ------------------------------------------------------------------ reports
-- A report stores the exact inputs and results it was generated from, so a later
-- publication cannot change it (booklet 3.9: "the old report remains associated
-- with its original inputs").
ALTER TABLE report ADD COLUMN section section_code;
ALTER TABLE report ADD COLUMN assumptions jsonb NOT NULL DEFAULT '{}';
ALTER TABLE report ADD COLUMN content jsonb;
ALTER TABLE report ADD CONSTRAINT ck_report_generated_has_content CHECK (generated_at IS NULL OR content IS NOT NULL);

-- Generated reports are immutable apart from their visibility.
CREATE FUNCTION report_frozen_after_generation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.generated_at IS NOT NULL AND (
        NEW.content IS DISTINCT FROM OLD.content
        OR NEW.filters IS DISTINCT FROM OLD.filters
        OR NEW.assumptions IS DISTINCT FROM OLD.assumptions
        OR NEW.data_mode IS DISTINCT FROM OLD.data_mode
        OR NEW.section IS DISTINCT FROM OLD.section
        OR NEW.generated_at IS DISTINCT FROM OLD.generated_at
    ) THEN
        RAISE EXCEPTION 'a generated report is frozen'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_report_frozen';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_report_frozen
    BEFORE UPDATE ON report
    FOR EACH ROW EXECUTE FUNCTION report_frozen_after_generation();

CREATE INDEX ix_recommendation_run ON recommendation (analysis_run_id);
CREATE INDEX ix_recommendation_review_rec ON recommendation_review (recommendation_id, id);
