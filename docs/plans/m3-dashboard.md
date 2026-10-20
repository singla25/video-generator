# Plan — M3: Operator dashboard (F1–F6)

**Status:** Approved (Admin, 2026-10-19). Assignment waits for M1 gate 3 · **Date:** 2026-10-19
**Inputs:** REQ-001 §7 (R7), §10 · `docs/design/reference/DESIGN-NOTES.md` + `trustvest-dashboard.png` · ADR-006 (auth), ADR-009 (stack) · M1 API (T10–T14)
**Schedule:** starts after M1 **merge gate 3** (backend + tests verified, as the Admin asked). Can run in parallel with M2 backend work (worktrees, if the guard allows; otherwise interleaved).

## Goal
A TrustVest-style dashboard over the M1 API with these parts:
- an overview with live KPIs and charts
- a 4-step New batch wizard
- batch detail with the rows table
- templates with consent status
- history
- a security (audit) view

It has a clean design, correct Hindi text and accessible motion, and every screen handles loading, empty and error states.

## Acceptance criteria
1. **UI-AC1 Design fidelity:** colours, card style (1 px border, 12–14 px radius, near-zero shadow, 20–24 px padding), typography (Plus Jakarta Sans + Noto Sans Devanagari), chips, hatched stepped chart and spacing follow DESIGN-NOTES §1. Tokens are defined once in the Tailwind config. A visual review against the reference is signed off by the Admin.
2. **UI-AC2 Layout:**
   - The sidebar has MENU (Overview, Batches → Running/Completed/Failed, Templates, History, Security) and GENERAL (Settings, Help).
   - The header shows the page title, **+ New batch** and the avatar.
   - It is responsive down to tablet width (768 px).
3. **UI-AC3 Overview (R7.1, R7.2, R7.6):**
   - Six KPI cards (Total · Completed · Processing · Queued · Failed · Skipped) with status chips, plus a dashed **New batch** card.
   - A "Videos generated" hatched stepped chart (day/week) with the big total and a "+X % vs last" pill.
   - A Current batch panel: progress ring, ETA, counts, Pause/Resume/Retry failed, and the lime main action.
   - Live updates poll every 2 s, and the counts always add up.
4. **UI-AC4 Rows table (R7.4):**
   - Columns: Name (Devanagari OK), ID, status chip (Completed green · Processing blue · Queued grey · Failed red · Skipped amber), failure reason in plain words, render time, and actions (preview, download, retry).
   - Search by name or ID, filter by status, paged. It stays smooth with 1,000 rows (virtualised or paged).
5. **UI-AC5 New batch wizard (4 steps):**
   - Steps: upload (drag-and-drop video + sheet with preview) → map columns & validate (invalid rows highlighted with reasons) → mark slot & preview (video player, timeline with the detected slot, editable range, Generate preview, **approval required**) → output folder & start (default `YYYY-MM-DD-N` pre-filled, confirm screen).
   - It respects the preview gate (A5), the consent gate and the API's error codes.
6. **UI-AC6 Batch detail (R7.3, R7.7):**
   - Header stats, progress bar + ETA, a failure-reason chart (clicking a reason filters the rows), and an inline video preview.
   - Actions: Download ZIP, Export failures CSV, Pause/Resume/Cancel and Retry failed. Each confirms first where it can't be undone.
7. **UI-AC7 Templates:** cards show a thumbnail, the consent badge (✓ / missing), a slot summary, the original name and a usable state. Consent upload + confirmation flow.
8. **UI-AC8 History & Security (R7.5, C4, D-15):**
   - History: past batches with date, template, totals and success rate.
   - Security: the audit log with filters.
   - A **security alert banner** appears when a `SECURITY_LOGIN_THROTTLED` event exists.
9. **UI-AC9 Auth:**
   - A login screen. The session cookie is never read by JS; the CSRF token is sent as `X-CSRF-Token` on every state-changing call.
   - A 401 leads to login, and 429 shows "Too many attempts, try again in N s".
10. **UI-AC10 States & motion:**
    - Every screen has loading (skeletons), empty and error states (the API being down shows an error state, not stale numbers).
    - Count-up and grow-in animations are disabled under `prefers-reduced-motion`.
11. **UI-AC11 Hindi:** Devanagari names render correctly (shaping, no tofu) in the table, wizard and previews.
12. **UI-AC12 Privacy:**
    - No external network requests: fonts self-hosted, no CDNs, no analytics.
    - No voter data is stored in `localStorage` or `sessionStorage`.
    - The TrustVest name, logo and designer photo don't appear anywhere in `frontend/`.
13. **UI-AC13 Quality:**
    - TypeScript strict, ESLint + Prettier clean.
    - Component tests ≥ 85 % line coverage on `frontend/src`.
    - Playwright end-to-end on the main flows, plus axe accessibility checks with no serious violations.

