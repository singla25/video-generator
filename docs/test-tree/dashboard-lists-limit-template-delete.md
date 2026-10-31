# Test tree: dashboard lists, start limit, template delete, new template form (DD-37)

Decision: DD-37. Tests: `tests/frontend/unit/batch-list-pages.test.tsx` (A), `start-limit.test.tsx` (B), `template-delete.test.tsx` (C), `new-template-form.test.tsx` (D). E2E lines for the new template form updated in `tests/frontend/e2e/full-flow.spec.ts`. Old structure asserted in `tests/frontend/unit/new-template.test.tsx` (TT-UI-AC7-P3, N3, N4) is updated to the new structure.

Case IDs: `TT-DD37-<A|B|C|D>-<P|N|E><n>`. Status at red: 72 new tests fail (missing feature), 5 new guard tests pass (behaviour that must keep working).

```
Feature: A. Batch list pages Running, Completed, Failed
├── Scenario: opening a list page from the sidebar
│   ├── ✅ P1 /batches/running|completed|failed render the table, not "is coming soon"
│   ├── ✅ P2 each view asks GET /batches?page=1&page_size=50&view=<its view>
│   └── ❌ N1 an empty view shows "No running|completed|failed batches"
├── Scenario: reading a row
│   ├── ✅ P3 headers exactly Batch, Template, Progress, Rows, Created
│   ├── ✅ P4 a full row reads name, template, "75 %", "100 rows · 10 failed", date
│   ├── ✅ P5 the batch name links to /batches/<id>
│   ├── ✅ P6 name falls back: sheet name, then folder name, then "Batch"
│   ├── ✅ P7 progress = (completed + failed + skipped) / total, rounded (33 %, 67 %, processing not counted)
│   ├── ✅ P8 template column shows the template name
│   ├── ✅ P9 created column shows the date like History
│   ├── ⚠️ E1 zero rows shows "-" progress and "0 rows"
│   ├── ⚠️ E2 zero failures omit "· n failed"
│   └── ❌ N4 a template id not in the list shows "-"
├── Scenario: paging
│   ├── ✅ P10 Next and Previous move page; "Page 2 of 3"
│   ├── ⚠️ E3 a single page disables both buttons ("Page 1 of 1")
│   └── (paging buttons follow History)
├── Scenario: API failure
│   ├── ❌ N2 role=alert "Could not load batches" with a Retry button
│   └── ❌ N3 Retry asks again and shows the list
├── Scenario: live refresh
│   ├── ✅ P11 running view refetches every 5 s
│   ├── ✅ P12 completed and failed views do not poll
│   └── ⚠️ E4 leaving the running page stops polling
└── (no other edge cases: all counted above)

Feature: B. Wizard step 4 "Videos to generate" and the start limit
├── Scenario: choosing how many videos
│   ├── ✅ P1 radio group with All N rows (selected), First 5, First 10, First 15, Custom
│   ├── ✅ P2 with 8 rows First 5 enabled, First 10 and First 15 disabled
│   ├── ✅ P3 with 20 rows all fixed options enabled
│   ├── ✅ P4 summary "You will get 5 videos. The other 3 rows are skipped." and "You will get 8 videos."
│   ├── ✅ P5 Custom reveals "Number of videos"; typing 3 gives the 3 of 8 summary
│   ├── ✅ P6 "Number of videos" has min 1 and max N
│   └── ⚠️ E3 with 20 rows First 15 is allowed (limit 15)
├── Scenario: start request body
│   ├── ✅ P7 First 5 posts {folder_name, limit: 5}
│   ├── ✅ P8 All posts {folder_name} with no limit key (guard, passes today)
│   ├── ✅ P9 Custom 3 posts limit 3
│   ├── ✅ P10 Idempotency-Key header still sent
│   ├── ✅ N1 switching back to All drops the limit
│   └── ⚠️ E2 Custom equal to N is accepted and sends no limit
├── Scenario: invalid custom number
│   ├── ❌ N2 0, a negative, empty, or 9 (above 8): Review and start disabled, "Enter a number from 1 to 8"
│   ├── ❌ N3 an invalid number sends nothing and opens no dialog
│   └── ⚠️ E1 bounds 1 and N-1 (1 and 7 for 8 rows) are sent as the limit
└── Scenario: few rows
    └── ⚠️ E4 a single valid row disables all fixed options

Feature: C. Delete a template from its card
├── Scenario: opening the confirmation
│   ├── ✅ P1 every card has "Delete template"
│   └── ✅ P2 dialog "Delete this template?" with "This cannot be undone.", Delete, Cancel
├── Scenario: confirming
│   ├── ✅ P3 Delete sends DELETE /templates/<id>; dialog closes; card disappears
│   ├── ✅ P4 the templates list is refetched after the delete
│   ├── ⚠️ E3 deleting the last template shows "No templates yet"
│   ├── ⚠️ E1 Delete is disabled while the request runs
│   └── ⚠️ E2 double click sends one DELETE
├── Scenario: cancelling or failing
│   ├── ✅ N1 Cancel closes the dialog and sends nothing
│   ├── ❌ N2 409 keeps the dialog open; the API message ("This template is used by 2 batches...") in role=alert
│   └── ❌ N3 network failure keeps the dialog and the card, with an alert

Feature: D. New template form (drop zone)
├── Scenario: the layout
│   ├── ✅ P1 drop zone named "Template video" with "Drop the video here or choose a file" and a video input
│   ├── ✅ P2 "Word to replace" with helper text and the consent reminder line
│   └── ✅ P3 Cancel and Upload template are offered
├── Scenario: choosing a video
│   ├── ✅ P4 chosen video shows "intro.mp4 · 0.1 MB" (one decimal)
│   ├── ✅ P5 "Remove file" clears the choice
│   ├── ✅ P6 a dropped video behaves like a chosen one
│   ├── ✅ P7 size line has one decimal for a larger file
│   ├── ✅ P8 Upload enabled only when a file is chosen and the word is not blank (guard, passes today)
│   ├── ✅ P9 multipart upload with the trimmed word (guard, passes today)
│   ├── ⚠️ E2 unicode and spaces in the file name are shown intact
│   └── ⚠️ E3 after Remove file a new video can be chosen
├── Scenario: refusing a file
│   ├── ❌ N1 a non-video file: role=alert "Choose a video file.", not shown, Upload disabled
│   ├── ❌ N2 a dropped non-video file is refused the same way
│   ├── ❌ N3 an .mp4 name with a non-video MIME type is refused (the MIME type decides)
│   └── ⚠️ E1 a word of spaces only keeps Upload disabled (guard, passes today)
└── Scenario: Cancel
    └── ✅ P3 (see Layout) Cancel stays
```

## Acceptance mapping

| Contract item | Cases |
|---|---|
| A. Batch list pages, routes, columns, progress, empty, error, paging, polling | A-P1..P12, A-N1..N4, A-E1..E4 |
| B. Wizard step 4 "Videos to generate", limit, custom number | B-P1..P10, B-N1..N3, B-E1..E4 |
| C. Template delete dialog, 204, 409, disabled while pending | C-P1..P4, C-N1..N3, C-E1..E3 |
| D. New template drop zone, file summary, refusal, helper text | D-P1..P9, D-N1..N3, D-E1..E3 |
