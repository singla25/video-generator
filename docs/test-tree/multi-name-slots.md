# Test tree: several name slots, dashboard (DD-40, task FE-RED)

Plan: docs/plans/multi-name-slots.md (AC3, AC4, AC9, AC10). The template JSON gets `extra_slots`
and `slots`; `PUT /api/templates/<id>/slot` takes `extra_slots` (always sent). The slot editor
(SlotEditor, used by the wizard step 3 and the Templates card) adds up to 4 extra pairs and runs
client-side checks. The template card lists all slots.

Files:
- tests/frontend/unit/multi-slot-editor.test.tsx (editor, wizard step 3, PUT body, confirm again)
- tests/frontend/unit/multi-slot-card.test.tsx (card text, card editor prefill)
- tests/frontend/mocks/data.ts and handlers.ts (fixtures and default PUT handler that records bodies)

Decisions from the Admin (through the CEO), now encoded in the tests:
1. The primary slot keeps its existing messages: end past the video -> "The slot must be inside the video (20 s)."
   and end <= start -> "End must be after start." (P19, P20). The new messages are for extra slots only:
   "Slot N ends after the video." and "Each slot must end after it starts.".
2. After a removal the extra slots are renumbered, so the labels follow the position (P21, P22).
3. extra_slots in the PUT body are sent sorted ascending by start, whatever the typing order (P23, P24).
Overlap ("Slots must not overlap or touch.") and "Fill in every slot or remove it." check all slots.

```
Feature: several name slots in the dashboard (DD-40)
├── Scenario: add and remove extra name slots  (multi-slot-editor.test.tsx)
│   ├── ✅ TT-DD40-P1 "Add another name slot" shows empty "Slot 2 start (s)" / "Slot 2 end (s)"
│   ├── ✅ TT-DD40-P2 each further click adds the next pair: "Slot 3 ...", "Slot 4 ..."
│   ├── ✅ TT-DD40-P3 "Remove slot 2" removes its pair; Add again gives an empty Slot 2
│   ├── ✅ TT-DD40-P4 every extra pair has its own "Remove slot N" button
│   ├── ❌ TT-DD40-N1 "Remove slot N" never touches the primary Slot start/end fields
│   ├── ⚠️ TT-DD40-E1 no extra pair by default: the editor looks as before (no "Slot 2" fields)
│   ├── ⚠️ TT-DD40-E2 "Add another name slot" is disabled with 5 slots shown (primary + 4), no "Slot 6"
│   └── ⚠️ TT-DD40-E3 a template with 4 extra slots starts with the button disabled
├── Scenario: prefill from the template  (multi-slot-editor.test.tsx)
│   ├── ✅ TT-DD40-P5 extra_slots [[2,3],[10,11]] -> Slot 2 = 2 / 3, Slot 3 = 10 / 11, primary unchanged
│   ├── ✅ TT-DD40-P6 a template without extra slots has no extra pair
│   └── ✅ TT-DD40-P7 wizard step 3 (StepSlot) shows the same extra pairs for a draft
├── Scenario: save sends the slots  (multi-slot-editor.test.tsx)
│   ├── ✅ TT-DD40-P8 zero extra slots: body {start_s, end_s, extra_slots: []}
│   ├── ✅ TT-DD40-P9 one extra slot: extra_slots [[10, 11]]
│   ├── ✅ TT-DD40-P10 two extra slots: extra_slots [[10, 11], [15, 16]]
│   ├── ✅ TT-DD40-P11 prefilled extra slots are sent unchanged when nothing is edited
│   ├── ✅ TT-DD40-P12 numbers, not strings, for start_s, end_s and every extra value
│   ├── ❌ TT-DD40-N2 a removed extra slot is not sent (extra_slots [])
│   └── ⚠️ TT-DD40-E4 typed "10.0" and "10" send the same number 10
├── Scenario: client checks disable Save and explain why  (multi-slot-editor.test.tsx)
│   ├── ❌ TT-DD40-N3 overlap with the primary slot: 5.0-6.0 vs 4.2-5.1 -> "Slots must not overlap or touch."
│   ├── ❌ TT-DD40-N4 touching: extra start equals primary end -> same text
│   ├── ❌ TT-DD40-N5 gap of 0.1 s (< 0.2 s) -> same text
│   ├── ❌ TT-DD40-N6 overlap found after sorting: extra 1-4.5 placed before 4.2-5.1 -> same text
│   ├── ❌ TT-DD40-N7 two extra slots overlap each other (10-12, 11-13) -> same text
│   ├── ❌ TT-DD40-N8 end equal to start, or before start -> "Each slot must end after it starts."
│   ├── ❌ TT-DD40-N9 an empty extra start or end -> "Fill in every slot or remove it."
│   ├── ❌ TT-DD40-N10 extra end above the video duration (21 s of 20 s) -> "Slot 2 ends after the video."
│   ├── ❌ TT-DD40-N11 the same check names the right slot ("Slot 3 ends after the video.")
│   ├── ⚠️ TT-DD40-E5 gap of exactly 0.2 s is allowed (5.3 after 5.1)
│   ├── ⚠️ TT-DD40-E6 a slot ending exactly at the video duration (20 s) is allowed
│   ├── ⚠️ TT-DD40-E7 fixing the value removes the alert and enables Save again
│   └── ⚠️ TT-DD40-E8 all slots valid and sorted: no alert, Save enabled
├── Scenario: after saving, the slot must be confirmed again  (multi-slot-editor.test.tsx)
│   ├── ✅ TT-DD40-P13 confirmed slot -> save with an extra slot -> "Slot confirmed" gone, "Confirm slot" back
│   └── ✅ TT-DD40-P14 then Confirm slot posts once and shows "Slot confirmed" again
└── Scenario: the template card lists all slots  (multi-slot-card.test.tsx)
    ├── ✅ TT-DD40-P15 one slot reads exactly as today: "Slot 4.2 s - 5.1 s"
    ├── ✅ TT-DD40-P16 two slots: "Slots 2 s - 3 s, 10 s - 11 s"
    ├── ✅ TT-DD40-P17 three slots with decimals: "Slots 1 s - 2.5 s, 3 s - 4 s, 10 s - 11.5 s"
    ├── ✅ TT-DD40-P18 an unconfirmed card shows the editor prefilled with the extra slots
    ├── ❌ TT-DD40-N12 no primary slot shows "No slot yet" (extra slots alone are not a slot)
    ├── ⚠️ TT-DD40-E9 a single slot never shows the plural "Slots"
    └── ✅ TT-DD40-P25 one slot and several slots print the numbers in the same format (table of values)
```

Mapping of plan acceptance criteria to tests:
- AC3 (PUT accepts extra_slots, empty list clears): TT-DD40-P8, P9, P10, N2.
- AC4 (template JSON has extra_slots and slots): fixtures in data.ts; TT-DD40-P5, P15, P16, P17.
- AC9 (Add button up to 5, Remove per extra slot, client checks, card lists all slots):
  TT-DD40-P1 to P4, E2, E3, N3 to N11, P15 to P18, P19 to P25.
- AC10 (one-slot template unchanged): TT-DD40-P15, E1, E9, P6.
- AC1 and AC2 (server rules) are covered by the backend tree, not here; the client mirrors them
  (5 slots, 0.2 s gap, no overlap).
