-- OSRIP migration 0036 down: the outlook table and types, the utility indicators and scope.
-- Refused (foreign keys) while observations or import rows still use the indicators or the area.

DROP TABLE IF EXISTS outlook_item;
DROP TYPE IF EXISTS outlook_review;
DROP TYPE IF EXISTS outlook_class;
DELETE FROM indicator WHERE code IN ('WATER_SUPPLY_UTILITY', 'WATER_DELIVERED_UTILITY');
DELETE FROM area_group_member WHERE group_area_id = (SELECT id FROM area WHERE code = 'OM-GRP-NWS');
DELETE FROM area WHERE code = 'OM-GRP-NWS';
