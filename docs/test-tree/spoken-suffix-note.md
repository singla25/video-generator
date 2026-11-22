# Feature: spoken suffix shown in the dashboard (BL-12) - backend part

Feature: the system status route exposes `spoken_suffix`
└── Scenario: dashboard reads the active suffix
    ├── Positive: default "जी"; custom Latin/Devanagari; present in fake and local mode; key set exact
    ├── Negative: 401 without a session (no suffix in body); no other setting or secret leaks
    └── Edge: spaces stripped; empty or blank gives "" (not null); two apps differ; Redis down still 200 with suffix

Tests: tests/unit/api/test_system_status_spoken_suffix.py; existing key-set assertions updated in
test_system_status.py and test_schema_gate.py.

## Dashboard (BL12-T2): tests/frontend/unit/spoken-suffix-note.test.tsx

Feature: spoken suffix note in the preview step (role="note", data-testid="spoken-suffix-note")
└── Scenario: the user opens the preview step
    ├── ✅ Positive: Devanagari, Latin and empty suffix give the exact texts; shown in every preview state (none, pending, ready, failed, stale), in fake and local mode; inside the panel; not aria-hidden (BL12-P1..P7)
    ├── ❌ Negative: nothing while status loads, when status returns 500, or when the key is missing (older server) (BL12-N1..N3)
    └── ⚠️ Edge: markup-like value stays text, 20 character suffix, surrounding spaces, one note after refetch, local spoken-name box coexists (BL12-E1..E5)
