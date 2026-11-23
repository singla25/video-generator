# Optimization round 5: dashboard (static, read-only)

Date: 2026-11-23. Base `origin/main`. Only this file is added. The one source edit used for measuring (a lazy import) was reverted; `git status` is clean.
Measured here: `npm ci` 9 s, `npm run build` 5 s (Vite 8, one run each).

## Bundle (production build, measured)

| Item | Size |
|---|---|
| Entry JavaScript (one chunk) | **698.5 kB, 211.6 kB gzip** |
| CSS | 38.2 kB, 13.2 kB gzip |
| `dist/` total | 1.1 MB, 26 files (fonts are the rest) |
| Build warning | "Some chunks are larger than 500 kB after minification" |

What is inside the JavaScript (bytes attributed through the source map, so the shares are of the 695 kB it could attribute; method: read the map's `mappings`, no extra tool):

| Package | Size | Share |
|---|---|---|
| react-dom | 203.8 kB | 30.0 % |
| **recharts** | 190.3 kB | 28.0 % |
| app code | 92.3 kB | 13.6 % |
| react-router | 38.2 kB | 5.6 % |
| @tanstack/query-core | 31.9 kB | 4.7 % |
| d3-scale, decimal.js-light, @reduxjs/toolkit, immer, d3-time-format, es-toolkit, d3-color (all pulled in by recharts) | about 70 kB together | about 10 % |
| lucide-react, react | about 17 kB | about 2.5 % |

Recharts and the libraries only it needs are about 260 kB, roughly 37 % of the bundle, and are used by one component: `VideosChart` on the Overview page (`src/components/VideosChart.tsx`, imported only in `src/pages/OverviewPage.tsx:8`). Every page, including the login page, downloads it.

## Experiment (measured, then reverted)

Loading `VideosChart` with `React.lazy` and a `Suspense` around it (6 changed lines in `OverviewPage.tsx`):

| | Before | After |
|---|---|---|
| Entry JS | 698.5 kB (211.6 kB gzip) | **395.5 kB (119.7 kB gzip)**, 43 % smaller raw and 43 % smaller gzip |
| Chart chunk | inside the entry | 302.8 kB (90.8 kB gzip), loaded only when the Overview page shows a batch |

The chunk warning disappears (395 kB is under 500 kB). The login page and every page except the Overview now skip about 91 kB of gzip. The Overview page itself still loads the chart, so its total download is unchanged, but it renders its cards first and the chart after.

## Findings

| # | Finding | Evidence | Measured or estimated gain | Risk | Proposed fix | Needs Admin approval |
|---|---|---|---|---|---|---|
| 1 | One 698 kB entry chunk; the chart library is loaded on every page | build output; `OverviewPage.tsx:8` | Measured: entry 211.6 kB to 119.7 kB gzip on all pages except Overview | Low: a chart placeholder shows for a moment; the vitest tests for the Overview must wait for the lazy chart (`findBy...`) | Lazy-load `VideosChart` (PR proposal, tests first) | No (no dependency or structure change), but I ask because it touches the Overview tests |
| 2 | No route-level code splitting: all pages are in the entry | `src/App.tsx` (no `lazy`) | ESTIMATE: app code is 92 kB raw, so at most about 25 kB gzip more; not worth it now | Low | Skip until app code grows | No |
| 3 | Fonts: both `.woff` and `.woff2` of each weight are emitted (the browser downloads only one) | `dist/assets` | None for users; 26 files in `dist` | None | None | No |
| 4 | Dead components: none. All 73 source files are imported by another file (round 1 import analysis) | round 1 | n/a | n/a | n/a | No |

## Accessibility (static scan, no regressions found)

- 0 `<img>` without `alt`; 0 click handlers on `div`, `span`, `tr`, `td` or `li`; `<html lang="en">` is set.
- 55 `<button>` elements; every form control I checked has a label, an `aria-label` or an `id` tied to a label (6 controls inspected: search box, status select, preview field, data-class radio and checkbox, template select).
- 25 live regions (`aria-live`, `role="alert"`, `role="status"`); no positive `tabIndex`; no `outline-none` that would hide focus.
- The Playwright suite runs axe on every route (`tests/frontend/e2e/dashboard.spec.ts:122`, "no serious or critical violations"), and CI runs it (the e2e job). Colour contrast is covered only by axe there; I did not run a browser in this round.

Not checked here (needs a running app or data): the stale numbers on the Overview (BL-10) and the per-row download (BL-9), and keyboard flow through the wizard.

## What I changed

Only this report, branch `optimizer/report-round-5`.

## What I recommend next

1. Approve the lazy chart PR (measured: entry JS 211.6 kB to 119.7 kB gzip). I will write the failing Overview test first.
2. Round 6: the ranked top 10.
