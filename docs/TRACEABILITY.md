# Requirement-to-test traceability

Maps each requirement in [requirements.md](requirements.md) to the tests that verify
it and to the latest result from the audit run of 2026-09-25
([TEST_RESULTS.md](TEST_RESULTS.md)). Test locations:

* `B:` backend, `backend/tests/<file>::<test>` (pytest; `OSRIP_RUN_DB_TESTS=1` for integration)
* `E:` full-stack browser test, `frontend/e2e-api/<file>` › "title"
* `M:` mock-mode browser test, `frontend/e2e/shell.spec.ts` › "title"
* `S:` script or manual evidence

## Booklet Appendix A objectives

| Objective | Requirement | Verification in the booklet | Implemented verification | Result |
|---|---|---|---|---|
| Preserve definitions | FR01, FR02 | T03, T04, T05, import log | Rows for FR01, FR02, T03–T05 below; import error preview and error CSV | Pass |
| Trace a displayed value | FR03, FR05 | T02, T07, report fixture | Rows for FR03, FR05, T02, T07 below | Pass |
| Support meaningful comparison | FR04 | T01, T03, T09 | Rows below | Pass |
| Explain review actions | FR06 | Rule review with recorded feedback | Row FR06 | Pass |
| Evaluate forecasting | FR07 | T10 and saved chronological errors | Rows FR07, T10 | Pass (engine); no eligible real series |
| Protect administrative actions | SEC01 | T06 and session tests | Row SEC01 | Pass |
| Support two languages | UX01 | T08 and keyboard review | Rows UX01, NFR17 | Pass |

## Functional requirements

| Req. | Tests | Result |
|---|---|---|
| FR01 Import and validate | B: `test_import_validation.py` (all 35 functions); `test_import_workflow_integration.py::test_upload_map_validate_preview_approve_publish_and_read`, `::test_all_rows_rejected_cannot_be_approved`, `::test_remapping_invalidates_the_previous_validation`, `::test_oversized_and_non_csv_uploads_are_refused`, `::test_same_file_cannot_be_uploaded_twice_for_a_source`; E: `workflow.spec.ts` › "a data manager uploads, maps, validates, reviews, approves and publishes a CSV"; E: `journey.spec.ts` | Pass |
| FR02 Publish a version | B: `::test_publication_requires_prior_approval`, `::test_revision_supersedes_previous_snapshot_without_double_counting`, `::test_repeated_publication_does_not_duplicate_observations`, `::test_concurrent_publication_requests_insert_once`, `::test_failed_publication_rolls_back_and_keeps_previous_snapshot`; E: `journey.spec.ts` (v1 then v2) | Pass |
| FR03 Explore indicators | B: `test_analysis_integration.py` (16); `test_geography_forecast_integration.py::test_coverage_counts_only_the_exact_area_and_missing_is_not_zero`; E: `analysis.spec.ts` (sections, filters and exports), `workflow.spec.ts` › "the published synthetic fixture is served…", `geography-forecast.spec.ts`; M: filter and empty-state tests | Pass |
| FR04 Compare compatible records | B: `test_calculations.py::test_t03_gwh_compared_with_mw_is_rejected`, `::test_year_to_date_is_not_compared_with_complete_year`, `::test_different_commodities_are_not_combined`; `test_import_workflow_integration.py::test_mixed_frequencies_for_one_indicator_are_refused`; `test_release_audit_integration.py::test_mixed_frequencies_are_refused_with_a_reason_until_one_is_chosen`; E: `zz-mixed-frequency.spec.ts` | Pass |
| FR05 Generate a report | B: `test_reviews_reports_integration.py::test_report_freezes_inputs_and_survives_a_later_publication`, `::test_report_keeps_its_snapshot_after_a_revision_is_published`, `::test_report_export_keeps_label_filters_assumptions_and_versions`, `::test_private_reports_are_hidden_and_published_ones_are_shared`, `::test_report_creation_needs_permission_and_known_filters`; E: `analysis.spec.ts` › "an analyst runs the rules, reviews a card and freezes a report", `journey.spec.ts` | Pass |
| FR06 Explain a recommendation | B: `::test_rules_produce_transparent_cards_for_the_fixture`, `::test_thresholds_are_parameters_recorded_with_the_run`, `::test_data_quality_card_for_a_missing_input`, `::test_analyst_reviews_are_appended_and_the_latest_is_the_status`, `::test_review_needs_a_valid_status_and_reason`; E: `analysis.spec.ts` (review card and history) | Pass |
| FR07 Evaluate a forecast | B: `test_forecasting.py` (16: eligibility, identical dates, chronology, hand-computed baseline and least squares, no look-ahead, MAE/RMSE, exact errors); `test_geography_forecast_integration.py::test_eligible_synthetic_series_records_predictions_errors_and_metrics`, `::test_predictions_are_append_only` | Pass |
| SEC01 Authorize protected actions | B: `test_auth_integration.py` (16), `::test_rules_need_the_analysis_permission`, `::test_running_a_forecast_needs_the_analysis_permission`; E: `workflow.spec.ts` › "a viewer is refused by the server even when calling the API directly", `analysis.spec.ts` › "a viewer sees the cards but cannot…"; M: "data management is restricted" | Pass |
| UX01 Switch language | M: "T08: switching to Arabic keeps mode, route and numbers; sets RTL", "T08: switching language preserves page filters and the filtered values"; E: `workflow.spec.ts` › "Arabic shows the same API values", `geography-forecast.spec.ts` (selection kept across a switch), `quality.spec.ts` (every page in both languages) | Pass |

