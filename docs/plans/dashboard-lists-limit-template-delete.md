# Plan — Dashboard: real batch lists, "how many videos", delete template, better template form

Status: Approved by the Admin on 2026-10-31 (DD-37).

## Goal
The Admin tried local mode and asked for four dashboard changes: (1) the Running, Completed and Failed pages show real batch lists instead of "coming soon"; (2) after the sheet upload, the wizard asks how many videos to generate (all, first 5, first 10, first 15, or a custom number); (3) templates can be deleted; (4) the "New template" form is easier to use.

## Acceptance criteria
1. `GET /batches?view=all|running|completed|failed` returns only the batches that match the view: running = RUNNING or PAUSED; completed = COMPLETED with no failed rows; failed = RUNNING, PAUSED or COMPLETED with at least one failed row; `all` returns every batch except DRAFT and CANCELLED; DRAFT and CANCELLED batches are never listed in any view; an unknown `view` value is refused with a clear client error.
2. The Running, Completed and Failed dashboard pages show the real batch list from that endpoint (with the same rules as AC1); the "coming soon" placeholders are gone from these three pages.
3. `POST /batches/{id}/start` accepts an optional `limit`. With `limit = N`, the first N rows (in sheet order) are rendered; every other row becomes `SKIPPED` with failure code `NOT_SELECTED` and the message "Not selected: outside the number of videos requested.", and no video is rendered for it.
4. Without `limit`, or with a `limit` at or above the row count, every row is rendered and no row is `SKIPPED`. A `limit` of 0 or below, or a value that is not a whole number, is refused with a clear client error and the batch does not start.
5. On the last wizard step, "How many videos?" offers All N rows, First 5, First 10, First 15 and a custom number; the chosen value is sent with the start request. The custom number accepts whole numbers from 1 to the row count (default rule chosen by the CEO; see Requirement tree). The number is set at start only; there is no "generate the rest" action.
6. `DELETE /templates/{id}` returns 204 and removes the template, its consent records and its stored files when no batch uses it. When any batch uses the template it returns 409 with code `TEMPLATE_IN_USE` and removes nothing. An unknown id returns 404.
7. The dashboard Delete button on a template opens a confirmation dialog. The template is deleted only after the user confirms; Cancel changes nothing. A 409 `TEMPLATE_IN_USE` answer is shown as a clear message in the dialog.
8. The "New template" form has a drop zone (click and drag and drop), shows the chosen file name and size, has helper text under the fields, and shows clear empty, uploading, error and done states. The existing upload behaviour is unchanged: the same accepted file types, the same API call and the same validation messages.

## Requirement tree
```
Dashboard: real lists, start limit, delete template, template form
├── Functional
│   ├── R1  Batch list views: GET /batches?view=all|running|completed|failed (AC1, AC2)
│   ├── R2  Start limit: optional `limit` on POST /batches/{id}/start; rows beyond it -> SKIPPED / NOT_SELECTED (AC3, AC4)
│   ├── R3  Wizard step "How many videos?": All N rows, First 5/10/15, custom number (AC5)
│   ├── R4  Delete template: DELETE /templates/{id}; 409 TEMPLATE_IN_USE when any batch uses it (AC6)
│   ├── R5  Delete confirmation dialog in the dashboard (AC7)
│   └── R6  New template form: drop zone, file name and size, helper text, clear states (AC8)
├── Non-functional
│   ├── Stays stateless API; list queries use the database, not Python-side filtering of all batches
│   ├── Deleting stored files is irreversible: the in-use check runs before any file is removed
│   └── Mobile width works (16 px gutter, no horizontal scroll) on the changed pages
├── Constraints
│   ├── No database migration: failure codes and statuses are text; if a database check constraint blocks NOT_SELECTED the developer stops and reports
│   ├── No new dependency
│   ├── Tests first (TDD red -> green -> verify)
│   └── Haiku agents with exact briefs, verified by the CEO
├── Out of scope
│   ├── Setting the number after start ("generate the rest")
│   ├── Undo for a deleted template
│   └── Changes to the render pipeline beyond skipping unselected rows
└── Open questions (must be empty)
    └── none (defaults chosen by the CEO: custom number = whole number 1..row count; a template in use by any batch cannot be deleted; the number is set at start only)
```

