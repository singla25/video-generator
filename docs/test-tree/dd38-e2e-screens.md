# Feature: DD-38 draft screens (e2e screenshots, TT-UI-E2E-P2c)
└── Scenario: draft batch exists after sheet validation, viewed from a second tab
    ├── ✅ Positive — /batches/running shows "Not started" → shot `dd38-running-not-started`
    ├── ✅ Positive — / shows "Continue setup" and the "Not started" tile → shot `dd38-overview-draft`
    └── ⚠️ Edge — second page closed before "Review and start"; no new assertions, main flow unchanged
