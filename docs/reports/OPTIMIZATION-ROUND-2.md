# Optimization round 2: test suite and CI time, plus functional gaps from round 1

Date: 2026-11-22. Base `origin/main` 633e203. Read-only: this file is the only change.
Sources: GitHub Actions run 45035959027 (CI on main, run 73, all green), `.github/workflows/ci.yml`,
`tests/`, branch `perf/pytest-xdist`. Measured numbers come from step timestamps in that one run.
One run is one sample; runner noise is not known. Anything else is marked ESTIMATE.

## 1. Where the CI time goes (measured, one run)

Wall clock of the whole run: 15:01:19 to 15:12:26 = **667 s (11 min 7 s)**. The "7 minutes" is the
`python` job alone (440 s). The `e2e` job only starts after `python` ends, so the two add up.

| Job | Start to end | Duration | Share of 667 s wall |
|---|---|---|---|
| python (lint, types, pytest) | 15:01:22 to 15:08:42 | 440 s | 66 % |
| frontend (runs in parallel with python) | 15:01:22 to 15:03:15 | 113 s | 0 % (hidden behind python) |
| e2e (waits for python) | 15:08:44 to 15:12:25 | 221 s | 33 % |

Per step, `python` job:

| Step | Seconds |
|---|---|
| Set up job | 1 |
| Initialize containers (Postgres 16, Redis 7) | 23 |
| Checkout | 2 |
| Install uv and Python | 2 |
| apt-get install ffmpeg, fonts | 22 |
| uv sync | 2 |
| Secrets, ruff check, ruff format | about 0 each |
| mypy strict | 7 |
| **pytest** | **378 (86 % of the job)** |
| Teardown | 2 |

`e2e` job: containers 16 s, apt-get 17 s, uv sync 1 s, Node 2 s, `npm ci` 48 s, Playwright Chromium 15 s,
**end-to-end tests 115 s**. `frontend` job: `npm ci` 35 s, vitest 45 s, typecheck 6 s, eslint 4 s, rest under 10 s.

Measured: pytest is 378 s of 667 s wall (57 %). `apt-get` runs in both python and e2e (22 s + 17 s = 39 s). `npm ci` runs in both frontend and e2e (35 s + 48 s).

## 2. Test suite facts (static)

- 2,197 `test_` functions in 249 files (about 3,990 collected cases, so parametrization adds the rest).
- By folder (functions): tests/unit 1,223; tests/integration 970, of which api 550, worker 177, db 88, ffmpeg 67, ingest 61, storage 26.
- `time.sleep` in tests: 7 calls. Real waits: `tests/unit/ai_local/test_musetalk_support.py:156` (a child process sleeps 5 s, probably a timeout test), `tests/e2e/test_docker_stack_e2e.py:133` (3 s poll), `tests/integration/worker/test_worker.py:282` (0.5 s), `tests/frontend/e2e/run_stack.py:55` (0.5 s poll). Together under 10 s: sleeps are not the problem.
- The CI does not print per-test durations (`pytest -q` with no `--durations`), so **which tests are slow is not measured**. I will not name slow files; the folder counts above are a ESTIMATE of where the weight is (integration tests use Postgres, FFmpeg and per-test table clean-up and are likely the bulk).
- Postgres log in the run (service container) shows one checkpoint that took 121 s to write 2,537 buffers across 36,358 synced files. That many files suggests heavy create/drop of tables or databases (tests/integration/conftest.py makes a models database and a migrations database per session and cleans tables before every test). It is a hint, not proof.
- Shared state for parallel runs: Postgres (per-session random database names, already unique), Redis (no integration test connects to a real Redis; they use doubles `tests/fixtures/redis_double.py`), ports (only `tests/frontend/e2e` and `tests/e2e`, which are not in the main pytest job), storage (temp dirs). Risk of cross-worker clashes looks low.

## 3. Existing xdist work

Branch `perf/pytest-xdist` exists (2 commits, no open PR): per-worker database names in `tests/integration/conftest.py`, a guard test `tests/unit/meta/test_xdist_isolation.py` (321 lines), small marker edits in 12 test files, docs. It does not change `pyproject.toml`, `uv.lock` or `ci.yml`, so adding the `pytest-xdist` dependency and the `-n` flag are still not proposed anywhere. I did not touch that branch and I do not duplicate it.

## 4. Findings