## Test tree outline (tester expands into `docs/test-tree/m3-dashboard.md`)
```
Dashboard
├── Auth: login ok / wrong / 429 countdown / 401 → login / CSRF header on POST
├── Overview: KPIs add up · polling updates · API down → error state · empty (no batches) · reduced motion
├── Rows table: chips per status · Devanagari names · search · filter · 1,000 rows smooth · retry/download actions
├── Wizard: upload validation messages · mapping + invalid rows · slot edit + preview gate · folder default/custom/invalid
├── Batch detail: failure chart click-through · ZIP / CSV · pause/resume/cancel confirmations
├── Templates: consent missing → not usable · consent upload + confirm
├── History / Security: success rate · audit filters · throttle alert banner
└── Cross-cutting: tablet width · keyboard navigation · axe · no external requests · no PII in browser storage
```

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| F0 | Install Node.js LTS (`brew install node`); approve npm deps below | **Admin** | System install + approval gate | Plan approval | — | — | `node -v` works |
| F1 | Test tree + failing component tests (Vitest/Testing Library, MSW-mocked API) + Playwright skeleton | tester | TDD red; owns `tests/` | Gate 3, F0 | sonnet | if parallel with M2 | Tests fail only on missing components |
| F2 | App shell: Vite + TS + Tailwind tokens, fonts, sidebar, header, routing, auth (login, CSRF, 401/429), API client, loading/empty/error primitives | frontend-dev | Owns `frontend/` | F1 | sonnet | if parallel | F1 shell/auth tests green |
| F3 | Overview: KPI cards, hatched stepped chart, current-batch panel, live polling | frontend-dev | | F2 | sonnet | if parallel | UI-AC3 tests green |
| F4 | New batch wizard (4 steps) incl. video player + slot timeline + preview gate | frontend-dev | Largest screen; most API states | F2 | sonnet | if parallel | UI-AC5 tests green |
| F5 | Batch detail, rows table, Templates, History, Security + alert banner | frontend-dev | | F2 | sonnet | if parallel | UI-AC4, 6–8 tests green |
| F6 | Verify: full UI suite, Playwright E2E against the real API (docker compose), axe, tablet width, reduced motion, Devanagari, no external requests; coverage report | tester | Independent verification | F3–F5 | sonnet | — | All UI-ACs ✅ |
| F7 | Visual review against the reference; Admin sign-off for UI-AC1 | CEO → Admin | Fidelity is a human judgement | F6 | — | — | Admin approves the look |

Order (TDD): F0 → F1 → F2 → (F3, F4, F5 in sequence or parallel) → F6 → F7 → merge gate (Admin).

## Risks
| # | Risk | Mitigation |
|---|------|------------|
| R1 | M1 API changes after F1 | F1 starts only after gate 3; MSW mocks are generated from the FastAPI OpenAPI schema |
| R2 | Pixel-matching the reference becomes subjective | Tokens from DESIGN-NOTES; F7 Admin visual sign-off |
| R3 | Hatched chart / count-up hurt performance or accessibility | SVG patterns; reduced-motion respected; axe in CI |
| R4 | Copying third-party branding | UI-AC12 check: grep for "TrustVest", no reference assets in `frontend/` |
| R5 | The shared folder without worktrees slows parallel M2 + M3 work | Ask the Admin to allow `.claude/worktrees/**` in the guard, or interleave tasks |

## Dependencies (need separate Admin approval)
**System:** Node.js LTS (Homebrew). Package manager: npm (bundled; lockfile `frontend/package-lock.json`).

**npm runtime:**
| Package | Purpose | Licence |
|---|---|---|
| react, react-dom | UI | MIT |
| react-router-dom | Routing | MIT |
| @tanstack/react-query | Data fetching + polling | MIT |
| recharts | Charts | MIT |
| lucide-react | Icons | ISC |
| @fontsource/plus-jakarta-sans, @fontsource/noto-sans-devanagari | Self-hosted fonts | OFL-1.1 (fonts) / MIT (packaging) |
| clsx | Class names | MIT |

**npm dev:** @types/react, @types/react-dom, @types/node (added under delegated authority, DD-14), typescript, vite, @vitejs/plugin-react, tailwindcss 4 + @tailwindcss/vite (DD-15; replaces postcss + autoprefixer), vitest, @vitest/coverage-v8, @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jsdom, msw, @playwright/test, @axe-core/playwright, eslint (+ typescript-eslint, eslint-plugin-react-hooks), prettier. All MIT / Apache-2.0 / BSD.

**Open questions:** none blocking. The product name and logo for the sidebar are needed before F2: the Admin supplies them, or we use a plain text name.

## Admin approval
- [x] Plan approved — 2026-10-19
- [x] Node.js + npm dependencies approved as listed — 2026-10-19
- [ ] Product name / logo supplied by the Admin (before F2)
- [ ] Task assignment approved (after M1 gate 3)
- [ ] Visual sign-off (F7) and merge
