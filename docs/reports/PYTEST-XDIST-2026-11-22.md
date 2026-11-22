# Backend test suite with pytest-xdist (2026-11-22)

Branch `perf/pytest-xdist` (fresh from `origin/main`). Measured on the Admin's Mac (12 CPUs), dev stack stopped, nothing else
running, the exact CI command plus xdist options. No `vidgen` or `vidgen_demo` database was touched.

## Results (4087 tests = 4054 on main + 33 new isolation checks; 2 skipped in every run)
| Configuration | Time | Speed-up vs serial (206 s) | Peak test memory | Counts |
|---|---|---|---|---|
| serial (CI command) | 206-214 s | 1.0x | 0.45 GB | 4087 passed, 2 skipped |
| `-n 2 --dist loadgroup` | 110 s | 1.9x | 0.9 GB | same |
| `-n 4 --dist loadgroup` | 61-65 s | 3.3x | 1.2-1.4 GB | same |
| `-n 4 --dist load` / `loadscope` | 86 s / 80 s | 2.5x / 2.7x | 1.2 GB | same |
| `-n 8 --dist loadgroup` | 47 s | 4.4x | 2.2 GB | same |
| **`-n auto --dist loadgroup`** (12 workers), 6 runs | **35, 35, 35, 37, 45, 45 s** | **5-6x** | 2.9-3.3 GB | same, 6 of 6 green |
| coverage: serial vs `-n 4 --dist loadgroup --cov=vidgen` | 238 s vs 70 s | 3.4x | | identical: 6978 statements, 188 missed, 97 % |

Main before this work: 213-228 s for 4054 tests (three runs). Swap was unchanged (2.5 GB) in all runs. Server-side, no test
left a database behind: only `postgres`, `vidgen`, `vidgen_demo`, `vidgen_migration_test`, `vidgen_test` exist afterwards.
`--dist loadgroup` is needed so the `xdist_group` marks (docker stack, timing tests) take effect; plain `load` ignores them.

## Isolation audit
| Shared resource | Finding | Fix |
|---|---|---|
| PostgreSQL | every pytest session (so every xdist worker) already created its own random `vidgen_<hex>_test` databases and dropped only its own | names now carry the worker id (`vidgen_gw0_<hex>_test`); `vidgen_demo` added to the protected names; six unit modules that held the URL of the real `vidgen_test` now point at a dummy `vidgen_unit_nodb_test` (they never connected) |
| Redis | never real: a double and an in-memory `StubBroker`; the "21 worker tests that hang" are not Redis-bound (they use the stub; the hang I saw earlier happened with the dev stack running) | none needed |
| TCP ports | only `free_port()`, no fixed bind | none |
| Docker stack test | one fixed compose project `vidgen-t3test` | project name `vidgen-t3test-<worker>`, module marked `xdist_group("docker-stack")` |
| Temp folders | one test (`test_temp_work_folder_is_removed_after_a_failed_render`) globbed the machine-wide temp folder: **real flaky failure found in 1 of 3 early parallel runs** (another worker's MuseTalk temp folder appeared) | test redirects the temp folder to its `tmp_path`; a static check forbids reading the shared temp folder without redirecting it |
| Repo tree, env vars, globals | no writes outside `tmp_path`, no env leaks, `dramatiq.set_broker` and `sys.modules` stubs always restored | static checks keep it that way |
| Timing tests | 10 tests with wall-clock bounds | tagged `xdist_group("timing")`, the two 0.5 s bounds relaxed to 2 s |

A first version of one new static check took 44 s (an AST scan that called `get_source_segment` on every node). It is now 0.08 s.

## Needs the Admin (guard)
1. **`pyproject.toml` / `uv.lock`.** The guard refused backend-dev's edit of `pyproject.toml`. `uv add --dev pytest-xdist` already resolved
   **pytest-xdist 3.8.0** (plus execnet 2.1.2, nothing else changed) and left `"pytest-xdist>=3.8.0"` and the lock change **uncommitted**
   in the worktree. Needed: the exact pin. Run in `.worktrees/xdist`:
   `uv add --dev "pytest-xdist==3.8.0" && git add pyproject.toml uv.lock && git commit -m "build: add pytest-xdist to the dev dependency group (exact pin)" && git push origin perf/pytest-xdist`
2. **`.github/workflows/ci.yml`** is outside the agent grants. Patch: `docs/patches/ci-pytest-xdist.patch` (`git apply docs/patches/ci-pytest-xdist.patch`):
   the pytest step becomes `uv run pytest -q -p no:cacheprovider -n auto --dist loadgroup`. Coverage keeps working: `pytest-cov` merges per-worker data (identical totals above).

## CI estimate
The last CI pytest step took **317 s** (public repo, 4 vCPU `ubuntu-24.04`). Locally `-n 4 --dist loadgroup` is 3.3x faster than serial, so about **95-130 s**, saving roughly 3 to 3.5 minutes per CI run. The real number is reported once CI runs on the PR.

## Not changed (reported only)
- **Vitest** already runs in parallel worker threads and takes about 7 s inside a 1 min 40 s job (the time is `npm ci` and setup): nothing to gain.
- **Playwright** (about 3.5 min in CI): the three projects (desktop, reduced-motion, tablet) run one after another against one stack, and the main flow spec is serial with shared data. Possible later: run the three projects as three parallel CI jobs, each with its own stack (about 3x runner minutes, about 1.5 min wall time).

## Leftovers
Parallel runs left per-worker Docker images (`vidgen-t3test-gw0`, `-gw1`, `-gw6`, `-master`, 1.24 GB each but sharing layers; 15 image tags in total). I did not remove them. Suggestion: have the Docker test's teardown remove the project's images (`compose down --rmi local`), or remove them yourself with `docker image ls | grep t3test` and `docker image rm`.
