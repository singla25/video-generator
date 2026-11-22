# Test tree: running the backend suite in parallel (pytest-xdist)

Task XD-T1. Goal: `pytest -n 4`, `-n auto` and `--dist loadgroup` give the same pass/skip counts as
the serial run. Checks live in `tests/unit/meta/test_xdist_isolation.py` (static, no Docker/DB).

## Audit: what the suite shares

| Resource | Finding | Action |
|---|---|---|
| PostgreSQL | `tests/integration/conftest.py` makes random `vidgen_<hex>_test` / `vidgen_mig_<hex>_test` per session; each xdist worker is its own session, so no clash. Names were not traceable to a worker. Six unit modules carried the URL of the real `vidgen_test` database (never connected). | Worker id in names (`vidgen_gw0_<hex>_test`, `master` when serial); `vidgen_demo` added to PROTECTED; unit URLs renamed `vidgen_unit_nodb_test`. |
| Redis | Never real: doubles and Dramatiq `StubBroker`. | None. |
| TCP ports | Only `free_port()` (bind to port 0) in the Docker e2e; no fixed bind in the suite. | Static check forbids fixed binds. |
| Docker / compose | e2e used the fixed project `vidgen-t3test` (containers, volumes, images collide across workers). | `project_name()` = `vidgen-t3test-<worker>`; module marked `xdist_group("docker-stack")` so the module-scoped stack is built once. |
| Files outside tmp_path | None found: repo files (`ROOT / ...`, `__file__`) are only read. `docs/html`, `.dev`, `media` are never written by tests. | AST check forbids repo-tree writes. |
| Environment variables | No `os.environ` assignment; `test_mode_switch` sets HF offline vars through app code and cleans up with monkeypatch. | Static check forbids assignments without monkeypatch. |
| Global state | `dramatiq.set_broker` is always restored (two integration modules, e2e conftest). `sys.modules["modal"/"torch"]` use `monkeypatch.setitem`; `test_modal_whisper_size` pops its own key; no random seeds, no frozen time, no logging handlers left behind (`setLevel` on a test logger only). Per worker process, so nothing crosses workers. | None. |
| Wall-clock bounds | 10 tests assert `perf_counter` bounds (0.5 s to 10 s); the hanging-ffmpeg test also relies on a timeout. Under CPU load they can flake. | Tagged `xdist_group("timing")` (they run on one worker under `--dist loadgroup`, so they do not compete with each other); the two 0.5 s bounds raised to 2.0 s because plain `-n` ignores groups. |
| Session fixtures | `test_db_url`, `migration_db_url`, `db_engine`: per-session, so per-worker; each worker pays create + `create_all` once. | None. |

## Tree

```
Feature: Parallel-safe backend suite
├── Scenario: integration database names
│   ├── ✅ names carry the worker id (gw0, gw13) or "master" when serial
│   ├── ❌ cleanup refuses vidgen, vidgen_demo, vidgen_test, vidgen_migration_test, postgres and names not ending in _test
│   └── ⚠️ 100 generated names are unique and never collide with the protected list
├── Scenario: Docker stack e2e
│   ├── ✅ project name is vidgen-t3test-<worker>
│   └── ⚠️ module is one xdist_group("docker-stack")
├── Scenario: shared resources scan
│   ├── ❌ no test module hard-codes a real database name (allow-list for assertions only)
│   ├── ❌ no fixed TCP port bind
│   ├── ❌ no write under the repo tree outside tmp_path
│   └── ❌ no os.environ assignment without monkeypatch
└── Scenario: wall-clock assertions
    ├── ✅ every test with a perf_counter bound is tagged xdist_group("timing")
    └── ⚠️ a new perf_counter bound in an unlisted module fails the scan
```
