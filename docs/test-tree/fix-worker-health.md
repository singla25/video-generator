# Test tree - FIX-WORKER-1 (DD-29): the dashboard says when the worker is not running

Bug: a batch preview was queued while the worker process was stopped; the dashboard showed 0 % / Queued for hours with no error. Branch `fix/worker-health`.

Tests: `tests/unit/infra/test_worker_heartbeat.py`, `tests/unit/api/test_system_status.py` (pytest; `tests/fixtures/redis_double.py` is an in-memory Redis with expiry on the shared FakeClock, no new dependency) and `tests/frontend/unit/worker-health.test.tsx` (Vitest + MSW; the default handler for the status route reports a live worker).

```
Feature: Worker heartbeat (port WorkerHeartbeat, RedisWorkerHeartbeat)
├── Scenario: worker running
│   ├── ✅ beat sets vidgen:worker:heartbeat with EX 15; alive right after; a new beat extends life
│   └── ✅ interval 5 s, two beats fit in one life
├── Scenario: worker stopped
│   ├── ❌ no beat yet -> not alive; 15 s after the last beat -> not alive
│   └── ⚠️ boundary 14.9 s alive, 15.0 s dead; beat after expiry revives
├── Scenario: several workers
│   └── ⚠️ one stops, the other keeps the signal; all stopped is detected
└── Scenario: Redis down
    ├── ❌ is_alive raises a redis error (the route turns it into redis_ok=false)
    └── ❌ beat logs at error level, does not raise, no DSN in the log

Feature: GET /system/status
├── ✅ 200 {worker_alive, queue_depth, redis_ok}; follows the heartbeat; real adapter with expiry
├── ❌ 401 without a session; POST -> 405
└── ⚠️ Redis down -> 200 worker_alive=false, redis_ok=false, depth null (not 503); depth error or
       queue without depth -> null; exact keys only; no DSN/password; works with the DB down

Feature: Dashboard banner (frontend)
├── ✅ TT-WH-P1..P3 alert with start hint when worker down and queued rows or pending preview; on every page
├── ❌ TT-WH-N1..N5 hidden when alive, nothing to do, status 500/503/network/non-JSON, loading, batch list failing
└── ⚠️ TT-WH-E1..E6 401 -> login; no call on login screen; polling shows/hides; redis_ok false; reduced motion; no secrets

Feature: Slow preview (frontend)
├── ✅ TT-WH-P4..P6 over 30 s pending: "Preview is taking longer than expected", worker named when down, Retry re-posts
├── ❌ TT-WH-N6, N7 live worker not blamed; nothing before 30 s
└── ⚠️ TT-WH-E7, E8 failing status call adds no accusation; preview done before 30 s never warns
```

Contract chosen by the tests: module `vidgen.infrastructure.queue.redis_heartbeat` (`DEFAULT_KEY`, `DEFAULT_TTL_SECONDS=15`, `HEARTBEAT_INTERVAL_SECONDS=5`, `RedisWorkerHeartbeat(client, key=, ttl_seconds=)` using `client.set(key, value, ex=)` and `client.exists(key)`), port `vidgen.ports.WorkerHeartbeat` (`beat()`, `is_alive()`), `AppDeps.worker_heartbeat`, queue depth from `job_queue.depth()`, route GET `/system/status`.