## Acceptance tests (Table 4.3)

| Test | Implemented as | Result |
|---|---|---|
| T01 | B: `test_calculations.py::test_t01_previous_zero_is_undefined_not_infinite`; `test_analysis_integration.py` (zero previous value explained) | Pass |
| T02 | B: `::test_t02_missing_previous_is_missing_not_zero_growth`; `test_analysis_integration.py` (missing input); `test_import_validation.py` (missing value kept as null); `test_geography_forecast_integration.py` (missing counted as missing) | Pass |
| T03 | B: `::test_t03_gwh_compared_with_mw_is_rejected`; `test_db_constraints.py` (unit dimension check) | Pass |
| T04 | B: `test_import_validation.py` (duplicate keys: every occurrence rejected); `test_db_constraints.py` (natural key with null dimensions) | Pass |
| T05 | B: `::test_revision_supersedes_previous_snapshot_without_double_counting`; E: `journey.spec.ts` | Pass |
| T06 | B: `::test_public_viewer_cannot_publish_even_with_a_direct_request`, `::test_publication_needs_the_explicit_publish_grant`; E: `workflow.spec.ts` (viewer, direct request) | Pass |
| T07 | B: `::test_report_export_keeps_label_filters_assumptions_and_versions`; E: `analysis.spec.ts`, `journey.spec.ts` (label and data mode on report and CSV) | Pass |
| T08 | See UX01 | Pass |
| T09 | B: `::test_t09_partner_subtotal_is_labelled_partial`, `::test_partner_sum_above_total_fails_reconciliation` | Pass |
| T10 | B: `test_forecasting.py::test_two_points_are_insufficient_history_and_withheld`; `test_geography_forecast_integration.py::test_booklet_fixture_series_are_ineligible_and_the_run_is_withheld`; E: `geography-forecast.spec.ts` › "an analyst request on an ineligible series is recorded as withheld (T10)" | Pass |
| T11 | B: `::test_failed_publication_rolls_back_and_keeps_previous_snapshot` | Pass |
| T12 | B: `test_reviews_reports_integration.py` (calculation CSV keeps 160,000 and the assumption); E: `analysis.spec.ts` › "food shows the balance…" (export link carries the assumption) | Pass |

## Non-functional and other requirements

