# ADR-011 — Continuous integration on GitHub Actions (CI now, CD later)

**Status:** Accepted (Admin chose scope B, 2026-10-28) · **Deciders:** Admin, CEO

## Context
The repository is now on GitHub (private, `singla25/video-generator`). Until now "main is always green" has depended on the CEO running the suite by hand. About 650 tests need Postgres/Redis, and local runs have failed when Docker was off. There is no deployment target yet (no server, GPU for M2 undecided).

## Options
| Option | Pros | Cons | Cost / complexity | Scales? |
|---|---|---|---|---|
| A. Fast CI (unit, dashboard, lint, types) | Quick, simple | Skips DB integration tests, where most real bugs showed up | Free / small | Yes |
| **B. Full CI (A + Postgres/Redis integration + Playwright)** | Same checks as the CEO's gate; blocks bad merges | ~10 min per run; Linux needs ffmpeg + libraqm | Free (private-repo free minutes, $0 spending limit) / medium | Yes |
| C. CI + CD | Auto-deploy | No deploy target; needs a paid server; would be rebuilt for M2 | Paid / large | Premature |

## Decision
Option **B**. CD is deferred until there is a deployment target (after W-1, the GPU decision).

## Consequences
- New folder `.github/workflows/` (folder-structure change, recorded here). Owner for this task: backend-dev; afterwards the CEO routes changes to the right agent.
- Workflows use **no secrets**: Postgres and Redis run as job services with throwaway passwords, and the app's own secrets are generated randomly inside the job. Real `.env` values are never needed in CI.
- Only first-party `actions/*` plus `astral-sh/setup-uv`, pinned to exact versions. Workflow permissions are `contents: read`.
- No voter data: `samples/` is git-ignored, so CI runs only on synthetic fixtures.
- Branch protection on `main` (require the CI check to pass) is a GitHub account setting that the **Admin** switches on.
- If the free minutes run out, runs stop (the spending limit stays at $0). No paid service is involved.
