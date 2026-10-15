-- Database constraint checks for migrations 0001-0003.
-- Run against a migrated database: psql -v ON_ERROR_STOP=1 -f db_checks/constraints_check.sql
-- (also executed by tests/test_db_constraints.py).
-- Everything runs in one transaction that is rolled back; no rows persist.
-- Each "expect_fail" block must raise; if the statement succeeds, the script aborts.

BEGIN;

CREATE TEMP TABLE check_log (name text, outcome text);

CREATE FUNCTION pg_temp.expect_fail(check_name text, stmt text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE stmt;
    EXCEPTION WHEN OTHERS THEN
        INSERT INTO check_log VALUES (check_name, 'PASS (rejected: ' || SQLERRM || ')');
        RETURN;
    END;
    RAISE EXCEPTION 'CHECK FAILED: % was accepted but must be rejected', check_name;
END;
$$;

CREATE FUNCTION pg_temp.expect_ok(check_name text, stmt text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE stmt;
    INSERT INTO check_log VALUES (check_name, 'PASS (accepted)');
END;
$$;

-- ---------------------------------------------------------------- fixtures (rolled back)
-- SYNTH_COMMODITY (synthetic_only) is seeded by migration 0003.
INSERT INTO partner (code, name_en, name_ar, is_fictional) VALUES ('REAL_TEST', 'Real partner (test)', 'شريك حقيقي', false);

INSERT INTO source (id, data_mode, dataset_title, geographic_coverage)
VALUES ('00000000-0000-0000-0000-00000000a001', 'synthetic', 'Booklet Table 4.1 fixtures', 'OM');
INSERT INTO dataset_version (id, source_id, data_mode, version_label, checksum_sha256)
VALUES ('00000000-0000-0000-0000-00000000b001', '00000000-0000-0000-0000-00000000a001', 'synthetic', 'v1', repeat('a', 64));

INSERT INTO source (id, data_mode, publisher, dataset_title, url, locator_kind, access_date, geographic_coverage, reuse_conditions)
VALUES ('00000000-0000-0000-0000-00000000a002', 'verified_source', 'Test publisher', 'Check table',
        'https://example.invalid/t.csv', 'direct_file', '2026-09-25', 'OM', 'Test');
INSERT INTO dataset_version (id, source_id, data_mode, version_label, checksum_sha256)
VALUES ('00000000-0000-0000-0000-00000000b002', '00000000-0000-0000-0000-00000000a002', 'verified_source', 'v1', repeat('d', 64));

-- ---------------------------------------------------------------- provenance
SELECT pg_temp.expect_fail('synthetic source with a publisher',
  $q$INSERT INTO source (data_mode, publisher, dataset_title, geographic_coverage)
     VALUES ('synthetic', 'NCSI', 'x', 'OM')$q$);

SELECT pg_temp.expect_fail('verified source without url/access date',
  $q$INSERT INTO source (data_mode, publisher, dataset_title, geographic_coverage)
     VALUES ('verified_source', 'Some publisher', 'x', 'OM')$q$);

SELECT pg_temp.expect_fail('verified source pointing at a catalogue page',
  $q$INSERT INTO source (data_mode, publisher, dataset_title, url, locator_kind, access_date, geographic_coverage, reuse_conditions)
     VALUES ('verified_source', 'P', 'x', 'https://example.invalid/', 'catalogue_page', '2026-09-25', 'OM', 'r')$q$);

SELECT pg_temp.expect_fail('verified source without reuse conditions',
  $q$INSERT INTO source (data_mode, publisher, dataset_title, url, locator_kind, access_date, geographic_coverage)
     VALUES ('verified_source', 'P', 'x', 'https://example.invalid/t.csv', 'direct_file', '2026-09-25', 'OM')$q$);

SELECT pg_temp.expect_fail('dataset version whose mode differs from its source',
  $q$INSERT INTO dataset_version (source_id, data_mode, version_label, checksum_sha256)
     VALUES ('00000000-0000-0000-0000-00000000a001', 'verified_source', 'v2', repeat('b', 64))$q$);

SELECT pg_temp.expect_fail('malformed checksum',
  $q$INSERT INTO dataset_version (source_id, data_mode, version_label, checksum_sha256)
     VALUES ('00000000-0000-0000-0000-00000000a001', 'synthetic', 'v3', repeat('Z', 64))$q$);

SELECT pg_temp.expect_fail('same file bytes uploaded twice for one source',
  $q$INSERT INTO dataset_version (source_id, data_mode, version_label, checksum_sha256)
     VALUES ('00000000-0000-0000-0000-00000000a001', 'synthetic', 'v1-again', repeat('a', 64))$q$);

-- ---------------------------------------------------------------- observations
SELECT pg_temp.expect_ok('valid synthetic generation observation (48,000 GWh)',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2001-01-01', '2001-12-31', 'annual', 48000, u.id, 'table4.1:row1'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_ok('missing value stored as NULL',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', NULL, u.id, 'row-missing'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_ok('year-to-date period marked incomplete',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, period_complete, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2003-01-01', '2003-06-30', false, 'annual', 1, u.id, 'ytd'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('observation without a frequency',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2004-01-01', '2004-12-31', 1, u.id, 'nofreq'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('complete monthly period spanning two months',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2004-01-01', '2004-02-29', 'monthly', 1, u.id, 'freq'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('complete annual period not covering the year',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2005-01-01', '2005-06-30', 'annual', 1, u.id, 'short'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('T04 duplicate natural key (null commodity/partner/flow)',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2001-01-01', '2001-12-31', 'annual', 48000, u.id, 'dup'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('T03 generation stored in MW (power unit on energy indicator)',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2006-01-01', '2006-12-31', 'annual', 5, u.id, 'mw'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='MW'$q$);

SELECT pg_temp.expect_fail('observation mode differs from its dataset version',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'verified_source', i.id, a.id, '2007-01-01', '2007-12-31', 'annual', 1, u.id, 'mode'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('period end before start',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2008-12-01', '2008-01-31', 'monthly', 1, u.id, 'period'
     FROM indicator i, area a, unit u WHERE i.code='ELEC_GENERATION' AND a.code='OM' AND u.code='GWh'$q$);

SELECT pg_temp.expect_fail('commodity indicator without commodity',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 100000, u.id, 'food'
     FROM indicator i, area a, unit u WHERE i.code='FOOD_PRODUCTION' AND a.code='OM' AND u.code='tonne'$q$);

SELECT pg_temp.expect_fail('trade indicator without flow',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, commodity_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 80000, u.id, c.id, 'trade'
     FROM indicator i, area a, unit u, commodity c
     WHERE i.code='TRADE_QUANTITY' AND a.code='OM' AND u.code='tonne' AND c.code='SYNTH_COMMODITY'$q$);

SELECT pg_temp.expect_ok('synthetic import from fictional Partner A (48,000 t)',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, commodity_id, partner_id, flow, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 48000, u.id, c.id, p.id, 'import', 'partner-a'
     FROM indicator i, area a, unit u, commodity c, partner p
     WHERE i.code='TRADE_QUANTITY' AND a.code='OM' AND u.code='tonne' AND c.code='SYNTH_COMMODITY' AND p.code='PARTNER_A'$q$);

SELECT pg_temp.expect_fail('synthetic observation attributed to a real partner',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, commodity_id, partner_id, flow, source_row)
     SELECT '00000000-0000-0000-0000-00000000b001', 'synthetic', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 1, u.id, c.id, p.id, 'import', 'real'
     FROM indicator i, area a, unit u, commodity c, partner p
     WHERE i.code='TRADE_QUANTITY' AND a.code='OM' AND u.code='tonne' AND c.code='SYNTH_COMMODITY' AND p.code='REAL_TEST'$q$);

SELECT pg_temp.expect_fail('verified observation attributed to a fictional partner',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, commodity_id, partner_id, flow, source_row)
     SELECT '00000000-0000-0000-0000-00000000b002', 'verified_source', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 1, u.id, c.id, p.id, 'import', 'fict'
     FROM indicator i, area a, unit u, commodity c, partner p
     WHERE i.code='TRADE_QUANTITY' AND a.code='OM' AND u.code='tonne' AND c.code='WHEAT' AND p.code='PARTNER_A'$q$);

SELECT pg_temp.expect_fail('verified observation of the synthetic-only commodity',
  $q$INSERT INTO observation (dataset_version_id, data_mode, indicator_id, area_id, period_start, period_end, frequency, value, unit_id, commodity_id, source_row)
     SELECT '00000000-0000-0000-0000-00000000b002', 'verified_source', i.id, a.id, '2002-01-01', '2002-12-31', 'annual', 1, u.id, c.id, 'synth-only'
     FROM indicator i, area a, unit u, commodity c
     WHERE i.code='FOOD_PRODUCTION' AND a.code='OM' AND u.code='tonne' AND c.code='SYNTH_COMMODITY'$q$);

-- ---------------------------------------------------------------- publication
SELECT pg_temp.expect_fail('published without published_at',
  $q$UPDATE dataset_version SET status='published' WHERE id='00000000-0000-0000-0000-00000000b001'$q$);

SELECT pg_temp.expect_ok('publish v1',
  $q$UPDATE dataset_version SET status='published', published_at=now() WHERE id='00000000-0000-0000-0000-00000000b001'$q$);

SELECT pg_temp.expect_fail('edit an observation of a published version',
  $q$UPDATE observation SET value = 1 WHERE dataset_version_id='00000000-0000-0000-0000-00000000b001'$q$);

SELECT pg_temp.expect_fail('delete an observation of a published version',
  $q$DELETE FROM observation WHERE dataset_version_id='00000000-0000-0000-0000-00000000b001'$q$);

SELECT pg_temp.expect_fail('T05 second published version for the same source',
  $q$INSERT INTO dataset_version (source_id, data_mode, version_label, checksum_sha256, status, published_at)
     VALUES ('00000000-0000-0000-0000-00000000a001', 'synthetic', 'v2', repeat('c', 64), 'published', now())$q$);

SELECT pg_temp.expect_fail('reviewed commodity without classification',
  $q$UPDATE commodity SET mapping_status='reviewed' WHERE code='WHEAT'$q$);

-- ---------------------------------------------------------------- accounts and history
SELECT pg_temp.expect_fail('plain-text password stored',
  $q$INSERT INTO app_user (email, display_name, password_hash) VALUES ('a@b.invalid', 'A', 'hunter2')$q$);

SELECT pg_temp.expect_fail('e-mail not normalised',
  $q$INSERT INTO app_user (email, display_name, password_hash) VALUES ('A@B.invalid', 'A', '!')$q$);

SELECT pg_temp.expect_fail('audit events cannot be deleted',
  $q$DELETE FROM audit_event$q$);

SELECT pg_temp.expect_fail('review history cannot be edited',
  $q$UPDATE recommendation_review SET reason = 'changed'$q$);

SELECT name, outcome FROM check_log;
SELECT count(*) AS checks_passed FROM check_log;

ROLLBACK;
