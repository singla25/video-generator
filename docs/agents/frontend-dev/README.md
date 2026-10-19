# Frontend developer (`frontend-dev`)

## Role
Builds the user interface that talks to the backend API, handling loading, error and empty states.

## Writes only in
`frontend/`

## Definition
`.claude/agents/frontend-dev.md`

## Current status
F1a tooling scaffold done (no screens yet).

## Known advisories
`npm audit` reports 7 findings (5 high, 2 moderate), all dev-only and never shipped. All come from one chain under `tailwindcss` 3.4.19: tailwindcss -> fast-glob -> micromatch -> braces (high), and tailwindcss -> postcss-nested -> postcss-selector-parser (moderate). Non-breaking `npm audit fix` changed nothing; the only fix is Tailwind 4 (major bump, needs a new approval).

## npm scripts (run in `frontend/`)
- `dev` - Vite dev server; proxies the API paths (auth, templates, batches, stats, audit, health) to 127.0.0.1:8000, so the app is same-origin
- `build` - typecheck + production build into `dist`
- `typecheck` - `tsc --noEmit` (strict)
- `lint` / `format:check` - ESLint (flat config) / Prettier
- `test` / `test:coverage` - Vitest (jsdom); reads `tests/frontend/unit`, setup file `tests/frontend/setup.ts`
- `e2e` - Playwright (`tests/frontend/e2e`; projects desktop, reduced-motion, tablet; env `E2E_BASE_URL`, `E2E_START_SERVER`)
