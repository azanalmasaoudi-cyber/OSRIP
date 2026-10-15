-- OSRIP migration 0002: definitional reference rows.
-- These are definitions (units, indicator meanings, a national area identity and
-- provisional commodity names), NOT observations or statistics. Arabic labels
-- require review by a qualified Arabic-speaking team member before release.

INSERT INTO unit (code, dimension, label_en, label_ar) VALUES
    ('GWh',        'energy',   'gigawatt-hour',        'جيجاواط ساعة'),
    ('MW',         'power',    'megawatt',             'ميجاواط'),
    ('million_m3', 'volume',   'million cubic metres', 'مليون متر مكعب'),
    ('tonne',      'mass',     'tonne',                'طن'),
    ('OMR',        'currency', 'Omani rial (nominal)', 'ريال عماني (اسمي)'),
    ('subscriber', 'count',    'subscribers',          'مشترك'),
    ('percent',    'ratio',    'percent',              'نسبة مئوية');

INSERT INTO indicator (code, section, measure, dimension, value_type,
                       requires_commodity, requires_partner, requires_flow,
                       name_en, name_ar, definition_en, definition_ar) VALUES
    ('ELEC_GENERATION', 'electricity', 'generation', 'energy', 'period_total', false, false, false,
     'Electricity generation', 'توليد الكهرباء',
     'Electrical energy generated during the period. Not a measure of consumption.',
     'الطاقة الكهربائية المولدة خلال الفترة. ليست مقياساً للاستهلاك.'),
    ('ELEC_CONSUMPTION', 'electricity', 'consumption', 'energy', 'period_total', false, false, false,
     'Electricity consumption', 'استهلاك الكهرباء',
     'Electrical energy consumed during the period, as defined by the source.',
     'الطاقة الكهربائية المستهلكة خلال الفترة وفق تعريف المصدر.'),
    ('ELEC_INSTALLED_CAPACITY', 'electricity', 'installed_capacity', 'power', 'end_of_period', false, false, false,
     'Installed capacity', 'القدرة المركبة',
     'Installed generating capacity at the end of the period. Must not be summed as energy.',
     'القدرة التوليدية المركبة في نهاية الفترة. لا تُجمع كطاقة.'),
    ('ELEC_PEAK_DEMAND', 'electricity', 'peak_demand', 'power', 'maximum', false, false, false,
     'Peak demand', 'ذروة الطلب',
     'Maximum load recorded in the period. Must not be summed across periods.',
     'أقصى حمل مسجل خلال الفترة. لا يُجمع عبر الفترات.'),
    ('ELEC_SUBSCRIBERS', 'electricity', 'connections', 'count', 'end_of_period', false, false, false,
     'Electricity subscribers', 'مشتركو الكهرباء',
     'Subscriber accounts at the end of the period, as defined by the source.',
     'حسابات المشتركين في نهاية الفترة وفق تعريف المصدر.'),
    ('WATER_PRODUCTION', 'water', 'production', 'volume', 'period_total', false, false, false,
     'Water production', 'إنتاج المياه',
     'Water produced during the period for the stated service area.',
     'المياه المنتجة خلال الفترة لمنطقة الخدمة المحددة.'),
    ('WATER_CONSUMPTION', 'water', 'consumption', 'volume', 'period_total', false, false, false,
     'Water consumption', 'استهلاك المياه',
     'Water consumption as defined by the source (e.g. billed). Not physical delivery or leakage.',
     'استهلاك المياه وفق تعريف المصدر (مثل المفوتر). ليس التوصيل الفعلي ولا التسرب.'),
    ('WATER_SUBSCRIBERS', 'water', 'connections', 'count', 'end_of_period', false, false, false,
     'Water subscribers', 'مشتركو المياه',
     'Subscriber accounts at the end of the period, as defined by the source.',
     'حسابات المشتركين في نهاية الفترة وفق تعريف المصدر.'),
    ('FOOD_PRODUCTION', 'food_security', 'production', 'mass', 'period_total', true, false, false,
     'Commodity production', 'إنتاج السلعة',
     'Domestic production of a mapped commodity in its registered product form.',
     'الإنتاج المحلي لسلعة مطابقة بشكلها المسجل.'),
    ('FOOD_STOCK_INCREASE', 'food_security', 'stock_increase', 'mass', 'period_total', true, false, false,
     'Stock increase', 'الزيادة في المخزون',
     'Increase in stocks during the period. Unknown values stay unknown, never zero.',
     'الزيادة في المخزون خلال الفترة. القيم غير المعروفة تبقى غير معروفة ولا تُعد صفراً.'),
    ('TRADE_QUANTITY', 'trade', 'trade_quantity', 'mass', 'period_total', true, false, true,
     'Trade quantity', 'كمية التجارة',
     'Physical quantity traded for a commodity and flow; partner optional.',
     'الكمية المادية المتداولة لسلعة واتجاه تجاري؛ الشريك اختياري.'),
    ('TRADE_VALUE', 'trade', 'trade_value', 'currency', 'period_total', true, false, true,
     'Trade value', 'قيمة التجارة',
     'Nominal monetary value traded, with the source valuation basis preserved.',
     'القيمة النقدية الاسمية المتداولة مع الحفاظ على أساس التقييم في المصدر.');

INSERT INTO area (code, level, name_en, name_ar) VALUES
    ('OM', 'national', 'Oman (national)', 'عُمان (وطني)');

-- Provisional demonstration commodities (booklet 1.4). Classification is not yet
-- mapped, so mapping_status stays 'provisional' and no trade codes are asserted.
INSERT INTO commodity (code, name_en, name_ar, product_form, quantity_unit_id, mapping_status)
SELECT c.code, c.name_en, c.name_ar, 'to be determined', u.id, 'provisional'
FROM (VALUES ('WHEAT', 'Wheat', 'القمح'),
             ('RICE', 'Rice', 'الأرز'),
             ('TOMATOES', 'Tomatoes', 'الطماطم')) AS c(code, name_en, name_ar)
CROSS JOIN unit u WHERE u.code = 'tonne';

-- Fictional partners for synthetic fixtures only (booklet 4.3).
INSERT INTO partner (code, name_en, name_ar, is_fictional) VALUES
    ('PARTNER_A', 'Partner A (fictional)', 'الشريك أ (افتراضي)', true),
    ('PARTNER_B', 'Partner B (fictional)', 'الشريك ب (افتراضي)', true),
    ('PARTNER_C', 'Partner C (fictional)', 'الشريك ج (افتراضي)', true);
