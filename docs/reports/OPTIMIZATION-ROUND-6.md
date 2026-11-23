# Optimization round 6: the top 10, ranked by value over risk

Date: 2026-11-23. Base `origin/main` 2d0ef52. Built from rounds 1 to 5 (`OPTIMIZATION-ROUND-1/2/3/4/5.md`, `OPT-BASELINE.md`). Numbers are measurements unless marked ESTIMATE.

## Before and after (measured)

| What | Before | After | How |
|---|---|---|---|
| CI, whole run (GitHub Actions) | 667 s (11 min 7 s), run 45035959027 | **273 s (4 min 33 s)**, run 45067421638 | xdist (#41), `e2e` in parallel (#51), retry-delay tests (#48) |
| CI, `python` job | 440 s | 186 s | same |
| CI, pytest step | 378 s | 118 s | same, plus the 7 retry tests |
| CI, `e2e` job | 221 s (waited for the others) | 255 s, now the longest job and the critical path | it runs alongside the rest; its own steps grew by about 30 s from runner noise and more tests |
| Local full suite, 4 CPUs | 319 s serial, 99 s parallel | 80 s parallel (retry-delay fix) | #41, #48 |
| Known CVEs in locked runtime dependencies | 1 | 0 | #47 |
| Output quality check in the real worker | none (`FakeQualityChecker` always) | real checks in `local` and `modal` mode | #49 (written by the Developer session; I reviewed it) |

One sample per CI number; runner time varies by some seconds.

## The top 10

| Rank | Improvement | Evidence | Gain | Risk | Status | Needs Admin approval |
|---|---|---|---|---|---|---|
| 1 | **Output quality check live (BL-14)**: a bad video (wrong length, format or loudness) now fails its row instead of being delivered | `worker/runner.py:122` was the fake; round 2 gaps G1 to G3 | Customer-visible: fewer bad videos in the delivered folder | Medium: false failures on real models are unmeasured (short-window loudness, variable frame rate) | Merged (#49). **Open: run 10 to 20 real rows on the Mac and count false `OUTPUT_CHECK_FAILED`** | Yes, for the real-model run |
| 2 | **Guard hook hardening**: 33 command variants the current guard allows (forced pushes, `.env.*`, shell writes to `CLAUDE.md`/`.claude/`) | `docs/patches/guard.hardened.py`, 122 tests, PR #52 | Closes the hole in the safety net of every agent session | Low to medium: a stricter guard may block an unusual normal command; 50 ordinary commands plus 18 from real sessions pass | Open (#52), Admin applies | Yes (`.claude/` is Admin-only) |
| 3 | **Stream the template instead of reading it whole** (`template.write_bytes(source.read())`) | `services/render_row.py:239`, round 3 finding 2 | Worker memory down by the template size per thread, up to 500 MB each; ESTIMATE of real saving needs a real template | Very low | Not started | No for the line change, yes if a per-batch cache is added |
| 4 | **Faster CI, next step**: `e2e` is now the longest job (255 s): `npm ci` 49 s, apt 33 s, Playwright browser 17 s, tests 117 s | run 45067421638 | ESTIMATE: 40 to 60 s by caching the Playwright browser and apt packages; the whole run would be about 220 s | Low | Not started | Yes (CI) |
| 5 | **Lazy-load the chart**: entry JavaScript 211.6 kB gzip to 119.7 kB gzip (measured with a reverted experiment) | `OPTIMIZATION-ROUND-5.md` | 43 % less to download on the login page and every page except the Overview | Low (tests must wait for the lazy chart) | Not started | No (I ask because Overview tests change) |
| 6 | **Template analysis out of the web request** (speech-to-text inside an HTTP request and an open DB transaction) | `services/templates.py:160-270`, round 3 finding 1, ADR-014 (proposed) | The API process stops loading models; no long-held DB connection | Medium (dashboard polls instead of waiting) | Proposed | Yes (architecture) |
| 7 | **Two security decisions**: sessions cannot be revoked (cookie valid up to 480 min); login brake is off on an empty database | round 4 findings 3 and 4 | Smaller window for a stolen cookie; no unlimited guessing before the first migration | Low | Waiting for the Admin | Yes. Recommendation: (b) shorten the cookie life to about 120 min, and an in-memory counter for the empty-database case |
| 8 | **Dead and superseded code**, with evidence: `BatchRepository` (about 84 lines, tests only), `is_retryable`, `status_after_cancel`, `status_after_retry_failed`, `validate_rows`, two unused port methods, two dead constants | `OPTIMIZATION-ROUND-1.md` findings 1 to 5 and round 2 G6 | About 150 lines and one parallel code path less to maintain | Medium for `BatchRepository` (six test files use it) | Not started | Yes (deleting code and moving tests) |
| 9 | **Layering fixes** (`infrastructure` imports `services`; `api` imports DB and queue drivers; the worker imports the API's composition root) | `OPTIMIZATION-ROUND-3.md` findings 3 to 5 | Layering enforced by a test; worker image without the web stack | Medium (folder move) | Proposed in ADR-014 | Yes (structure) |
| 10 | **Slowest tests and coverage holes**: the 100k-row xlsx test (about 21 s) is now the longest test in the local suite; `local_ai/compositing.py` is at 30 % and `fidelity.py` at 47 % coverage (real-model code) | `OPT-BASELINE.md`, parallel run durations | Local suite floor about 25 s; real-model coverage needs the Mac | Low | Not started | No for the xlsx test (mark it `slow` or shrink it); yes for the real-model tests |

Also delivered and merged: #45 (ignore `*.sql`, `*.dump`, `*.pem`, `*.key`), #46 (nginx upload limit 520m so templates between 100 and 500 MB are not rejected, plus four security headers; the CSP still needs a look in a browser), #50 (baseline).

## Decisions I need from the Admin

1. Apply `docs/patches/guard.hardened.py` (PR #52)? It is the most valuable and has no cost beyond a review.
2. Session revocation: (a) leave and document, (b) cut the lifetime to about 120 minutes, (c) server-side session table (migration). Recommend (b).
3. Login brake on an empty database: (a) accept, (b) in-memory counter. Recommend (b).
4. Real-model check of the quality gate (rank 1): who runs 10 to 20 rows on the Mac, and should the loudness rule start as warn-only?
5. ADR-014 (rank 6 and 9): approve, change or reject; and whether a polling analyse flow is acceptable.
6. Deleting dead code (rank 8): approve the list, or tell me which items to keep.
7. CI path filters for docs-only changes (not done): is CI a required check on `main`?

## Limits of these rounds

No real AI model ran anywhere (the container has none), so everything about model-dependent behaviour is unmeasured. The local numbers come from one machine with 4 CPUs; the CI numbers are single runs. Static tools (vulture, a self-written duplicate scan, an AST import graph) give candidates, not proof; each deletion needs its own evidence and a green suite. Two harness refusals changed my method: `npx jscpd` (round 1) and `npx source-map-explorer` (round 5) were refused, so I used my own scripts instead.

## What I changed

Only this report, branch `optimizer/report-round-6`. Pull requests of this optimization work: #40, #42, #44, #45, #46, #47, #48, #50, #51 (merged); #52, #53, #54 (open).
