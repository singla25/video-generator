# Optimization baseline (before any optimizer code change)

Date: 2026-11-22. Commit measured: `origin/main` 8bde7c8 (xdist merged in #41, reports #40, #42, #43, #44 merged).
Local machine: cloud container, 4 CPUs, 16 GB RAM, Postgres 16 and Redis 7 started locally, real FFmpeg 6.1.1, Python 3.11,
locked dependencies (`uv sync --locked`, ruff 0.17.1). One run per number unless noted, so expect noise of a few seconds.
CI numbers come from the GitHub Actions step timestamps. "Estimate" is written wherever a number is not a measurement.

## 1. Tests, local (same commit family, same machine)

| Run | Result | Wall time |
|---|---|---|
| Serial `pytest` (before xdist, commit 633e203) | 4,083 passed, 5 skipped, 1 failed* | **319 s** |
| Parallel `-n auto --dist loadgroup` (4 workers, commit 8bde7c8) | 4,083 passed, 5 skipped, 1 failed* | **99 s** |
| Parallel with coverage (`--cov=vidgen`) | same | 118 s (coverage costs about 19 s) |

\* `tests/unit/meta/test_native_worker.py::test_native_worker_refuses_unreadable_env_file` fails here because the container runs as root, so a permission-denied check cannot work. It also fails on a clean `main`; it passes in CI.

Slowest tests (parallel run, call time): 100k-row xlsx scale test 20.8 s; seven tests that waited the real 10 s retry delay (6 in `tests/integration/worker/test_worker.py`, 1 in `tests/e2e/test_synthetic_batch_e2e.py` at 11.9 s); four more between 3 and 5 s (full-size 1080x1300 FFmpeg render, bubble overlay, e2e batch).
Retry-delay waiting alone is about 72 s of the 319 s serial run (sum of the reported durations).

## 2. CI (GitHub Actions, run 45062805640 on `main` after xdist)

| Job | Duration | Biggest steps |
|---|---|---|
| python | 250 s | pytest 181 s, apt-get 28 s, containers 19 s, mypy 8 s |
| frontend | 134 s | vitest 64 s, npm ci 48 s, typecheck 9 s |
| e2e (waits for python and frontend) | 201 s | e2e tests 95 s, npm ci 33 s, apt-get 31 s, Playwright browser 12 s |
| **Whole run (wall)** | **455 s** | |

Before xdist (run 45035959027): pytest 378 s, python job 440 s, whole run 667 s. xdist already saved 212 s (32 %) of wall time in CI.
The e2e job runs after the others (`needs: [python, frontend]`), so about 201 s of the 455 s is serial.
CI prints no per-test durations (no `--durations`).

## 3. Static tools (local)

| Tool | Time | Result |
|---|---|---|
| ruff check + format check (`backend`, `tests`) | about 0.05 s each (cache warm) | clean |
| mypy --strict `backend/vidgen` | 5.0 s | clean |
| `import vidgen.api.app` | 600 to 760 ms (3 runs) | n/a |

## 4. Coverage (parallel run, branch coverage, `vidgen` package)

Total **97 %** (6,978 statements, 190 missed; 972 branches, 46 partly missed), 150 modules.
Lowest modules (the project target is 100 % on the core video pipeline and 85 % elsewhere):

| Module | Coverage | Note |
|---|---|---|
| `infrastructure/local_ai/compositing.py` | 30 % | real-model path, needs the local-ai extra |
| `infrastructure/local_ai/fidelity.py` | 47 % | real-model path; also has the unused `TEXTURE_TARGET` |
| `infrastructure/local_ai/offline.py` | 84 % | |
| `api/login_tolerance.py` | 86 % | |
| `infrastructure/local_ai/loaders.py` | 86 % | model loaders |
| `infrastructure/consent.py` | 89 % | |
| `api/container.py` | 90 % | |

The core pipeline modules (`services/render_row.py`, `domain/timing.py`, `infrastructure/ffmpeg/*`) are at or near 100 % by this run, but the coverage figure cannot see that `worker/runner.py:122` always builds `FakeQualityChecker` (see OPTIMIZATION-ROUND-2, gap G1): code that exists and is covered is not code that runs in production.

## 5. Repository size

810 tracked files, 9.5 MB of tracked content, `.git` 6.7 MB (pack 4.9 MiB). Small; size is not a problem.

## 6. What the next steps will be measured against

- Local parallel suite: 99 s (80 s measured with the retry-delay fix, PR #48).
- CI whole run: 455 s; python job 250 s; e2e 201 s.
- Coverage 97 %; mypy 5 s; app import about 650 ms.
