Feature: Preview stage progress and opt-in model warm-up (T-PROG-BE)
Tests: tests/unit/infra/test_redis_stage_reporter.py, tests/unit/services/test_render_preview_stage.py,
       tests/integration/api/test_preview_stage.py, tests/unit/infra/test_warm_up_setting.py,
       tests/unit/worker/test_warm_up.py

CONTRACT (the developer implements exactly this)
1. Port `vidgen.ports.progress.StageReporter` (Protocol): `report(batch_id: UUID, stage: str) -> None`, `current(batch_id: UUID) -> str | None`, `clear(batch_id: UUID) -> None`.
2. Adapter `vidgen.infrastructure.queue.redis_progress.RedisStageReporter(client, ttl_seconds: int = 900)`: stores key `vidgen:stage:<batch_id>` with TTL; `current` returns None when missing; `clear` deletes.
3. In-memory double `FakeStageReporter` in tests/fixtures/doubles.py (you add it).
4. The render-row service accepts optional kwarg `stage_reporter` (default None = no-op). During a PREVIEW job, each `run.stage(name)` start reports the raw stage name for the preview's batch id, in order fetch, tts, lipsync, encode, check, publish; after `preview_rendered` or `preview_failed` the reporter is cleared. Row (non-preview) jobs do not report. A reporter that raises must NOT fail the render (error is logged).
5. API: GET batch JSON `preview` gains `stage`: while preview status is pending: "preparing" for fetch or no stage yet, "voice" for tts, "lipsync" for lipsync, "finishing" for encode/check/publish; otherwise null (READY, FAILED, no preview). Unknown raw stage -> "preparing".
6. Settings `warm_up_on_start: bool = False` (env VIDGEN_WARM_UP_ON_START). Function `vidgen.worker.warm_up.warm_up_if_enabled(settings, warmables) -> bool`: returns False and calls nothing when disabled or when ai_mode is not "local"; when enabled and local, one model at a time: for each warmable in order, `warm_up()` then `release()` before the next one is touched (w1.warm_up, w1.release, w2.warm_up, w2.release, ...). Never more than one model is resident at once. Returns True. A `warm_up()` that raises is logged, `release()` is still tried best-effort, then the next model runs. A `release()` that raises is logged and the next model still runs. Nothing crashes start-up.

Assumptions the tests make beyond the contract (flagged to CEO):
- A. The API gets the reporter through `AppDeps.stage_reporter` (default: Redis adapter on settings.redis_url).
- A. An API read of the stage never fails the batch page: if the reporter raises, the stage is "preparing" and GET still returns 200.
- A. The adapter does not swallow Redis errors (the render service logs them); `ttl_seconds` must be positive.
- A. Warm-up is one model at a time (warm_up then release per model, before the next): never more than one model resident. A warm_up() error still triggers a best-effort release(). Any warm_up() or release() error is logged and does not stop the others.

Scenario: Worker reports the preview stage (render_row, preview job)
├── ✅ Positive  — P1 log is [stage:fetch, stage:tts, stage:lipsync, stage:encode, stage:check, stage:publish, rendered, clear]; reports carry the batch id
│                  — P2 a stage is reported for the preview batch, never the row id
│                  — P3 no reporter (None) renders and reports exactly as before
├── ❌ Negative  — N1 reporter.report raising on every call: preview still rendered, error logged (WARNING or higher)
│                  — N2 reporter.clear raising: preview still rendered and reported, no exception
│                  — N3 failing preview with a raising reporter: failure still reported with its code
│                  — N4 failure (TTS_FAILED, OUTPUT_CHECK_FAILED): log ends with failed, clear; nothing rendered
└── ⚠️ Edge      — E1 unknown preview row (job gone): reporter untouched, nothing reported
                   — E2 row (non-preview) job, success and failure: reporter never called

Scenario: Redis stage adapter (RedisStageReporter)
├── ✅ Positive  — P1 report then current returns the stage
│                  — P2 key is exactly `vidgen:stage:<batch_id>` (lowercase hyphenated UUID)
│                  — P3 default TTL 900 s: present at 899 s, gone at 900 s
│                  — P4 custom ttl_seconds is honoured
│                  — P5 clear removes the stage
│                  — P6 a newer report replaces the stage and renews the TTL
│                  — P7 two batches are isolated
├── ❌ Negative  — N1 Redis down on report, current, clear: error propagates (not swallowed)
│                  — N2 ttl_seconds 0 or negative rejected with ValueError
└── ⚠️ Edge      — E1 current on a missing key returns None
                   — E2 clear on a missing key is a no-op
                   — E3 client returning str instead of bytes (decode_responses) still works
                   — E4 StageReporter port is a Protocol

Scenario: Preview stage in the batch JSON (GET /batches/{id})
├── ✅ Positive  — P1 pending + fetch -> "preparing"; tts -> "voice"; lipsync -> "lipsync"; encode, check, publish -> "finishing"
│                  — P2 pending with no stage yet (reporter empty) -> "preparing"
│                  — P3 the key `stage` is present in the fake-mode preview body
│                  — P4 stage follows the reporter as it moves (tts then lipsync)
├── ❌ Negative  — N1 unknown raw stage ("mystery", "", "TTS") -> "preparing"
│                  — N2 reporter raising on current: still 200, stage "preparing"
│                  — N3 Redis down is not a 500
└── ⚠️ Edge      — E1 READY with a stale stage still stored -> null
                   — E2 FAILED with a stale stage stored -> null
                   — E3 DRAFT with no preview requested -> null
                   — E4 after preview_rendered / preview_failed the stage is null
                   — E5 a second batch does not see the first batch's stage

Scenario: Opt-in warm-up setting
├── ✅ Positive  — P1 default False when VIDGEN_WARM_UP_ON_START is unset
│                  — P2 truthy env values ("true", "1", "yes", "on") -> True
├── ❌ Negative  — N1 invalid value ("maybe") -> ValidationError naming the field
│                  — N2 falsy env values ("false", "0", "no", "off") -> False
└── ⚠️ Edge      — E1 env var name is exactly VIDGEN_WARM_UP_ON_START (other names ignored)

Scenario: Warm-up at worker start (warm_up_if_enabled, one model at a time)
├── ✅ Positive  — P1 enabled + local: w1.warm_up, w1.release, w2.warm_up, w2.release; returns True
│                  — P2 each warmable warmed and released exactly once
│                  — P3 never more than one model resident at a time; none left loaded at the end
├── ❌ Negative  — N1 disabled (local or fake): returns False, nothing called
│                  — N2 enabled + fake mode: returns False, nothing called
│                  — N3 a warmable whose warm_up raises: logged, its release still tried, next model still runs, no exception
│                  — N4 a release() that raises: logged, the next model still runs
│                  — N5 warm_up and release both raise for one model: both logged, next model still warmed and released
└── ⚠️ Edge      — E1 empty list when enabled + local: returns True, no error
                   — E2 warmables given as a one-shot iterator: all still warmed and released
                   — E3 a failing last model: returns True, nothing left resident