## Test tree outline
See docs/test-tree/dashboard-lists-limit-template-delete.md (tester expands this outline).
- View filter (AC1): positive per view; negative unknown view; edge: DRAFT and CANCELLED excluded, failed view paginates correctly under the subquery.
- Start limit (AC3, AC4): positive limit N; negative limit 0, negative, non-integer; edge limit above row count, no limit, single-row batch.
- Delete template (AC6): positive unused template removed with consent records and files; negative in-use 409 nothing removed, unknown 404; edge template used only by a CANCELLED or DRAFT batch is still refused (any batch that uses it blocks deletion).
- UI (AC2, AC5, AC7, AC8): list pages render rows and empty state; wizard limit choices and custom number bounds; delete dialog confirm and cancel and 409 message; template form states and unchanged upload.

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| BE-RED | Write failing backend tests for AC1, AC3, AC4, AC6 | tester | Tester owns `tests/` and writes tests from the acceptance criteria before code | — | haiku | Yes (feat/tester/dd37-be-red) | Tests collect and fail for the right reason; reported to CEO |
| FE-RED | Write failing UI tests for AC2, AC5, AC7, AC8 (API mocked to the contract in this plan) | tester | Tester owns `tests/` and the UI test tree; runs in parallel with BE-RED | — | haiku | Yes (feat/tester/dd37-fe-red) | Tests collect and fail for the right reason; reported to CEO |
| BE-GREEN | Views filter, start limit with NOT_SELECTED, template delete with in-use check and file removal | backend-dev | Backend-dev owns `backend/` (API, services, storage, database) | BE-RED | haiku | Yes (feat/backend/dd37-green) | BE tests pass; no test edited; ruff, mypy clean |
| FE-GREEN | Three list pages, "How many videos?" step, delete dialog, new template form | frontend-dev | Frontend-dev owns `frontend/` (UI); runs in parallel with BE-GREEN against the fixed API contract | FE-RED | haiku | Yes (feat/frontend/dd37-green) | FE tests pass; no test edited; lint clean |
| VERIFY | Full backend and frontend suites; Playwright screenshots of the four changes (list pages, limit step, delete dialog, new template form) | tester | Tester owns verification and coverage and reports the screenshots | BE-GREEN, FE-GREEN | haiku | No | Full suites green; coverage reported; screenshots saved for the CEO |
| CEO-REVIEW | Review diffs, run pytest, ruff, mypy; open the PR | ceo | CEO reviews every diff against CLAUDE.md §4 | VERIFY | haiku | No | Review notes clean; PR opened; Admin approves merge |

## Order (TDD)
tester (red: BE-RED and FE-RED in parallel) → developers (green: BE-GREEN and FE-GREEN in parallel) → tester (verify) → CEO review → Admin approves merge

## Risks
1. Pagination under the failed filter needs a database subquery (rows with status FAILED must be counted per batch in the query, not in Python). Mitigation: BE-RED includes a paging test with more batches than one page; CEO checks the query plan.
2. Deleting stored files is irreversible. Mitigation: the in-use check and the file removal run in one service call, the check runs first, and the dashboard shows a confirmation dialog before the request is sent.
3. The new template form must keep the existing upload behaviour. Mitigation: AC8 names the unchanged parts; FE-RED keeps the existing upload tests and adds new ones beside them.

## Migrations / dependencies (need separate approval)
- Database migration: none planned. If `NOT_SELECTED` is blocked by a database check constraint, the developer stops and reports to the CEO; a migration then needs separate Admin approval.
- New dependencies: none.

## Admin approval
- [x] Plan approved (2026-10-31, DD-37)
- [ ] Task assignment approved
- [ ] Merge approved
