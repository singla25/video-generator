# Optimization round 1: dead and duplicated code (static only)

Date: 2026-11-22. Commit analysed: `633e203` (local HEAD; the local `origin/main` ref was one commit behind, `826d892`).
Method: static only. Nothing was run except linters and a text search. No tests, no AI models, no Docker. No code was changed.
Tools: `ruff 0.16.9` (repo config plus `--isolated` runs with extra rules), `vulture` via `uv run --no-project --with vulture` (an ephemeral run, not a project dependency), `git grep`, `wc`, and a small 8-line-window duplicate finder (script kept in the session scratchpad, not in the repo).

## Size of the project (measured)

| Part | Files | Lines |
|------|-------|-------|
| `backend/vidgen` (app code) | 150 py | 27,648 |
| `frontend/src` | 89 files in `frontend/` | 5,829 |
| `tests` (py, ts, tsx) | 298 | 43,677 |

Tests are about 1.6 times the size of the backend code. That is expected for a TDD project, not a finding by itself.

## Summary table

| # | Finding | Evidence | Gain | Risk | Proposed fix | Needs Admin approval |
|---|---------|----------|------|------|--------------|----------------------|
| 1 | `BatchRepository` is dead in production. The app uses `SqlBatchStore` and `SqlRowStore`. Only test fixtures still use it. | `backend/vidgen/infrastructure/db/repositories.py:177` (about 78 lines, with `add_rows`, `find_by_voter_id`, `delete_batch`). Zero references in `backend/` other than its definition. 30 references in `tests/` (for example `tests/integration/worker/world.py`, `tests/integration/db/test_repositories.py`). | Measured: about 78 lines of code that is not used at runtime. Two code paths that can drift apart. Speed gain: none. | Medium. Tests must move to the real stores first. | Move the tests to `SqlBatchStore` / `SqlRowStore`, then remove the class. One small PR. | Yes (tests change and code is deleted) |
| 2 | Six domain and infrastructure functions are only called by their own tests. | `domain/slot_match.py:47` `select_target_word`, `:90` `ensure_within_slot`; `domain/timing.py:113` `duration_within_tolerance`, `:121` `expected_frame_count`; `domain/validation.py:148` `validate_rows`; `domain/status.py:105,110` `status_after_cancel`, `status_after_retry_failed`; `domain/codes.py:94` `is_retryable`; `infrastructure/local_ai/name_slot.py:30` `detect_name_slot`; `infrastructure/local_ai/factory.py:101,115` `describe_mode`, `local_label_band_height`; `infrastructure/storage/local.py:73` `remove_stale_temp`. Each has 0 references in `backend/` and 3 to 16 in `tests/`. | Measured: 14 symbols, about 3 to 16 tests each. Some may be planned features (for example `validate_rows`, the streaming validator, and `remove_stale_temp`). | Low to medium. Could be planned, not dead. | The CEO decides per symbol: wire it up, keep it with a comment, or delete it with its tests. | Yes |
| 3 | Three names have no references anywhere. | `domain/name_sounds.py:69` `DEVANAGARI_MATRAS`; `infrastructure/local_ai/fidelity.py:25` `TEXTURE_TARGET`; `api/security.py:25` field `Session.issued_at` (set and never read; I did not check that it is never set). | 3 lines. | Very low. | Delete the two constants. Leave `issued_at` until the session code is reviewed in the security round. | Yes (deleting code) |
| 4 | `docs/patches/` holds 3 old patch files. One is already applied, one no longer applies, one still applies cleanly. | `docs/patches/readme-local-mode.patch` reverses cleanly, so it is already in the tree. `local-ai-deps.patch` does not apply. `readme-performance-demo-run.patch` applies cleanly (so the README does not have it yet). | Tidy-up only. | Low. | Ask the CEO whether the third patch is still wanted. Remove the other two. | Yes (deleting files) |
| 5 | `backend/spikes/m2_mac/` (11 files, about 1,400 lines) and `backend/scripts/musetalk_mac.patch` duplicate each other in part. | `backend/spikes/m2_mac/musetalk_mac.patch` and `backend/scripts/musetalk_mac.patch` are byte-identical (`cmp`, 93 lines each). The two largest spike files are over the 300-line rule: `make_marketing_template.py` 595, `s6_real.py` 310. `backend/scripts/local_ai_smoke.py` 429 and `scripts/setup.py` 401 are over it too. | About 93 duplicate lines. The long-file count is 4, all outside the app package. | Low. Spikes are history; `RESULTS.md` is referenced in 5 places. | Keep `RESULTS.md`. Archive or delete the `s*.py` spikes. At minimum remove the duplicate patch. Split `scripts/setup.py` and `local_ai_smoke.py` if they keep growing. | Yes |
| 6 | `main.py` is a 6-line placeholder that prints "video-generator ready". `requirements.txt` is empty (0 lines). | `main.py:1-6`; `requirements.txt` is a zero-byte file. Neither is referenced by Docker, CI or scripts. Only `pyproject.toml:63` excludes `main.py` from ruff. The project uses `pyproject.toml` and `uv.lock`. | Removes two confusing files. | Low. | Delete both and the ruff exclude. | Yes (deleting files) |
| 7 | Lint is not clean on the current tree. | `ruff check backend tests` reports 3 errors, all `I001` (unsorted imports) at `backend/vidgen/infrastructure/local_ai/loaders.py:50, 86, 146`. All 3 are auto-fixable. | CI lint would flag these, if CI runs ruff on that path. | Very low. | `ruff check --fix` on that one file, one tiny PR with no behaviour change. | No (small fix, no deletion) |
| 8 | Duplicated code is very low in the backend. One small duplicate in the frontend. | 8-line window search: 0 duplicated windows in `backend/vidgen`, 0 in spikes and scripts, 3 windows in the frontend: the confirm-dialog block in `frontend/src/components/CurrentBatchPanel.tsx:119` and `frontend/src/pages/batch/BatchActions.tsx:100`. | Small. | Low. | Optional: extract one shared cancel-confirm component. | No |
| 9 | Function complexity is good. | `ruff C901` at the default limit of 10: 0 findings in `backend/`. At limit 7 only 2 functions: `domain/name_match.py:63` `_sound_of` (8) and `domain/providers.py:92` `__post_init__` (9). | Nothing to gain. | None. | None. | No |
| 10 | Dependencies in `pyproject.toml` and `frontend/package.json`: no clearly unused ones. | Every one of the 15 Python runtime dependencies is imported somewhere, or is used indirectly: `psycopg` is the SQLAlchemy driver, `uvicorn` is the server command, `python-multipart` is used by FastAPI forms. Frontend: every runtime dependency is imported in `src/`. `@vitest/coverage-v8` is used by the `test:coverage` script and `@types/node` by the TypeScript config. `recharts` is imported by only 1 file in `src/`, so it is a heavy library for one chart (check in the dashboard round). | Nothing to remove. | None. | Report only. | n/a |