| Req. | Evidence | Result |
|---|---|---|
| NFR01, NFR07 | SEC01 rows | Pass |
| NFR02 | T02 rows; exports write empty cells for missing values (`test_import_workflow_integration.py::test_modes_are_separate_in_queries_and_exports`) | Pass |
| NFR03 | UX01 rows | Pass |
| NFR04 | S: `backend/scripts/perf_workload.py` → `docs/perf/perf-2026-09-25.json` | Measured; target not demonstrated under concurrency |
| NFR05, NFR06 | B: `::test_login_sets_protected_cookies_and_stores_only_hashes`; `test_db_constraints.py` (password-hash format) | Pass |
| NFR08 | B: `::test_repeated_failures_are_throttled_even_with_the_right_password` | Pass |
| NFR10 | B: `::test_oversized_and_non_csv_uploads_are_refused`; `test_import_validation.py` (CSV safety) | Pass |
| NFR11 | B: `::test_private_reports_are_hidden_and_published_ones_are_shared` | Pass |
| NFR12 | B: `::test_denied_attempts_are_audited` (no secrets in metadata) | Pass |
| NFR13 | S: `backend/scripts/backup_restore_drill.py` → `docs/backup/backup-drill-20260925.json` | Pass |
| NFR14 | E: `quality.spec.ts` › "failed requests show an explained error…" | Pass |
| NFR15 | M: empty-state tests; E: `quality.spec.ts` › "empty states…"; series cards have tables (`shell.spec.ts`) | Pass |
| NFR16 | E: `quality.spec.ts` › "negative values and units…"; S: `npm run check:contrast` 54/54 | Pass |
| NFR17 | M: skip link, dialog focus trap; E: `quality.spec.ts` › "keyboard: skip link, visible focus…" | Pass (screen reader not tested) |
| NFR18 | E: `quality.spec.ts` › "no page scrolls sideways…" (desktop and Pixel 7); M: @mobile tests | Pass |
| DR01 | B: `::test_modes_are_separate_in_queries_and_exports`, `test_db_constraints.py`; E/M: verified mode never falls back | Pass |
| DR02 | B: `::test_catalogue_page_cannot_be_registered_as_a_verified_source` | Pass |
| DR04 | B: `test_calculations.py::test_electricity_growth_is_4_375_percent_before_rounding`; E: 4.38% displayed, 4.375 exact | Pass |
| DR06, DR07 | T04, T05 rows; `test_db_constraints.py` | Pass |
| DR08 | B: `test_calculations.py` (23) and `test_analysis_integration.py` (booklet Table 4.2 literals) | Pass |
| DR09 | B: `test_import_validation.py` | Pass |
| RR01–RR03 | FR06 rows; `::test_history_tables_are_append_only` | Pass |
| GEO01 | B: `test_geography_forecast_integration.py::test_registry_has_11_governorates_and_63_wilayats`, `::test_2022_wilayats_have_their_governorates_and_sources`, `::test_every_entry_is_sourced_for_existence_names_and_parent`, `::test_codes_are_unique_and_osrip_codes_are_labelled`, `::test_hierarchy_is_enforced_by_the_database`; E: `geography-forecast.spec.ts` | Pass |
| GEO02 | S: map shown with attribution in the in-app browser (VERIFICATION.md); `::test_registry_carries_no_coordinates_or_geometry` | Partly met (no boundaries) |
| GEO03 | B: `::test_coverage_counts_only_the_exact_area_and_missing_is_not_zero`; E: "the national area shows its synthetic observations; governorates do not inherit them" | Pass |
| GEO04 | E: `geography-forecast.spec.ts` (map unavailable, table works), `quality.spec.ts` (keyboard-only selection) | Pass |
| FC01, FC02 | FR07 and T10 rows; E: "forecast is unavailable with reasons in both modes" | Pass |
| WS01 (analytical workspace and live studies, 10 Oct; `WORKSPACE.md`) | B: `test_live_study.py` (16: sentence findings with paragraph citations, one unit per table, invalid tables never sent, narration targets rows, withheld and cancelled studies confirm nothing, study tables unchanged, completion consistency, event order and replay, server-sent events with resume, comparison tables, cancellation, failed search warning, ownership, narration segment speech, deletion with the conversation, preview not stored); E: `workspace.spec.ts` (6: filters, cards, stale flags, chart = table rows, sorting, geography and verified-data states; live study with row highlighting and interruption; partial failure and keyboard access to sources and tabs; returning to a study and Arabic with unchanged values; crafted streams: late and superseded events ignored after a stop, invalid table never drawn), `workspace-phone.spec.ts` (phone tabs, study brought forward, follow-up, no sideways scroll) | Pass locally; server speech live pending |
| AI01 (governed providers, 10 Oct; `AI_PROVIDERS.md`) | B: `test_ai_providers.py` (21: OpenAI and Gemini request and response formats, retry and timeouts, daily limit and budget, citations, byte offsets, grounded results display-only, fallback, cross-check, planted instructions, routing, data status, readiness, retention); `test_ai_providers_integration.py` (9: routing, fallback recorded, limit not charged, grounded shown apart, cross-check on request, conflicting sources across routes, unsupported figure withheld, readiness and test permissions, purge); `test_api_foundation.py::test_app_refuses_scripted_ai_and_search_routes_in_production`; `test_migrations_roundtrip_integration.py::test_0018_provider_call_log_checks_and_round_trip`; E: `governed-ai.spec.ts` (4), `upgrade.spec.ts` › failures shown | Pass locally; **live providers not tested** |
| IV01 (integrated verification, 11 Oct; `VERIFICATION_REPORT.md`) | B: `test_allowance_rules_integration.py` (greetings free, failed answer and its retry free, replay, playback and Stop after completion charge once, five answers across personas, languages, voice, research and compare; sixth refused on every channel; exactly 5 charged in the database), `test_live_study.py::test_each_sentence_of_a_series_answer_points_at_its_own_row`; E: `e2e-demo/integrated.demo.spec.ts` (6: entrance carried in and placed in the centre, bilingual goals, skip and replay; persona choice and configured voices; verified-data analysis with matching table, chart and narration; labelled external research; provider failure and denied microphone not charged; limit after switching persona; phone), `zz-mixed-frequency.spec.ts` (frequency chosen in the workspace) | Pass (scripted providers; live voices and providers pending credentials) |
