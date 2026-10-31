# Plan — Drafts visible and resumable; confirmed spelling survives a new preview

**Status:** Approved by the Admin on 2026-10-31 (DD-38; the Admin asked for these fixes).
**Decision record:** DD-38 in `docs/agents/ceo/DELEGATED-DECISIONS.md`.
**Branch:** `fix/draft-visibility-and-spelling`

## Goal

Fix three problems the Admin hit in local mode. No migration, no new dependency.

1. **BUG:** `Confirm spelling` then `Generate preview` brought back the original name, because `BatchFlow.request_preview` built a new preview record and dropped the confirmed spoken name. Fix: keep the confirmed spoken name when a preview is requested again; in the dashboard `Confirm spelling` now immediately requests a new preview with the confirmed spelling.
2. A batch that was created but not started (DRAFT) vanished after a reload: it was not in Running, Completed or Failed, and the Overview showed its rows as "Queued". Fix: new `GET /batches?view=drafts`; the Running page gets a "Not started" section listing drafts with `Continue setup` and `Delete draft`; on the Overview a draft shows `Continue setup` instead of `Start batch` and its tile reads `Not started`.
3. No way back into the wizard for a draft. Fix: `/batches/new?batch=<id>` resumes a draft at step 3 (or step 4 when the preview is approved); a draft without sheet data or a batch that is not a draft shows a clear message.

Facts recorded (no change to these):
- The dropdown "All" on the Overview Rows table is the row status filter.
- The "Videos to generate" choice is on wizard step 4.

Cause: DD-37 deliberately left drafts out of the three lists (a CEO design error: nothing showed them). The Overview "Start batch" on a draft bypasses wizard step 4.

## Acceptance criteria
1. Backend: after a spoken name is confirmed, requesting a new preview for the same batch keeps the confirmed spoken name on the new preview record; the original name is not restored.
2. Dashboard: `Confirm spelling` sends the confirmed spelling and immediately requests a new preview, so the preview shown next uses the confirmed spelling without a separate `Generate preview` click.
3. `GET /batches?view=drafts` returns only batches with status DRAFT; the existing Running, Completed and Failed views return the same results as before.
4. The Running page shows a "Not started" section that lists the drafts, each with `Continue setup` and `Delete draft`; batches that are running, completed or failed do not appear in that section.
5. On the Overview a draft shows `Continue setup` instead of `Start batch`, its tile reads `Not started`, and its rows are not shown as "Queued"; running, completed and failed batches keep their current buttons and labels.
6. `/batches/new?batch=<id>` for a draft with sheet data opens the wizard at step 3, or at step 4 when the preview is approved.
7. `/batches/new?batch=<id>` shows a clear message, creates no new batch and does not crash, when the draft has no sheet data or when the batch is not a draft.
8. No migration file and no new dependency are added; all existing tests still pass, and ruff, mypy, Vitest, typecheck, lint and build are green.

## Requirement tree
```
Feature: drafts visible and resumable; confirmed spelling survives a new preview (DD-38)
├── Functional
│   ├── R1  Confirmed spoken name kept on a new preview (fix 1, backend)
│   ├── R2  Dashboard Confirm spelling requests a new preview at once (fix 1, frontend)
│   ├── R3  GET /batches?view=drafts returns DRAFT batches only (fix 2, backend)
│   ├── R4  Running page "Not started" section: Continue setup, Delete draft (fix 2, frontend)
│   ├── R5  Overview: draft shows Continue setup, tile reads Not started (fix 2, frontend)
│   ├── R6  /batches/new?batch=<id> resumes at step 3, or step 4 when preview approved (fix 3)
│   └── R7  Clear message for a draft without sheet data or a non-draft batch (fix 3)
├── Non-functional
│   ├── Same auth and privacy rules as the other batch endpoints; the batch id is the only query value (no personal data in URLs)
│   └── No data loss on regenerate; a running batch is never changed by the draft work
├── Constraints
│   ├── No migration, no new dependency
│   ├── Tests first (TDD); Haiku agents with exact briefs; CEO verifies each step
│   └── Backend and frontend work in disjoint folders (DD-5)
├── Out of scope
│   ├── Moving the "Videos to generate" choice or the Rows status filter
│   └── Any change to the render pipeline
└── Open questions: none
```
Note for BE-GREEN: if the API has no route to delete a batch, backend-dev adds `DELETE /batches/{id}` that accepts DRAFT batches only, and says so in its report. The CEO reviews that route before merge.