## Raw numbers

- vulture (confidence 60 and up) on `backend/vidgen` and `backend/modal_app`: 95 raw hits. After sorting by hand: about 28 are FastAPI route handlers, 7 are `_satisfies_port` type-check helpers, about 10 are settings and Pydantic fields or validators, 17 are Protocol and adapter arguments. These are false positives. The real signal is findings 1 to 3 above.
- `ruff ARG002` (unused method argument): 17 hits, all in fake adapters and the Modal lip-sync stub, which must match a Protocol signature. Not a problem.
- Files over 300 lines in app code (`backend/vidgen`, `frontend/src`): 0. The biggest frontend file is `RowsTable.tsx` at 264. Over 300 outside app code: 4 files (finding 5). Test files over 300 lines: 27 (largest `tests/frontend/unit/wizard.test.tsx` at 607). The project rule is about code, so this is only a note.
- `print(` in app code: 0. Bare `except:`: 0. One broad `except Exception` with `logger.exception` at `backend/vidgen/worker/periodic.py:39`, which is correct for a periodic loop. `TODO/FIXME`: 1. `# noqa` and `# type: ignore` in `backend/vidgen`: 42.
- Skipped tests: every skip I found is conditional and has a clear reason (no Docker, no `E2E_BASE_URL`, running as root, one project of a browser matrix, `RUN_LOCAL_AI=1` for real-model smoke tests). No unconditional `skip` or `xfail`, so no obvious obsolete tests from that angle.
- `time.sleep` in tests: 9 places. Most are small (0.05 s to 0.5 s). `tests/e2e/test_docker_stack_e2e.py:133` sleeps 3 s in a polling loop. `tests/frontend/e2e/*.spec.ts` wait a fixed 1,800 ms for animations. For round 2.
- `docs/html/` is tracked in git (96 files, 1.2 MB), although CLAUDE.md calls it generated. It makes diffs noisy. Whether to keep it tracked is an Admin decision, not a finding I would act on alone.

## Not done, and why

- No frontend dead-export scan (`knip` or `ts-prune`): it needs an `npm install`, which is a network and disk job. Ask for "go" if wanted. A text search found no unused npm dependency.
- No `pip-audit` or `npm audit` (round 5).
- Obsolete tests were judged only by skips and by tests of the dead symbols above. A real check needs a coverage run (round 2, needs "go").
- I did not create `.worktrees/optimizer`. This cloud session is already on its own branch and I changed no code. I will create the worktree before the first code PR.

## Recommendation

Act first on finding 7 (3 import-order fixes, zero risk), then finding 1 (`BatchRepository`, the largest real dead-code item), then ask the CEO about the 14 symbols in finding 2. Next area: round 2 (test suite cleanup and speed), which starts with CI durations from GitHub and needs no heavy local run.
