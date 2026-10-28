# Plan — CI on GitHub Actions (scope B)

**Status:** Approved by the Admin (scope B), 2026-10-28 · **ADR:** ADR-011 · **Branch:** `chore/ci-github-actions`

## Goal
Every push and pull request runs the same checks the CEO runs by hand before a merge, on a clean Linux machine.

## Acceptance criteria
1. **Python job:** Python 3.11 + `uv sync --locked`; `ruff check`, `ruff format --check` (on `backend` and `tests` only, NOT `backend/spikes`), `mypy`, `pytest -q` with Postgres 16 and Redis 7 as job services.
2. **Frontend job:** Node LTS + `npm ci`; `tsc --noEmit`, `eslint`, `prettier --check`, `vitest run`, `npm audit --omit=dev` (high level and up).
3. **E2E job (after the two above):** Playwright with browsers installed, against the app started the same way the e2e tests expect, using the synthetic fixtures only.
4. Linux system packages for the pipeline are installed in the job: `ffmpeg`, `libraqm0`, `libfribidi0` (ADR-001), plus a Devanagari font if the label tests need one.
5. No secrets: throwaway service passwords, random app secrets generated in the job. `permissions: contents: read`. Actions pinned to exact versions. `concurrency` cancels superseded runs. Timeouts on every job.
6. The workflow passes on this branch (green run on GitHub) before the merge, and a README badge/section explains how to read it.
7. Nothing is deployed, and no deploy step exists.

## Test case outline
- Positive: a clean push is green, caches work, and the job reports test counts.
- Negative: a deliberately failing test or a lint error makes the workflow red (verified once on a throwaway commit, then reverted).
- Edge: the first run with a cold cache, a fork or external PR (no secrets exist, so nothing leaks), a Postgres service that is slow to start (health check/wait), and a missing system library fails with a clear message.

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| CI-1 | Write `.github/workflows/ci.yml` (+ README note) to the criteria above; run each command locally first; push the branch and report the GitHub run result | backend-dev | Knows the Python/uv/test setup; only agent that touches repo tooling (ADR-011) | — | sonnet | no (single task) | Green GitHub run; no secrets; pinned actions |
| CI-2 | CEO review: diff, security (permissions, pins, no secrets), run result | CEO | Review gate | CI-1 | — | — | Reviewed |
| CI-3 | Admin switches on branch protection for `main` (steps provided) | Admin | GitHub account setting | CI-2 merged | — | — | Admin done |

## Risks
| # | Risk | Mitigation |
|---|------|------------|
| R1 | Linux differs from macOS (libraqm, fonts, ffmpeg build) | Install the packages explicitly; failing label tests are reported rather than skipped |
| R2 | E2E needs services started in a specific way | Reuse `scripts/dev_up.sh` logic or the e2e conftest; no new app code |
| R3 | A runaway workflow burns free minutes | Timeouts, concurrency cancel, path filters not needed yet |
| R4 | Supply chain through third-party actions | Only first-party + astral-sh/setup-uv, exact versions |
| R5 | CI running code on GitHub's servers | Repo is private; synthetic data only; no secrets |

## Dependencies / migrations
None to the project. No migration.
