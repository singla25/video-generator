# Test tree: startup schema check (BL-8)

When the database is behind the code (e.g. migration 0003 not applied) the app shows ONE clear
message instead of screens failing with database errors. The app never applies migrations itself.

Assumed names (the developer may rename, tests then follow): `AppDeps.schema_reader`,
`vidgen.worker.schema_log.report_schema_at_start(check)`, `SqlSchemaVersionReader(engine)`,
setting `schema_check_ttl_seconds`.

```
Feature: Startup schema check
├── Scenario: classify revisions (tests/unit/domain/test_schema_state.py)
│   ├── ✅ SS-D-P1 equal/behind by 1 and 2/ahead/None -> ok/behind/ahead/empty
│   ├── ❌ SS-D-N1 non-numeric current -> behind (never ok)
│   └── ⚠️ SS-D-E1 different zero-padding compares by number; SS-D-E2 pure/repeatable
├── Scenario: read the revision (tests/integration/db/test_schema_reader.py, throwaway db)
│   ├── ✅ SS-R-P1 at 0001/0002, P2 at head, P3 expected is the shipped head
│   ├── ❌ SS-R-N1 reading is read-only; SS-R-N2 connection error propagates
│   └── ⚠️ SS-R-E1 no alembic_version table -> None and none created; E2 empty table -> None
├── Scenario: cached check (tests/unit/services/test_schema_check.py, fake clock)
│   ├── ✅ SS-S-P1..P4 ok/behind/empty/ahead with exact messages; P5 inside TTL no re-read;
│   │      P6 after TTL sees the Admin's migration
│   ├── ❌ SS-S-N2 reader DB error is not cached
│   └── ⚠️ SS-S-E1 unknown revision is behind, raw value kept; E2 TTL <= 0 rejected
├── Scenario: settings (tests/unit/api/test_schema_settings.py)
│   ├── ✅ SS-ST-P1 default 5; P2 bounds 1 and 300 accepted
│   └── ❌ SS-ST-N1 0, -1, 301 rejected
├── Scenario: API gate (tests/unit/api/test_schema_gate.py)
│   ├── ✅ SS-A-P1 behind/empty -> 503 DB_NEEDS_MIGRATION on batches/templates/uploads/audit/stats;
│   │      P2 health/login/logout/status allowed; P3-P5 status.schema block; P6 ok blocks nothing;
│   │      P7 health unchanged; P8 startup WARNING once
│   ├── ❌ SS-A-N1 no stack trace/SQL in body; N2 status needs a session; N3 DB down keeps
│   │      DB_UNAVAILABLE, no secret leak
│   └── ⚠️ SS-A-E1 ahead blocks nothing; E2 TTL cache across requests; E3 recovers without restart;
│          E4 no warning when ok
├── Scenario: worker start (tests/unit/worker/test_schema_log.py)
│   ├── ✅ SS-W-P1/P2 one ERROR with the exact message
│   ├── ❌ SS-W-N1 ok/ahead log no error
│   └── ⚠️ SS-W-E1 behind still starts, reader only read
├── Scenario: never migrates (tests/unit/meta/test_no_runtime_migrations.py)
│   ├── ❌ SS-M-N1 no alembic command API in backend/vidgen; N2 no CLI shell-out
│   └── ⚠️ SS-M-E1 adapter file exists and holds no DDL/write keywords
└── Scenario: frontend banner (tests/frontend/unit/schema-banner.test.tsx, MSW)
    ├── ✅ TT-SB-P1 behind; P2 empty; P3/P4 DB_NEEDS_MIGRATION from any call
    ├── ❌ TT-SB-N1 ok; N2 ahead; N3 failing status call; N4 no schema block -> no banner
    └── ⚠️ TT-SB-E1 DB-error toast hidden, one alert only; E2 odd text rendered as text;
           E3 banner disappears after migration
```

Acceptance mapping: design points 1 -> SS-D, SS-S; 2 -> SS-R; 3 -> SS-S, SS-ST; 4 -> SS-A;
5 -> SS-W; 6 -> TT-SB; "never migrates" -> SS-M.
- SS-A-P2 (behind) and SS-A-N4 (DD-44): behind database has tables (integration test, real DB); login throttle still counts failures and locks out (429).