| Finding | Evidence | Measured or estimated gain | Risk | Proposed fix | Needs Admin approval |
|---|---|---|---|---|---|
| pytest is 57 % of wall time | step times above, run 45035959027 | 378 s measured | None | Finish the xdist branch (open its PR, add the dependency and `-n auto`). | Yes (dependency, CI) |
| Parallel pytest speed-up | no run exists | ESTIMATE: 378 s down to about 130-200 s if the runner has 4 CPUs. Method: 378 / 4 = 95 s at perfect scaling, plus a fixed cost per worker for the DB schema and slower Postgres sharing; the runner CPU count is not confirmed. Needs one measured trial run. | Medium (DB contention, flaky ordering) | Trial run on the xdist branch, compare to 378 s. | Yes |
| Serial `e2e` job after `python` | `needs` in `ci.yml` e2e job; e2e started 15:08:44 only after python ended 15:08:42 | Up to 221 s of wall time if e2e ran in parallel. Measured step times; actual gain depends on the reason for the dependency. | Low to medium (the reason for `needs` is not documented in the file) | Ask why e2e must wait; if only to save runner minutes, drop `needs`. | Yes (CI) |
| No per-test timing in CI | `ci.yml` pytest step has no `--durations` | Makes later tuning measurable | None | Add `--durations=25` to the pytest step. | Yes (CI) |
| Duplicate installs across jobs | apt-get 22 s + 17 s; npm ci 35 s + 48 s | At most about 40 s of wall time if shared or cached; ESTIMATE, because caching restores take time too | Low | Cache the apt packages, or put the e2e job in the frontend job. | Yes (CI) |
| Slow-test sleeps | 7 sleeps, under 10 s total | negligible | None | Leave. | No |
| Duplicated tests | AST scan: 0 identical test bodies in 2,197 functions | none | None | None. | No |

## 5. Functional gaps from round 1 (CEO request)

Round 1 listed symbols with no production caller. Compared with the plans, several are not dead code: they are checks the plan asks for that the pipeline does not run.

| # | Gap | Evidence (file:line) | Plan reference | Does the pipeline enforce it now? |
|---|---|---|---|---|
| G1 (highest) | **No output quality check runs in the real worker.** The worker always builds `FakeQualityChecker()`, which "accepts every output", also in `local` and `modal` AI modes. `OUTPUT_CHECK_FAILED` can never be raised in production. | `backend/vidgen/worker/runner.py:122`; fake: `backend/vidgen/infrastructure/fakes/adapters.py:79-84`; call site `backend/vidgen/services/render_row.py:266-267` | m1-batch-pipeline.md AC8 (line 17: duration = template + name delta within 50 ms, same resolution, fps, codec, audio format) and AC9 (line 18: slot loudness within 1 LU); m2-real-ai.md line 18 and 25-26 (Q1-Q6; task G5 "Planned") | No. A row with the wrong length, format or loudness still succeeds. |
| G2 | The helpers meant for AC8 exist but are unused: `duration_within_tolerance` and `expected_frame_count` | `backend/vidgen/domain/timing.py:113,121` | AC8, AC9 | Not called anywhere. |
| G3 | Settings for those tolerances are never read: `duration_tolerance_ms` (default 50) and `loudness_tolerance_lu` (default 1.0) | `backend/vidgen/settings.py:60-61` | AC8 (50 ms), AC9 (1 LU) | Not read by any code. An operator who changes them gets no effect. |
| G4 | Stale temp cleanup never runs: `remove_stale_temp` deletes `.tmp-*` files left by crashed writes, but nothing calls it (worker `periodic.py` is not given it) | `backend/vidgen/infrastructure/storage/local.py:73`; no caller in `backend/vidgen/worker/` or `services/storage_cleanup.py` | I found no plan line that names it (grep of docs/plans, docs/requirements, docs/decisions); it follows from the atomic-write design | No. Crash leftovers accumulate until someone deletes them (disk-full risk over time). |
| G5 | Output loudness measurement exists (`loudness.py` gain from ebur128) and is applied when mixing, but the result is not verified afterwards | `backend/vidgen/infrastructure/ffmpeg/loudness.py:21-25` | AC9 | Gain is applied; the 1 LU outcome is not checked (see G1). |
| G6 | Safe to treat as dead (superseded): `is_retryable` (the live logic is `domain/retry.py:25`, `_RETRYABLE_KINDS`), `status_after_cancel` and `status_after_retry_failed` (the services do bulk row updates in `services/batch_flow.py:227-263`), `validate_rows` (rows are validated by `RowValidator.validate` one at a time) | `domain/codes.py:94`, `domain/status.py:105,110`, `domain/validation.py:148` | B8 retry policy (m1 plan line 157) is implemented in `retry.py` | These are the tested-only duplicates; the behaviour exists elsewhere. |
| G7 | Port methods `TextDetector.detect` / `render_text` and the constants `DEVANAGARI_MATRAS`, `TEXTURE_TARGET`, `HEARTBEAT_INTERVAL_SECONDS` | round 1 findings 4, 5 | Not found in the plans for `render_text`; others unverified | Not enforced; unclear if wanted. |

Reading: G1, G2, G3 are one unfinished feature (the output check, plan item G5 of m2-real-ai). It is the biggest finding of rounds 1-2 because it is a quality and safety check that looks done (a code path, a failure code, a setting) but is switched off.

## What I changed

Only this report on branch `optimizer/report-round-2`. No code, dependency or CI file.

## What I recommend next

1. Admin decision on G1-G3: build the real output check (AC8/AC9) or accept that M1 outputs are unchecked. Do not delete the helpers or the settings until that is decided.
2. Open a PR for the `perf/pytest-xdist` branch and measure one parallel CI run against the 378 s baseline.
3. Next round (as ordered by the CEO): round 4, security.
