# Frontend developer — Changelog

Newest first. One entry per task.

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
