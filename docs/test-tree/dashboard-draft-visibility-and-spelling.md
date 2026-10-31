# Test tree: draft visibility, wizard resume, confirm regenerates (DD-38)

Decision: DD-38. Frontend tests: `tests/frontend/unit/preview-confirm-regenerate.test.tsx` (A), `running-drafts.test.tsx` (B), `overview-draft.test.tsx` (C), `wizard-resume.test.tsx` (D). Old tests changed to the contract: `overview.test.tsx` TT-UI-AC3-P10 and `overview-batch-controls.test.tsx` TT-UI-CTL-P2 (DRAFT "Start batch" becomes "Continue setup").

Case IDs: `TT-DD38-<A|B|C|D>-<P|N|E><n>`.

Status at red: 54 new tests. 36 fail, each only because the feature is missing (missing link, heading, text, or request). 18 are guard tests that pass at red and must keep passing. Old tests changed to the contract: 2 (both fail at red until the feature lands).

```
Feature: A. Confirm spelling regenerates the preview (PreviewPanel)
├── Scenario: confirming a spoken name
│   ├── ✅ P1 confirm POSTs {spoken_name}, then POST /preview, in that order
│   ├── ✅ P2 the panel shows "Generating preview..." after the new preview starts
│   └── ✅ P3 the hint "Confirm to hear the preview with this spelling." is shown under the field
├── Scenario: confirm fails
│   ├── ✅ N1 409 or 500 on confirm: no preview request, the error shows in role=alert
│   └── ✅ N2 after a failed confirm the Approve button stays disabled (no new preview)
└── Scenario: edge cases
    ├── ❌ E1 confirming the unchanged suggestion still regenerates
    ├── ⚠️ E2 a whitespace-only spelling disables Confirm and sends nothing (guard)
    └── ❌ E3 a long spelling with a space is sent unchanged

Feature: B. Not started drafts on the Running page
├── Scenario: a draft exists
│   ├── ❌ P1 a "Not started" section appears below the running list
│   ├── ❌ P2 its table headers are exactly Batch, Template, Rows, Created, Actions
│   ├── ❌ P3 each row has a "Continue setup" link to /batches/new?batch=<id>
│   ├── ❌ P4 a row shows its sheet name, template name, row count and created date
│   ├── ❌ P5 "Delete draft" opens "Delete this draft?", then DELETE /batches/<id> and a refetch
│   ├── ❌ P6 the list asks GET /batches?page=1&page_size=50&view=drafts
│   └── ❌ P7 several drafts give one row each
├── Scenario: no draft exists
│   ├── ✅ N1 no "Not started" heading, no "Continue setup" link, only the running table
│   ├── ❌ N2 running empty and drafts present: "No running batches" and the section both show
│   └── ✅ N3 running empty and no drafts: only "No running batches"
├── Scenario: failures and cancel
│   ├── ❌ N4 Keep closes the dialog and sends no DELETE
│   ├── ❌ N5 a failed DELETE shows its message and keeps the row
│   └── ❌ E1 double click on Delete sends one DELETE
└── Scenario: other views never ask for drafts
    ├── ✅ E2 the completed and failed views never call view=drafts
    └── ❌ E3 the running view asks for drafts with the same paging as the list

Feature: C. Overview for a DRAFT current batch (CurrentBatchPanel, KpiCards)
├── Scenario: the current batch is a draft
│   ├── ❌ P1 the primary button is the link "Continue setup" to /batches/new?batch=<id>
│   ├── ✅ P2 "Delete draft" stays
│   ├── ❌ P3 the KPI tile that said "Queued" says "Not started" and keeps its number
│   ├── ✅ P4 the other KPI labels stay the same
│   ├── ❌ N1 no "Start batch" link for a draft
│   ├── ✅ N2 no Pause, Resume or Cancel batch for a draft
│   ├── ❌ E1 a draft with zero queued rows still reads "Not started" with 0
│   └── ❌ E2 clicking "Continue setup" leaves the Overview for the wizard
└── Scenario: other statuses keep today's labels
    ├── ✅ N3 RUNNING: tile "Queued", "View batch", Pause shown, no "Continue setup"
    ├── ✅ N4 PAUSED: tile "Queued", Resume shown, no "Continue setup"
    └── ✅ N5 COMPLETED: tile "Queued", "View batch", no "Delete draft"

Feature: D. Resume a batch from /batches/new?batch=<id> (WizardPage)
├── Scenario: the batch cannot be continued
│   ├── ❌ N1 404 shows "This batch can't be continued." and a "Back to Overview" link
│   ├── ❌ N2 RUNNING, COMPLETED or CANCELLED shows the same message
│   └── ❌ E1 "Back to Overview" opens the Overview
├── Scenario: a draft with no sheet data
│   ├── ❌ P1 DRAFT with report null or missing: "This draft has no sheet data yet. Delete it and upload the sheet again." and a "Delete draft" button
│   ├── ❌ N3 Delete draft asks first; Keep sends nothing
│   ├── ❌ N4 a failed DELETE shows its message and stays on the page
│   ├── ❌ P2 confirm Delete sends DELETE /batches/<id>, then opens the Overview
│   └── ❌ E2 a double click on confirm sends one DELETE
├── Scenario: a draft with sheet data and an unapproved preview
│   ├── ✅ P3 opens step 3 "Slot & preview" (NONE, READY, STALE)
│   └── (step 3 template slot is covered by wizard.test.tsx TT-UI-AC5-P6)
├── Scenario: a draft with sheet data and an approved preview
│   ├── ❌ P4 opens step 4 "Output & start" with the output folder
│   └── ❌ P5 step 4 counts report.valid_rows (Review and start asks "Start 5 videos?")
└── Scenario: no batch parameter
    ├── ✅ P6 /batches/new opens step 1 "Upload" and fetches no batch
    └── (no edge cases beyond the above)
```

Notes on the contract left open (not tested, see the report): a draft with `valid_rows: 0` and an unapproved preview (contract says step 3, the old code said step 2); the failure message location for a failed Delete draft in the wizard (only "role=alert" is asserted).
