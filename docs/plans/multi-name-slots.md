# Plan — Several name slots per template (DD-40)

**Status:** Approved by the Admin on 2026-10-31 (DD-40)
**Branch:** feat/multi-slot
**Decision record:** docs/agents/ceo/DELEGATED-DECISIONS.md (DD-40)

## Goal

A template can have several name slots. The Admin's video says the name at 2–3 s and again at 10–11 s, and the app supported only one slot. With this change the same person's name is spoken at each slot, and each slot is lip-synced and labelled as the single slot is today.

## Acceptance criteria
1. A template holds at most 5 name slots in total (the primary slot plus extra slots). A request that would make a sixth slot is rejected with a clear validation error and nothing is saved.
2. Slots are sorted by start time. Any two consecutive slots are at least 0.2 s apart and never overlap. Otherwise the request is rejected with failure code `SLOTS_INVALID` and message "The name slots overlap or are too close.", and nothing is saved.
3. Each slot is valid on its own, with the same rules as the primary slot today. `PUT /templates/{id}/slot` accepts an optional `extra_slots` list of `[start, end]`. Omitting it keeps the current extra slots, and an empty list clears them.
4. The template JSON contains `extra_slots` and `slots`. `slots` is the sorted list of all slots. A template without extra slots shows exactly one slot and reads as before. Migration `0002` only adds the nullable `extra_slots` column, and existing rows read as "no extra slots".
5. The approval fingerprint includes the extra slots. Changing them makes an approved preview stale, so it must be approved again before a batch can use it.
6. The spoken name (name plus the global suffix) is generated once per row and the same audio is reused at every slot.
7. Lip sync runs once per slot in ascending order. Each pass starts at its slot's `start_s` and reads the face boxes from the template (`key_from`). Face boxes are not recomputed for later slots.
8. The encoder runs once per slot, from the last slot to the first. Each pass takes the previous pass's output as input. Only the pass for the first slot draws the AI label and writes the metadata; earlier passes use a 1x1 transparent label image.
9. The dashboard slot editor has "Add another name slot" (up to 5 slots) and a "Remove slot N" button per extra slot, runs client-side overlap and gap checks, and the template card lists all slots.
10. A one-slot template behaves exactly as before: same pipeline calls, same output and metadata, and every existing test still passes. The total video length grows by the sum over extra slots of (0.25 s gap + that slot's extension). No new dependency is added.

## Requirement tree
```
Feature: several name slots per template
├── Functional
│   ├── R1  Up to 5 slots per template (primary + extra)            → AC1
│   ├── R2  Slots sorted; >= 0.2 s apart; no overlap (SLOTS_INVALID) → AC2
│   ├── R3  Each slot valid as today; PUT /templates/{id}/slot extra_slots → AC3
│   ├── R4  Template JSON: extra_slots + slots; migration 0002 additive → AC4
│   ├── R5  Fingerprint includes extra slots (stale preview)        → AC5
│   ├── R6  One spoken name per row, reused at every slot           → AC6
│   ├── R7  Lip sync once per slot, ascending, key_from = template  → AC7
│   ├── R8  Encoder once per slot, last to first; label only on first slot → AC8
│   ├── R9  Dashboard: Add another name slot, Remove slot N, card lists slots → AC9
│   └── R10 One-slot templates unchanged; length grows by sum of gap + extension → AC10
├── Non-functional
│   ├── Quality: one extra encode generation (CRF 18) per extra slot
│   ├── Time: one extra lip-sync pass and one extra encode pass per extra slot
│   ├── Scale: API stays stateless; no new queue or storage
│   └── Security: no new endpoint; input validated server-side
├── Constraints
│   ├── Additive migration only (0002); the Admin runs it after a rehearsal
│   ├── No new dependency
│   ├── Tests first (Red → Green → Refactor → Verify)
│   ├── Haiku agents with exact briefs; the CEO verifies each step
│   └── One-slot templates behave exactly as before
├── Out of scope
│   ├── Automatic detection of every occurrence of the word (extra slots are added by hand)
│   ├── A different spoken text per slot
│   └── A per-slot suffix
└── Open questions (must be empty): none
```

## Test tree outline
See docs/test-tree/multi-name-slots.md (tester writes it in BE-A-RED / BE-B-RED / FE-RED).
- Scenario: slot validation (AC1, AC2, AC3)
  - Positive: slots 2–3 s and 10–11 s saved; the list is returned sorted.
  - Negative: a sixth slot rejected; overlap rejected with SLOTS_INVALID and the exact message; nothing saved.
  - Edge: exactly 0.2 s apart accepted; 0.19 s rejected; empty list clears extra slots; slots given unsorted are sorted.
- Scenario: template API and migration (AC3, AC4)
  - Positive: PUT with extra_slots; GET shows extra_slots and slots.
  - Negative: malformed extra_slots (wrong shape, non-numbers) rejected, nothing saved.
  - Edge: an old row with NULL extra_slots reads as no extra slots; omitting extra_slots keeps them.
- Scenario: fingerprint (AC5)
  - Positive: changing extra slots marks an approved preview stale.
  - Edge: re-saving identical extra slots does not make it stale.
- Scenario: pipeline (AC6, AC7, AC8)
  - Positive: two slots give one voice generation, two lip-sync passes ascending, two encode passes last to first.
  - Negative: a lip-sync failure on the second slot fails the job cleanly with no partial output.
  - Edge: boxes read from the template (key_from) and not recomputed; the first pass alone draws the AI label; the intermediate pass uses the transparent 1x1 label.
- Scenario: one-slot regression (AC10)
  - Positive: a one-slot template gives the same calls, output and metadata as before.
  - Edge: length growth equals the sum of (0.25 s + extension) per extra slot.
- Scenario: dashboard (AC9)
  - Positive: Add another name slot adds a row; Remove slot N removes it; card lists all slots.
  - Negative: a sixth slot is blocked; overlap is shown before saving.
  - Edge: adding the fifth slot enables no further adds; removing the primary slot is not offered.

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| BE-A-RED | Failing tests: model, slot validation, DB column, migration 0002, API, fingerprint | tester | Writes the test trees and failing tests first (TDD red); does not touch backend/ | — | haiku | Yes: feat/tester/multi-slots-be-a-red | Tests fail for the right reason; test tree in docs/test-tree/multi-name-slots.md |
| BE-B-RED | Failing tests: pipeline (one voice, lip sync per slot, key_from, encoder order, transparent label, length) | tester | Pipeline tests are the tester's domain; developers never edit tests | — | haiku | Yes: feat/tester/multi-slots-be-b-red | Tests fail for the right reason |
| FE-RED | Failing tests: slot editor, add/remove, client checks, template card | tester | UI tests are written by the tester before the frontend-dev builds | BE-A-RED (API shape is fixed in this plan) | haiku | Yes: feat/tester/multi-slots-fe-red | Tests fail for the right reason |
| BE-A-GREEN | Model, validation, DB column, migration 0002 (file only), API, fingerprint | backend-dev | Owns backend/ and the model and API code | BE-A-RED | haiku | Yes: feat/backend/multi-slots-model | BE-A tests pass; ruff, mypy strict on new modules green |
| BE-B-GREEN | Pipeline: one voice, lip sync per slot with key_from, encoder per slot, transparent intermediate label | backend-dev | Owns the video pipeline in backend/ | BE-B-RED, BE-A-GREEN (reads TemplateRecord.slots) | haiku | Yes: feat/backend/multi-slots-pipeline | BE-B tests pass; one-slot regression tests unchanged and green |
| FE-GREEN | Slot editor, Add/Remove slot, client checks, template card | frontend-dev | Owns frontend/ | FE-RED, BE-A-GREEN | haiku | Yes: feat/frontend/multi-slots-editor | FE tests pass; typecheck, lint, build green |
| MIG | Rehearse migration 0002 on a throwaway database; the Admin runs the real one later | backend-dev | Owns the database code and migration files | BE-A-GREEN | haiku | No | Rehearsal log shows additive change and old rows read as before |
| DEMO | Synthetic two-name marketing template (script option, names at two slots) | backend-dev | Owns the demo script under backend/ | BE-B-GREEN, MIG | haiku | No | Script builds the template; sample outputs listed |
| ADMIN-MIG | Run migration 0002 on the Admin's real database | Admin | Running a migration needs the Admin's approval (CLAUDE.md §2.3) | MIG | — | No | Admin confirms the run |
| VERIFY | Full suites, E2E, and a real two-slot render on the Admin's Mac; coverage and lint | tester | Verifies independently of the developers; owns tests/ and coverage | DEMO, ADMIN-MIG, FE-GREEN | haiku | No | Suites green; coverage >= 85 % on new code; render approved by Admin |
| PR | Pull request for feat/multi-slot; CEO diff review; merge only after Admin approval | CEO | Only the CEO reviews and merges (CLAUDE.md §4) | VERIFY | — | No | PR open; Admin answers the merge question |

## Order (TDD)
1. Red: BE-A-RED, BE-B-RED and FE-RED run in parallel, each in its own worktree.
2. Green: BE-A-GREEN first; then BE-B-GREEN and FE-GREEN (FE-GREEN in parallel with BE-B-GREEN).
3. Migration: MIG rehearsal on a throwaway database; the Admin then runs ADMIN-MIG.
4. Demo and verify: DEMO, then VERIFY (suites, E2E, real two-slot render).
5. CEO review, then PR. Admin decides on merge.

Every Haiku brief uses the CEO template (TASK ID, GOAL, CONTEXT, ACCEPTANCE CRITERIA, FILES YOU MAY TOUCH, TESTS, DO NOT, REPORT BACK). The CEO checks each diff and runs pytest, ruff and mypy before accepting a step.

## Risks
1. Two encode generations (CRF 18) cost a little quality. Mitigation: the Admin checks the two-slot render in VERIFY; the number of extra generations is capped by the 5-slot limit.
2. The second and later lip-sync passes must read face boxes from the template, not recompute them. Mitigation: `key_from` is a tested argument; a test fails if boxes are recomputed.
3. Slot validation must reject overlaps and near-overlaps. Mitigation: server-side check in the model (AC2) and the same check in the dashboard; both have negative and edge tests.
4. The migration must be additive and rehearsed. Mitigation: migration 0002 adds only a nullable column; MIG rehearses it on a throwaway database; the Admin runs the real one.

## Migrations / dependencies (need separate approval)
- **Migration 0002 (additive):** adds the nullable JSON column `extra_slots` to the templates table. Creating the file is allowed; running it needs the Admin's approval (ADMIN-MIG). Rehearsed first on a throwaway database (MIG).
- **Undo:** do not run the migration, or revert the merge commits. A template with no extra slots behaves as before.
- **Dependencies:** none added.

## Admin approval
- [x] Plan approved (DD-40, 2026-10-31)
- [x] Task assignment approved (DD-40, 2026-10-31)
- [ ] Migration 0002 run (separate approval, ADMIN-MIG)
- [ ] Merge approved
