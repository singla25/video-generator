# Test tree: native local-AI worker next to the Docker app (E-T1)

Tests: `tests/unit/meta/test_native_worker.py` (static; no Docker, no model, no worker started).
Platform seam: `setup.host_platform() -> (system, machine)`, monkeypatched in tests.

```
Feature: Native worker beside the Docker app
├── Scenario: scripts/setup.py native-worker --print
│   ├── ✅ defaults -> local mode, 127.0.0.1:5432/6379, absolute media path, threads 1, weights dir
│   ├── ✅ custom ports, db user/name, weights dir; both command steps printed in order
│   ├── ✅ relative, absolute, spaced, unicode and emoji media dirs
│   ├── ❌ password, keys and tokens never printed (`***`); nothing written; subprocess never called
│   └── ⚠️ default password redacted; default settings file is <root>/<dotfile>
├── Scenario: Refusals (exit 2, clear message, no process)
│   ├── ❌ not macOS arm64 (Intel Mac, Linux x2, Windows)
│   ├── ❌ missing settings file, directory as settings file, unreadable settings file
│   └── ❌ mode fake / modal / real / empty / no mode line
├── Scenario: docker-compose.yml
│   ├── ✅ postgres and redis on 127.0.0.1 with VIDGEN_DB_PORT / VIDGEN_REDIS_PORT
│   ├── ✅ api and worker mount the same host media folder; profiles; worker scale default
│   ├── ✅ api blanks MODAL tokens; internal service addresses kept
│   └── ❌ no container gets local mode, weights dir or GPU settings; no non-loopback port
└── Scenario: Docs and installer text
    └── ✅ installer source, README and the plan name `python3 scripts/setup.py native-worker`
```
