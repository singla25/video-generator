# Frontend developer — Changelog

Newest first. One entry per task.

## 2026-10-28 - FIX-WORKER-3
- `useSystemStatus` (2 s polling of GET /system/status) and `useBatchList({poll})` in `api/queries.ts`; `SystemStatus` type; `SLOW_PREVIEW_MS` in `config.ts`.
- `layout/WorkerBanner.tsx` in the app shell: role=alert, only when worker_alive is false and a batch has queued rows or a pending preview; silent while loading or failing.
- `PreviewPanel`: after 30 s pending shows "Preview is taking longer than expected" (names the worker only when the status read says it is down) plus Retry.
- Tests: worker-health.test.tsx 24/24; full suite 313/313. Open: none.

## 2026-10-28 - FIX-UPLOAD-3
- Uploads (wizard sheet, Validate sheet, new template, consent) go through one XHR helper `apiUpload` in `src/api/client.ts` (CSRF, 401, error envelope, plain-words messages for 413/500/503/network/timeout) and the `useUpload` hook (progress, error, Retry, cancel, abort on unmount, one request at a time).
- `UploadFeedback` shows role=progressbar or the error via `ErrorState` (new `retryLabel` prop). Consent refuses 0-byte files.
- `test-support/xhr-formdata.ts` (Vitest setup in `vite.config.ts`): jsdom XHR cannot send the Node FormData that tests/setup installs, so it is encoded as multipart. Test-only.
- Tests: upload-feedback.test.tsx green, Vitest 277/277. Playwright not run (needs the backend).

## 2026-10-20 - W-4 fixes
- Batch detail header and ring use the counts of the rows page (same snapshot as the table); rows refetch after every status poll. Current-batch panel shows completed / renderable and skipped separately.
- Files: `BatchDetailPage.tsx`, `RowsTable.tsx`, `CurrentBatchPanel.tsx`, `api/types.ts`. Vitest 209 pass. Open: none.

## 2026-10-20 - DD-21/22/23 fixes
- `API_PREFIX = '/api'` (client `apiUrl`, all download/video hrefs, dev proxy forwards only `/api`).
- Slot editor with Confirm slot / "Slot confirmed" on the Templates card and wizard step 3 (explicit confirm; preview no longer auto-confirms).
- `chipColors.ts` AA colour pairs applied inline; chart uses a fixed-width BarChart (hatch fills now render in jsdom) and weekly buckets are calendar-based.

## 2026-10-19 - F6 prep (DD-18, DD-19)
- Removed `test-support/` and its setupFiles entry (glue now lives in tests/frontend/support).
- RowsTable row Retry posts `/batches/{id}/rows/{n}/retry`; wizard step 3 plays the template video and marks the slot on the timeline.

## 2026-10-19 - F5
- BatchDetail (stats, failure reasons, inline preview, exports, pause/resume/cancel/delete with dialogs), Templates (cards, consent upload, new template form), History, Security; ConfirmDialog; `useBatchAction` now guards double submits and supports cancel.
- Open: AC5-P10 (test defect) and the DD-18 per-row retry tests (AC4-P6/P11/N2) are not wired yet.

## 2026-10-19 - F4
- New batch wizard (4 steps, draft resume, preview gate, idempotent start) in `src/pages/WizardPage.tsx` and `src/pages/wizard/*`.
- `test-support/node-fetch-types.ts` (Vitest setup): lets multipart uploads built from jsdom files reach MSW handlers (jsdom vs Node File/FormData mismatch).
- Open: TT-UI-AC5-P10 cannot pass (toHaveValue does not accept asymmetric matchers; test should use toHaveDisplayValue).

## 2026-10-19 - F3
- OverviewPage (KPI cards, Videos generated chart with hatched bars, current batch panel, polling, error/empty/loading), RowsTable, api/queries, api/types, format helpers. Typecheck is green again.
- Open: AC9-N4 and AC12-P1 need BatchDetailPage (F4).

## 2026-10-19 - F2
- App routing, api/client (CSRF, ApiError, 401 handler), LoginPage with 429 countdown, AppShell (sidebar, header, skip link, security banner), StatusChip, CountUp, Skeleton/ErrorState/EmptyState, useReducedMotion; other pages are placeholders.
- `tsconfig.tests.json` type-checks `tests/frontend` (typecheck script runs both). Fails only until RowsTable exists (F4).
- Open: AC9-N3/N4 and AC12-P1/P3 need the F3/F4 pages.

## 2026-10-19 - F1a round 3 (DD-15)
- Migrated to Tailwind 4.3.3 with @tailwindcss/vite; removed tailwindcss 3, postcss, autoprefixer, postcss and tailwind configs. Tokens moved to `@theme` in `src/index.css`. npm audit: 0 findings.

## 2026-10-19 - F1a
- Tooling scaffold in `frontend/`: Vite 8, React 19, TS 6 strict, Tailwind 3.4 (design tokens), Vitest 5, Playwright, ESLint 10, Prettier. Exact pinned versions.
- Placeholder `src/main.tsx` (no screens), logo copied, `frontend/.gitignore`.
- Tests added: none (tester next). Open: `@types/react`, `@types/react-dom`, `@types/node` are NOT approved but will be needed for TSX components; asked CEO.

## 2026-10-18 — SETUP
- Agent created.
