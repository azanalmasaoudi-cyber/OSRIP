-- OSRIP migration 0035: honey production, as the Statistical Year Book 2026 (Table 4-5) publishes
-- it by governorate. Definitions only (a unit and an indicator), NOT observations: values come
-- through the reviewed import workflow (validate, approve, publish), never from a migration.

INSERT INTO unit (code, dimension, label_en, label_ar) VALUES
    ('kg', 'mass', 'kilograms', 'كيلوغرام');

INSERT INTO indicator (code, section, measure, dimension, value_type, requires_commodity, requires_partner, requires_flow,
                       name_en, name_ar, definition_en, definition_ar, limitation_en, limitation_ar, parent_code) VALUES
('AGRI_PROD_HONEY', 'food_security', 'production', 'mass', 'period_total', false, false, false,
 'Honey production', 'إنتاج العسل',
 'Quantity of honey produced from beehives during the year, in kilograms, as published by the National Centre for Statistics and Information.',
 'كمية العسل المنتجة من خلايا النحل خلال العام بالكيلوغرام، كما ينشرها المركز الوطني للإحصاء والمعلومات.',
 'A partial agricultural indicator, not a measure of food security on its own; quantities are not prices, consumption or self-sufficiency.',
 'مؤشر زراعي جزئي وليس مقياساً للأمن الغذائي بمفرده؛ الكميات ليست أسعاراً ولا استهلاكاً ولا اكتفاءً ذاتياً.', NULL);
