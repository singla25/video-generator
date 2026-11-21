# Test tree: better name detection, dashboard (A-N2, BL-6 AC5)
Test file: tests/frontend/unit/name-candidates.test.tsx

```
Feature: Closest-match candidate buttons in the slot editor
├── Scenario: analysis found no slot but returned candidates
│   ├── ✅ 1, 2, 3 candidates -> one list item and one "Use this word" button each (NC-P1)
│   ├── ✅ best first; word, "1.2-1.7 s", "80% close" for 0.804 (NC-P2)
│   └── ✅ click sets the slot via PUT, group disappears, still needs "Confirm slot" (NC-P3)
├── Scenario: no usable candidates
│   ├── ❌ empty list -> today's message, no group (NC-N1)
│   ├── ❌ slot found -> no group (NC-N2)
│   └── ❌ old response without the field -> treated as empty (NC-N3)
├── Scenario: picking fails
│   └── ❌ 409 and 500 -> message in role="alert", group kept (NC-N4)
└── Scenario: odd cases
    ├── ⚠️ very long and Devanagari words shown whole (NC-E1)
    ├── ⚠️ double click -> one request; all buttons disabled while pending (NC-E2)
    ├── ⚠️ new analyse clears earlier candidates (NC-E3)
    └── ⚠️ candidates not kept after leaving the page (NC-E4)
```
