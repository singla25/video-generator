Feature: DD-37 e2e screenshots (tests/frontend/e2e/full-flow.spec.ts, desktop, 1440x900)
└── Scenario: operator views the DD-37 screens during the main flow
    ├── ✅ dd37-templates-form-empty — Templates, "New template" form open, no file chosen
    ├── ✅ dd37-templates-form-filled — same form, video chosen and "Rahul" typed, before upload
    ├── ✅ dd37-templates-delete-dialog — "Delete this template?" dialog on the Rahul card, then Cancel
    ├── ✅ dd37-wizard-count — wizard step 4, "Videos to generate" group with "All 3 rows" selected
    ├── ✅ dd37-list-completed — /batches/completed, the finished batch (Rahul, 5 rows, 100 %)
    ├── ✅ dd37-list-running — /batches/running, nothing running after the batch completes
    └── ✅ dd37-list-failed — /batches/failed, empty state "No failed batches"
