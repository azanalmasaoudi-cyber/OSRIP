-- OSRIP migration 0035 down: the honey production definitions. Refused (foreign keys) while
-- observations or import rows still use them.

DELETE FROM indicator WHERE code = 'AGRI_PROD_HONEY';
DELETE FROM unit WHERE code = 'kg';
