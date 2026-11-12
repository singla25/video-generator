Feature: DD-40 second name slot against the real API (E2E)
└── Scenario: operator adds slot 2 (3 s - 3.8 s) to the Rahul template on the Templates page
    ├── ✅ Positive  — save returns 200, card reads "Slots 1 s - 2 s, 3 s - 3.8 s", reload keeps both (TT-DD40-E2E-P1)
    ├── ❌ Negative  — a save error would show an alert in the card; asserted absent (TT-DD40-E2E-P1)
    └── ⚠️ Edge      — decimal end 3.8 shown as typed; slot confirmed again so the template stays usable
Screenshots: media/review/ui/dd40-slot-editor.png, media/review/ui/dd40-card-two-slots.png
