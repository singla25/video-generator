Feature: Overview batch controls (T-UI-controls)
Tests: tests/frontend/unit/overview-batch-controls.test.tsx

├── Scenario: DRAFT batch (uploaded, never started)
│   ├── ✅ P1 row chips read "Not started"; P2 "Start batch" + "Delete draft"; P3 confirm Delete -> DELETE, batch gone
│   ├── ❌ N1 "Keep" calls nothing; N2 failed DELETE shows message, batch stays
│   └── ⚠️ E1 double click on Delete = one request; E2 RUNNING batch keeps "Queued" chips, no Delete draft
├── Scenario: RUNNING / PAUSED batch
│   ├── ✅ P4 Pause; P5 Cancel batch behind confirm; P6 Resume + Cancel batch
│   ├── ❌ N3 "Keep running" sends nothing; N4/N5 409 message shown
│   └── ⚠️ E3 double click = one request, buttons disabled; E4 Cancel disabled while Resume pending
└── Scenario: COMPLETED / CANCELLED batch
    └── ✅ P7 no controls at all
