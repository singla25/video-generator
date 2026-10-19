# ADR-009 — Frontend stack: React + TypeScript + Vite + Tailwind, self-hosted fonts

## Status
Accepted (Admin, 2026-10-19)

## Context
M3 builds the operator dashboard (REQ-001 §10). It must match the TrustVest reference (`docs/design/reference/trustvest-dashboard.png`, `DESIGN-NOTES.md`): light cards, hatched stepped charts, status chips, count-up motion. It talks to the FastAPI backend with a signed SameSite=strict session cookie + CSRF header (ADR-006), shows Hindi names, and must not leak operator or voter data to third parties (C5).

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **React + TypeScript + Vite + Tailwind CSS** | Huge ecosystem; Tailwind maps 1:1 to design tokens; fast; static build served same-origin with the API | Node toolchain | Low–medium | Yes (static assets, CDN-able) |
| Next.js | Routing + SSR built in | A second server we don't need | Medium | Yes |
| Streamlit | Fastest, Python only | Cannot match the design or the motion | Low | Limited |

Charts: **Recharts** (SVG; hatch patterns via `<pattern>`; built-in animation) over ECharts (heavier, less card-native).
Fonts: **self-hosted** via `@fontsource/*` npm packages over the Google Fonts CDN (which would make every browser contact Google on each visit).

## Decision
- **React 18 + TypeScript (strict) + Vite + Tailwind CSS**, single-page app in `frontend/`.
- **Recharts** for charts, **Lucide** icons (1.5 px outline).
- Fonts: **Plus Jakarta Sans** (UI) + **Noto Sans Devanagari** (Hindi), self-hosted via `@fontsource`.
- Data fetching: **TanStack Query** (polling every 2 s for live progress, R7.2), routing: **React Router**.
- Same origin as the API (Vite dev proxy in dev; static files served behind the same host in prod), so the SameSite=strict cookie works and no CORS is needed.
- Tests: **Vitest + Testing Library** (components) and **Playwright** (end-to-end, reduced motion, tablet width). Test code lives in `tests/frontend/` (tester's domain), run with configs in `frontend/`.
- Design tokens (colours, radii, spacing, shadows) are defined once in the Tailwind config from `DESIGN-NOTES.md` §1.

## Consequences
- New system tool: Node.js LTS (Admin installs). New npm dependencies need Admin approval (listed in `docs/plans/m3-dashboard.md`).
- The TrustVest screenshot is a **reference only**: its name, logo, illustrations and the designer's photo are never copied into `frontend/` or shipped.
- Reduced-motion users get no count-up or grow-in animations.
