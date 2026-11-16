Feature: Several name slots per template (DD-40): model, database, API, fingerprint
Tests: tests/unit/domain/test_validate_slots.py, tests/unit/domain/test_template_slots_property.py,
       tests/unit/services/test_fingerprint_extra_slots.py,
       tests/integration/db/test_template_extra_slots_repository.py,
       tests/integration/db/test_migration_0002_extra_slots.py,
       tests/integration/db/test_row_store_template_slots.py,
       tests/integration/api/test_template_extra_slots.py
Updated: tests/unit/domain/test_codes.py (SLOTS_INVALID in the code set)

Constants used by the tests: slot gap minimum 0.2 s, at most 5 slots in total, at most 4 extra
slots per request, video duration 4.0 s. Float-safe boundary values are used on purpose:
2.2 - 2.0 >= 0.2 holds in binary floats, 1.8 - 1.6 does not.

├── Scenario: The set of slots is valid together (validate_slots)
│   ├── ✅ Positive
│   │   ├── MS-VS-P1 two slots inside the video, well apart, are accepted
│   │   ├── MS-VS-P2 three slots are accepted
│   │   ├── MS-VS-P3 exactly 5 slots (the maximum) are accepted
│   │   ├── MS-VS-P4 gap of exactly 0.2 s between neighbours is accepted
│   │   ├── MS-VS-P5 a single slot behaves like validate_slot and is accepted
│   │   └── MS-VS-P6 slots given unsorted are accepted when they are fine once sorted
│   ├── ❌ Negative
│   │   ├── MS-VS-N1 6 slots are refused with SLOTS_INVALID
│   │   ├── MS-VS-N2 gap of 0.19 s is refused with SLOTS_INVALID
│   │   ├── MS-VS-N3 overlapping slots are refused with SLOTS_INVALID
│   │   ├── MS-VS-N4 touching slots (gap 0) are refused with SLOTS_INVALID
│   │   ├── MS-VS-N5 overlap that only appears after sorting is refused with SLOTS_INVALID
│   │   ├── MS-VS-N6 a slot beyond the video duration is refused by the single-slot rule (SLOT_NOT_FOUND)
│   │   ├── MS-VS-N7 a single invalid slot (reversed, zero length, negative, NaN, infinite) is refused like validate_slot
│   │   └── MS-VS-N8 5 slots with one overlap is refused with SLOTS_INVALID
│   └── ⚠️ Edge
│       ├── MS-VS-E1 the SLOTS_INVALID message reads "The name slots overlap or are too close."
│       ├── MS-VS-E2 a slot that ends exactly at the video duration is accepted
│       └── MS-VS-E3 a gap of 0.2 s is accepted but 0.19 s is not (boundary pair)
│
├── Scenario: The slots property (TemplateRecord.slots, row-job TemplateInfo.slots)
│   ├── ✅ Positive
│   │   ├── MS-SP-P1 primary only: slots is one pair
│   │   ├── MS-SP-P2 primary plus extras: slots holds all of them sorted by start
│   │   ├── MS-SP-P3 extra_slots defaults to () on a new record
│   │   └── MS-SP-P4 row-job TemplateInfo has the same slots meaning, and extra_slots defaults to ()
│   ├── ❌ Negative
│   │   └── MS-SP-N1 no primary slot: slots is () even when extra slots are set
│   └── ⚠️ Edge
│       ├── MS-SP-E1 primary in the middle of the extras: sorted by start, not primary first
│       └── MS-SP-E2 slots is a tuple of (float, float) tuples
│
├── Scenario: Extra slots are stored and read back (repository)
│   ├── ✅ Positive
│   │   ├── MS-DB-P1 extra slots round-trip exactly as a tuple of tuples
│   │   ├── MS-DB-P2 a template saved without extras reads back as ()
│   │   ├── MS-DB-P3 saving with no extras again clears the stored extras
│   │   └── MS-DB-P4 the stored JSON is a list of [start, end] pairs
│   ├── ❌ Negative
│   │   └── MS-DB-N1 an unknown template id still reads as None (no crash on the new column)
│   ├── ⚠️ Edge
│   │   ├── MS-DB-E1 NULL in the column reads as ()
│   │   └── MS-DB-E2 an empty JSON list in the column reads as ()
│
├── Scenario: The render job's template snapshot (row store, SqlRowStore.preview_job)
│   ├── ✅ Positive
│   │   ├── MS-DB-R1 stored extra slots reach the job as a tuple of float tuples
│   │   ├── MS-DB-R2 job slots are the primary and the extras sorted by start
│   │   └── MS-DB-R3 no extras: extra_slots () and slots is the primary only
│   └── ❌ Negative
│       └── MS-DB-R4 no primary slot: slots is ()
│
├── Scenario: Migration 0002 adds the extra_slots column
│   ├── ✅ Positive
│   │   ├── MS-MG-P1 the alembic head is 0002, a child of 0001
│   │   ├── MS-MG-P2 upgrade 0001 -> 0002 adds a nullable extra_slots column
│   │   ├── MS-MG-P3 the migrated schema matches the models exactly (no drift)
│   │   └── MS-MG-P4 downgrade 0002 -> 0001 drops the column and keeps the other columns and rows
│   ├── ❌ Negative
│   │   └── MS-MG-N1 the database at 0001 has no extra_slots column before the upgrade
│   └── ⚠️ Edge
│       ├── MS-MG-E1 rows written at 0001 stay readable after the upgrade, with extra_slots ()
│       ├── MS-MG-E2 upgrade, downgrade, upgrade again works and matches the models
│       └── MS-MG-E3 the migration runs only against a *_test database (name guard)
│
├── Scenario: Set several slots (PUT /api/templates/{id}/slot with extra_slots)
│   ├── ✅ Positive
│   │   ├── MS-API-P1 PUT with two extra slots: 200, GET shows extra_slots and the sorted slots
│   │   ├── MS-API-P2 response of PUT and of confirm carry extra_slots and slots
│   │   ├── MS-API-P3 a request without extra_slots stores none (default empty)
│   │   ├── MS-API-P4 extras sent unsorted: slots come back sorted
│   │   ├── MS-API-P5 four extra slots (five in total) are accepted
│   │   ├── MS-API-P6 an extra slot ending at the video duration is accepted
│   │   ├── MS-API-P7 a gap of exactly 0.2 s between slots is accepted
│   │   ├── MS-API-P8 GET /templates lists extra_slots and slots for every template
│   │   ├── MS-API-P9 a new template has extra_slots [] and slots []
│   │   ├── MS-API-P10 analyse (automatic detection) clears the extra slots
│   │   └── MS-API-P11 changing only an extra slot unconfirms a confirmed slot (usable becomes false)
│   ├── ❌ Negative
│   │   ├── MS-API-N1 overlapping extra slot: 422 SLOTS_INVALID, nothing changed
│   │   ├── MS-API-N2 gap of 0.19 s: 422 SLOTS_INVALID, nothing changed
│   │   ├── MS-API-N3 touching slots: 422 SLOTS_INVALID, nothing changed
│   │   ├── MS-API-N4 extra slot beyond the video duration: 422 SLOT_NOT_FOUND, nothing changed
│   │   ├── MS-API-N5 six slots in total (five extras): 422, nothing changed
│   │   ├── MS-API-N6 malformed items (wrong length, text, null, bare numbers, object, NaN) are 422 VALIDATION_ERROR, nothing changed
│   │   ├── MS-API-N7 extra_slots that is not a list is 422 VALIDATION_ERROR
│   │   └── MS-API-N8 PUT for an unknown template is 404 even with extra slots
│   └── ⚠️ Edge
│       ├── MS-API-E1 an extra slot equal to the primary slot is an overlap: 422 SLOTS_INVALID
│       ├── MS-API-E2 zero-length or reversed extra slot: 422 SLOT_NOT_FOUND
│       ├── MS-API-E3 extras given in reverse order that overlap once sorted: 422 SLOTS_INVALID
│       └── MS-API-E4 an empty extra_slots list behaves like no extras
│
└── Scenario: Changing only an extra slot makes an approved preview stale
    ├── ✅ Positive
    │   └── MS-FP-P1 approved preview; re-sending identical extras keeps the approval
    ├── ❌ Negative
    │   ├── MS-FP-N1 changing only an extra slot: batch preview approved becomes false
    │   └── MS-FP-N2 ... and start is refused with 409 PREVIEW_NOT_APPROVED
    └── ⚠️ Edge
        ├── MS-FP-E1 fingerprint differs when only an extra slot differs (unit, fingerprint_for)
        ├── MS-FP-E2 fingerprint with no extras equals the one from before the feature (default ())
        └── MS-FP-E3 a preview gate approved for the old extras cannot start after an extra-only change (unit)

Updated existing tests (red state expected):
  - tests/unit/domain/test_codes.py: EXPECTED_CODES now includes SLOTS_INVALID.
  - No existing test pins the alembic head or the exact template JSON key set; none needed changing.