## Test tree outline
See `docs/test-tree/draft-visibility-and-spelling.md` (tester writes it). Scenarios:
- **A. Confirmed name kept on regenerate** — P: name confirmed, new preview keeps it (also after two regenerations). N: preview requested for an unknown batch gives an error and creates no record. E: a Devanagari confirmed name is kept exactly; the name survives a page reload.
- **B. Drafts view and Overview** — P: `view=drafts` lists the drafts; the Running page shows the section with both buttons. N: a running batch is not listed; the draft tile never reads "Queued". E: no drafts (section hidden); a draft that starts leaves the section; a draft with zero rows.
- **C. Resume the wizard** — P: draft with sheet data opens at step 3; with an approved preview opens at step 4. N: draft without sheet data shows the message and creates nothing; a non-draft id shows the message. E: malformed or unknown batch id; a draft whose preview is being regenerated.

## Tasks

| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| BE-RED | Write failing backend tests for R1, R3 and the resume data needed by R6–R7 | tester | Writes tests only in its own folder; TDD red step | — (parallel with FE-RED) | haiku | No (disjoint folders, DD-5) | Tests collect and fail only because the behaviour is missing |
| FE-RED | Write failing UI tests for R2, R4, R5, R6, R7 | tester | Writes UI tests only in `tests/frontend/`; TDD red step | — (parallel with BE-RED) | haiku | No (disjoint folders, DD-5) | Tests fail only because the behaviour is missing |
| BE-GREEN | Keep the confirmed name on a new preview; drafts view; resume data; delete-draft route if none exists | backend-dev | Owns `backend/`; implements the API | BE-RED | haiku | No | Backend tests green; ruff and mypy clean; no migration |
| FE-GREEN | Dashboard: Not started section, Overview draft button and tile, Confirm spelling regenerates, `?batch=` resume and messages | frontend-dev | Owns `frontend/`; implements the UI | FE-RED (API shape fixed in this plan) | haiku | No (parallel with BE-GREEN, disjoint folders) | Vitest, typecheck, lint and build green |
| VERIFY | Run all suites; restart the Admin's local app with `scripts/dev_up.sh`; check fixes 1–3 by hand | CEO | Owns review and the merge gate | BE-GREEN, FE-GREEN | haiku | No | All suites green; app restarted; three fixes checked |
| PR | Open PR `fix/draft-visibility-and-spelling` → `main` with a summary of the diff | CEO | Owns the PR; the Admin decides the merge | VERIFY | haiku | No | PR open; merge waits for Admin |

API contract used by both GREEN tasks: `GET /batches?view=drafts` returns the same item shape as the existing batch list responses (backend-dev confirms this in its report).

## Order (TDD)
1. BE-RED and FE-RED in parallel (tester), red only.
2. BE-GREEN and FE-GREEN in parallel (backend-dev, frontend-dev), green and tidy; developers do not edit tests.
3. VERIFY (CEO): full suites, then restart of the Admin's app, then manual check of the three fixes.
4. PR; the Admin decides whether to merge.

tester (red) → developers (green + refactor) → CEO verify → Admin approves merge

## Risks
1. **Resuming a draft depends on the stored sheet report.** If a draft has no stored report, the wizard cannot return to step 3. Mitigation: criterion 7 shows a clear message instead of a broken wizard.
2. **The preview regenerate must not lose the confirmed name.** Mitigation: criterion 1 and scenario A test it at the backend; criterion 2 tests it in the dashboard.
3. **The Overview button change must not break running batches.** Mitigation: `Continue setup` is shown only for DRAFT; criterion 5 requires running, completed and failed batches to keep their buttons and labels.

## Migrations / dependencies (need separate approval)
- Migrations: **none.** If a change needs a column that is not in the schema, backend-dev stops and reports to the CEO; a migration needs Admin approval.
- Dependencies: **none.**

## Admin approval
- [x] Plan approved (DD-38, 2026-10-31)
- [ ] Task assignment approved
- [ ] Merge approved
