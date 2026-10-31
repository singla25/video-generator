# Feature: DD-38 draft screens (e2e screenshots, TT-UI-E2E-P2c)
└── Scenario: draft batch exists after sheet validation, viewed from a second tab
    ├── ✅ Positive — /batches/running shows "Not started" → shot `dd38-running-not-started`
    ├── ✅ Positive — / shows "Continue setup" and the "Not started" tile → shot `dd38-overview-draft`
    ├── ✅ Positive — Continue setup on /batches/running opens /batches/new?batch=, step 3 "Slot & preview" is current, "Generate preview" visible, no "no sheet data" message (real API, no report) → shot `dd38-resume-step3`
    └── ⚠️ Edge — second page closed before "Review and start"; no new assertions, main flow unchanged
