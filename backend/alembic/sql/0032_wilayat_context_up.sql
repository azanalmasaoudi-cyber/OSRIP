-- OSRIP migration 0032: definitions for the November 2026 wilayat evidence review.
-- Definitions only (units and indicator meanings), NOT observations. Values come through the
-- reviewed import workflow (validate, approve, publish), never from a migration.

INSERT INTO unit (code, dimension, label_en, label_ar) VALUES
    ('person',       'count', 'persons',       'نسمة'),
    ('registration', 'count', 'registrations', 'سجل');

-- Population is context for the four axes (per-person comparisons), not a fifth axis.
INSERT INTO indicator (code, section, measure, dimension, value_type, requires_commodity, requires_partner, requires_flow,
                       name_en, name_ar, definition_en, definition_ar, limitation_en, limitation_ar, parent_code) VALUES
('POP_TOTAL', 'population', 'population', 'count', 'end_of_period', false, false, false,
 'Population', 'عدد السكان',
 'Population of the area at the end of the year (Omani and non-Omani), as published by the National Centre for Statistics and Information.',
 'عدد سكان المنطقة في نهاية العام (عمانيون وغير عمانيين) كما ينشره المركز الوطني للإحصاء والمعلومات.',
 'Context for per-person comparisons, not a resource statistic. A wilayat''s population is never used to share out a governorate or national total.',
 'سياق للمقارنات للفرد، وليس إحصاءً للموارد. لا يُستخدم عدد سكان الولاية لتوزيع إجمالي المحافظة أو الإجمالي الوطني.', NULL),
('POP_OMANI', 'population', 'population', 'count', 'end_of_period', false, false, false,
 'Population: Omani', 'السكان: العمانيون',
 'Omani nationals in the area at the end of the year.', 'المواطنون العمانيون في المنطقة في نهاية العام.',
 'A component of the population; never added to the total.', 'جزء من عدد السكان؛ لا يُضاف إلى الإجمالي.', 'POP_TOTAL'),
('POP_NON_OMANI', 'population', 'population', 'count', 'end_of_period', false, false, false,
 'Population: non-Omani', 'السكان: غير العمانيين',
 'Residents who are not Omani nationals in the area at the end of the year.', 'المقيمون من غير المواطنين العمانيين في المنطقة في نهاية العام.',
 'A component of the population; never added to the total.', 'جزء من عدد السكان؛ لا يُضاف إلى الإجمالي.', 'POP_TOTAL'),
('TRADE_NEW_COMMERCIAL_REGISTRATIONS', 'trade', 'new_registrations', 'count', 'period_total', false, false, false,
 'New commercial registrations', 'السجلات التجارية الجديدة',
 'Commercial registrations newly issued during the period, as announced by the Ministry of Commerce, Industry and Investment Promotion.',
 'السجلات التجارية الصادرة حديثاً خلال الفترة كما تعلنها وزارة التجارة والصناعة وترويج الاستثمار.',
 'Business registrations, not merchandise trade. New registrations are neither active registrations nor the cumulative stock; a year, a quarter and a year to date are never added together.',
 'سجلات أعمال وليست تجارة سلعية. السجلات الجديدة ليست السجلات النشطة ولا الرصيد التراكمي؛ ولا تُجمع السنة والربع والفترة منذ بداية العام معاً.', NULL),
('TRADE_COMMERCIAL_REGISTRATIONS_STOCK', 'trade', 'registrations_stock', 'count', 'end_of_period', false, false, false,
 'Commercial registrations on record', 'السجلات التجارية القائمة',
 'Commercial registrations on record at the end of the period (a cumulative stock), as announced by the ministry.',
 'السجلات التجارية المسجلة في نهاية الفترة (رصيد تراكمي) كما تعلنها الوزارة.',
 'A stock at a date; never added to new registrations or compared with them as if it were a flow.',
 'رصيد في تاريخ محدد؛ لا يُضاف إلى السجلات الجديدة ولا يُقارن بها كأنه تدفق.', NULL);
