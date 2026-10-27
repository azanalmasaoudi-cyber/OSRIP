-- Reverses 0024: uploaded datasets and research and dataset reports are removed.
DELETE FROM role_permission WHERE permission_code = 'dataset.analyze';
DELETE FROM user_permission_grant WHERE permission_code = 'dataset.analyze';
DELETE FROM permission WHERE code = 'dataset.analyze';

DROP TRIGGER trg_analysis_report_frozen ON analysis_report;
DROP FUNCTION analysis_report_frozen();
DROP TABLE analysis_report;
DROP TABLE analysis_dataset;
