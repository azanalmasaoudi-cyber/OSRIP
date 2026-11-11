-- OSRIP migration 0032 down: the definitions added for the wilayat evidence review. Refused
-- (foreign keys) while observations or import rows still use them; the 'population' value of
-- section_code stays, since PostgreSQL cannot drop an enum value.

DELETE FROM indicator WHERE code IN (
    'POP_OMANI', 'POP_NON_OMANI', 'POP_TOTAL',
    'TRADE_NEW_COMMERCIAL_REGISTRATIONS', 'TRADE_COMMERCIAL_REGISTRATIONS_STOCK'
);
DELETE FROM unit WHERE code IN ('person', 'registration');
