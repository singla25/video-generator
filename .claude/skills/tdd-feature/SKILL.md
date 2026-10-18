---
name: tdd-feature
description: Step-by-step TDD cycle (Red → Green → Refactor → Verify) for building one feature of the Dynamic Video Generator across tester, backend-dev and frontend-dev. Use whenever the CEO turns an approved plan into delegated work, or a developer starts a task.
---

# TDD feature cycle

Use only after the Admin approved the plan (`docs/plans/<feature>.md`) and the task assignments.

## 1. Branch / worktree (CEO)
- Sequential work: one branch `feat/<feature-slug>`.
- Parallel work: one worktree per agent, branch `feat/<agent>/<feature-slug>`.

## 2. RED — tester
1. Write `docs/test-tree/<feature>.md` (use the `test-tree` skill).
2. Write failing tests in `tests/` — positive, negative and edge for each scenario.
3. Run `pytest -q` → tests fail **because the behaviour is missing**, not because of import typos.
4. Commit `test: <feature> failing tests`. Report to CEO.

## 3. GREEN — backend-dev / frontend-dev
1. Run the failing tests named in the brief.
2. Write the minimum code to pass them. Do not touch `tests/`.
3. `pytest -q` → green.

## 4. REFACTOR — same developer
1. Improve names, split long functions, remove duplication, add types and docstrings.
2. `pytest -q && ruff check . && ruff format --check . && mypy backend` → all pass.
3. Commit `feat(<area>): <what>`; append to own CHANGELOG. Report to CEO.

## 5. VERIFY — tester
1. `pytest -q --cov=backend --cov-report=term-missing`.
2. Add any missing edge cases; send defects to the CEO (never fix app code).
3. Update `docs/agents/tester/COVERAGE.md`.

## 6. REVIEW & MERGE — CEO
1. Review diff: domain boundaries respected, no tests edited by developers, no secrets, no deleted code.
2. Report to Admin with acceptance criteria ✅/❌ and test counts.
3. Merge **only after Admin says "Merge"**: `git merge --no-ff`, re-run full suite on `main`.
4. `python scripts/build_docs.py`.

## Done means
- Every acceptance criterion has at least one passing test.
- Positive, negative and edge tests exist for every scenario.
- Coverage ≥ 85 % on new code (100 % on core pipeline).
- Lint, format and type checks pass. Docs updated (MD + HTML).
