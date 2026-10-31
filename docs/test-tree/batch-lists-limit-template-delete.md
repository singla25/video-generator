Feature: Batch lists by view, start with a limit, template delete (DD-37)
Tests: tests/integration/api/test_batch_views.py, test_batch_start_limit.py, test_template_delete.py

├── Scenario: Batch list filtered by view (GET /batches?view=)
│   ├── ✅ Positive
│   │   ├── V-P1 view=all lists every batch in every state (test_view_all_lists_every_batch_in_every_state)
│   │   ├── V-P2 view=running lists RUNNING and PAUSED batches, with or without failed rows (test_view_running_lists_running_and_paused_batches)
│   │   ├── V-P3 view=completed lists COMPLETED batches with zero FAILED rows only (test_view_completed_lists_completed_batches_without_failed_rows)
│   │   ├── V-P4 view=failed lists RUNNING/PAUSED/COMPLETED batches with a FAILED row (test_view_failed_lists_started_batches_with_at_least_one_failed_row)
│   │   ├── V-P5 running batch with one failed row is under running and failed (test_running_batch_with_a_failed_row_is_listed_under_running_and_failed)
│   │   ├── V-P6 view=all is byte-for-byte the unfiltered listing (test_view_all_is_exactly_the_unfiltered_listing)
│   │   ├── V-P7 page_size 1 walks only matching batches, newest first, totals = filtered count (test_pages_under_a_filter_hold_only_matching_batches_newest_first)
│   │   └── V-P8 total and total_pages follow the filter (test_totals_count_only_the_filtered_batches)
│   ├── ❌ Negative
│   │   └── V-N1 any value other than all/running/completed/failed is 422 VALIDATION_ERROR, parametrized: bogus, RUNNING, Failed, queued, all,running, empty (test_unknown_view_value_is_a_validation_error)
│   └── ⚠️ Edge
│       ├── V-E1 DRAFT and CANCELLED batches (with or without FAILED rows) never appear in running, completed or failed (test_draft_and_cancelled_batches_never_appear_in_the_filtered_views)
│       ├── V-E2 filter that matches nothing is an empty page with total 0 (test_view_with_no_matching_batches_is_an_empty_page)
│       └── V-E3 filtered view on an empty history is empty (test_view_on_an_empty_history_is_empty)
│
├── Scenario: Start with a limit (POST /batches/{id}/start, body limit)
│   ├── ✅ Positive
│   │   ├── L-P1 limit 2 of 5 rows: response queued_rows 2, counts queued 2 / skipped 3 (test_limit_two_of_five_rows_leaves_two_queued_and_three_skipped)
│   │   ├── L-P2 the two lowest row numbers stay QUEUED, 4-6 SKIPPED (test_the_first_rows_by_row_number_are_the_queued_ones)
│   │   ├── L-P3 skipped rows read back via rows endpoint: code NOT_SELECTED and exact message; queued rows have none (test_not_selected_rows_carry_the_code_and_the_exact_message)
│   │   ├── L-P4 fake queue receives exactly the two selected row ids (test_only_the_selected_rows_are_enqueued)
│   │   ├── L-P5 default folder name uses the selected count: 2026-10-18-2 (test_default_folder_name_counts_the_selected_rows)
│   │   ├── L-P6 folder_name and limit together (test_custom_folder_name_is_still_used_with_a_limit)
│   │   ├── L-P7 limit 5, 6 or 100 on 5 rows skips nothing (test_limit_at_or_above_the_queued_rows_skips_nothing)
│   │   └── L-P8 no body = today's behaviour: 5 queued, folder 2026-10-18-5 (test_without_a_limit_every_valid_row_is_queued_as_before)
│   ├── ❌ Negative
│   │   └── L-N1 limit 0, -1, "abc", 2.5 is 422 VALIDATION_ERROR; batch stays DRAFT, nothing queued, every row still QUEUED (test_invalid_limit_is_422_and_nothing_is_changed)
│   └── ⚠️ Edge
│       ├── L-E1 limit 1 queues only the first row (test_limit_of_one_queues_only_the_first_row)
│       ├── L-E2 invalid row keeps its own reason and does not use a slot; NOT_SELECTED only for valid rows beyond the limit (test_limit_counts_only_queued_rows_and_invalid_rows_keep_their_own_reason)
│       ├── L-E3 same Idempotency-Key repeated: same body, still 3 skipped, 2 jobs, one BATCH_STARTED (test_repeating_the_same_limited_start_does_not_skip_more_rows)
│       └── L-E4 another key with a smaller limit on a started batch changes nothing (test_another_key_on_a_started_batch_with_a_smaller_limit_changes_nothing)
│
├── Scenario: Audit of BATCH_STARTED
│   ├── ✅ Positive
│   │   └── A-P1 details carry limit 2 and skipped_rows 3, both ints (test_batch_started_audit_records_limit_and_skipped_rows)
│   └── ⚠️ Edge
│       └── A-E1 without a limit skipped_rows is 0 (test_batch_started_audit_without_a_limit_records_zero_skipped)
│
└── Scenario: Delete a template (DELETE /templates/{id})
    ├── ✅ Positive
    │   ├── T-P1 unused template: 204, then GET 404, list empty (test_deleting_an_unused_template_returns_204_and_it_is_gone)
    │   ├── T-P2 stored video and consent file deleted from storage (test_deleting_removes_the_stored_video_and_consent_file)
    │   ├── T-P3 every consent record and its file removed (test_deleting_removes_every_consent_record_and_its_file)
    │   ├── T-P4 another template's files untouched (test_deleting_one_template_leaves_another_templates_files_alone)
    │   ├── T-P5 one TEMPLATE_DELETED audit entry with template id, no name or file name (test_delete_writes_one_audit_entry_with_the_id_and_no_names)
    │   └── T-P6 template deletable after its only batch was deleted (test_template_is_deletable_after_its_only_batch_was_deleted)
    ├── ❌ Negative
    │   ├── T-N1 DRAFT batch: 409 TEMPLATE_IN_USE, message "1 batch", template and files kept (test_template_used_by_a_draft_batch_is_409_and_kept)
    │   ├── T-N2 COMPLETED batch: 409 TEMPLATE_IN_USE (test_template_used_by_a_completed_batch_is_409_and_kept)
    │   ├── T-N3 RUNNING, PAUSED, CANCELLED batch: 409 (test_template_used_by_a_batch_in_any_other_status_is_409)
    │   ├── T-N4 message counts all batches in any status; "1 batch" / "3 batches" (test_conflict_message_counts_every_batch_with_the_right_plural)
    │   ├── T-N5 batches of other templates are not counted (test_only_batches_of_this_template_are_counted)
    │   ├── T-N6 unknown id: 404 NOT_FOUND (test_unknown_template_is_404)
    │   ├── T-N7 no session: 401 UNAUTHENTICATED, nothing removed (test_delete_without_a_session_is_401_and_removes_nothing)
    │   └── T-N8 missing CSRF token: 403 CSRF_FAILED, nothing removed (test_delete_without_the_csrf_token_is_refused)
    └── ⚠️ Edge
        └── T-E1 second delete of the same template is 404 (test_deleting_twice_is_404_the_second_time)
