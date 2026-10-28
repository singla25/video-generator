# Backend developer — Changelog

Newest first. One entry per task.

## 2026-10-20 - dev_up.sh asks before migrating
- `scripts/dev_setup.py pending` lists unapplied migrations (read-only); `dev_up.sh` shows them and asks y/N, and never applies without an answer (no terminal = refuse). Tests: `tests/unit/meta/test_dev_setup.py` (3). Open: none.

## 2026-10-20 - W-4 fixes (progress, rows snapshot)
- `progress_percent` now counts renderable rows only (skipped excluded; nothing renderable = 0). `GET /batches/{id}/rows` also returns `counts` and `progress_percent` from the same transaction as the rows.
- Files: `services/batch_rules.py`, `batch_queries.py`, `batch_views.py`, `api/schemas_batches.py`. Tests: 1744 Python pass. Open: none.

## 2026-10-20 — T14 round 2 (DD-10 layering)
- `RowRenderer` takes `row_store_factory` (new `RowStore`/`PreviewSink` exports in `vidgen.ports`); the label band comes from `RenderConfig.label_band_share` (setting `label_band_share`, default 0.10, minimum 0.10). No `vidgen.infrastructure` import remains in `vidgen/services` (test_layering).
- `worker/runner.py` builds the store factory; only `run()` is marked `# pragma: no cover`. Open: `render_config`/`build_renderer` need a unit test (module shows 0 % until then).

## 2026-10-20 — T14 (render pipeline, worker, queue adapter)
- Pipeline: `services/render_row.py` (RowRenderer: claim, tts -> lipsync -> encode -> check -> publish, retry classification, previews, manifest), `claim_rules.py` and `manifest.py` (pure), `infrastructure/db/row_store.py` (claim with `FOR UPDATE SKIP LOCKED`, batch completion under a batch row lock), ports `rows.py`, domain `outcomes.py`.
- Queue and worker: `infrastructure/queue/dramatiq_queue.py` (ids only in messages, `depth()`), `worker/actors.py` (retries and busy/paused rows are re-sent with a delay; a busy row is re-checked until its worker finishes or the row goes stale), `worker/runner.py` (`python -m vidgen.worker`).
- Defaults: `infrastructure/fakes` (STT, tone voice, pass-through lip sync, accept-all checker) wired when `ai_backend=fake`; `DramatiqJobQueue` on Redis is the default queue.
- Privacy: `StripQueryFilter` on `uvicorn.access` removes query strings (DD-9); batch deletion now also removes `manifest.csv`.
- Domain: `plan_timing` snaps float noise below 1e-9 s to zero padding (needed for exact plan equality in tests).
- Layering note: `RowRenderer` takes a `session_factory` (the T13 contract) and builds `SqlRowStore` itself, so `services/render_row.py` imports one infrastructure class.
- Tests: 1186 fast + 6 slow pass; 6 fast and 2 slow fail because of test defects (reported).
- Open: tests for `infrastructure/fakes` and `worker/runner.py`; a transactional outbox for queue sends (M2).

## 2026-10-20 — T12 (batch services + endpoints)
- Ports: `JobQueue`, `BatchStore` and batch records (`ports/batches.py`), `Storage.folder_exists`, `UnitOfWork.batches`. Domain: `BatchAction.RETRY`, `DRAFT -> CANCEL` transitions (D-19).
- Infrastructure: `SqlBatchStore` (Core bulk inserts, row locks, grouped counts), `LocalStorage.folder_exists` and `remove_stale_temp`.
- Services (no FastAPI): `batch_create`, `batch_flow`, `batch_queries`, `batch_downloads` (streamed ZIP + manifest), `batch_retention`, pure `batch_rules`, facade `batches.BatchService`.
- API: `/batches/*`, `/batches/{id}/download.zip`, `failures.csv`, `/stats/daily`; sheet uploads streamed with size limit (413); missing job queue fails loudly (`_NotConfiguredQueue`) until T14.
- No migration 0002: preview state, mapping and sheet name live in the JSON `batches.column_mapping`.
- Choices: jobs are queued after the commit (an outbox would be safer, M2); resume does not re-queue (worker must defer jobs while paused); `httpx` logger is set to WARNING because URLs can hold search text.
- Tests: 1064 pass; 7 fail because of test defects (session TTL 8 h vs clock advances of days). Verified green with VIDGEN_SESSION_TTL_MINUTES=999999.

## 2026-10-19 — T10 round 2 (D-17)
- Login protection state moved to Postgres: new table `login_attempts` (campaign_id, client_key [resolved IP or `*` for the global row], window_started_at, failure_count, locked_until, last_allowed_at; PK campaign_id + client_key). `services/login_guard.py` is now pure decision functions plus a thin `LoginGuard` over a `LoginStateStore`; `infrastructure/db/login_state.py` implements it. Every attempt locks the global row (`SELECT ... FOR UPDATE`), so instances never lose updates; stale client rows are pruned on each write.
- Partial unique index `uq_batch_rows_batch_id_voter_id_index_live` (status <> 'SKIPPED') and `ix_batches_finished_at`. Migration 0001 amended in place (create-only upgrade, reverse downgrade, no data); migration tests (schema diff empty, round trip) pass.
- The repository does NOT map IntegrityError to DUPLICATE_ID: the T10b tests expect the raw IntegrityError. Window counting is now a fixed window from the first failure.
- Open: `test_models::test_all_expected_tables_are_defined` expects exactly six tables; it needs `login_attempts` added (tester).

## 2026-10-19 — T10 (persistence, migration 0001, auth, templates, audit)
- DB: `infrastructure/db/{models,repositories,uow}.py` (SQLAlchemy 2 typed models, naming convention, PII only as ciphertext + blind index). Ports gained `TemplateRepository`, `AuditRepository`, `UnitOfWork`, `TemplateRecord`, `AuditEntry`.
- Migration `0001_initial` (hand-written, create-only; downgrade drops the six tables in reverse). `env.py` needs only a DB URL (`-x db_url`, `sqlalchemy.url`, or `VIDGEN_DATABASE_URL`), no Settings. Checked offline (`--sql`) against the models' DDL: same statements, only constraint order differs. Never run against a database.
- API: `create_app(settings, deps=AppDeps(...))`, signed session cookie + CSRF header, login guard (D-15), client-address resolution, streaming uploads with size limits (413 before storing), consent type by content, template/slot/audit endpoints, uniform `{code, message}` errors.
- Services: `login_guard`, `templates`, `audit` (no FastAPI imports). Settings gained cookie/session/login/trusted_proxies/encryption_key_id and hex key helpers.
- Choices: routers are mounted flat (FastAPI 0.146 `include_router` hides routes from `app.routes`); login-guard state is in-process (a multi-instance deployment needs Redis); sessions are stateless signed cookies (logout clears cookies, no server-side revocation; bump `session_version` to revoke all); `batch_rows.voter_id_index` index is NOT unique (duplicate IDs are stored as skipped rows); no `unique` on campaign names (tests create several), default campaign has a fixed id; default speech-to-text is a placeholder that fails with STT_FAILED until T14.
- Tests: 837 pass, 1 fails (see report: `test_crossing_the_global_cap_writes_exactly_one_alert_per_window` conflicts with D-15 item 2); slow 4 pass.
- Open: that one test; the migration round-trip test is for the tester.

## 2026-10-18 — T8 (FFmpeg engine + label)
- Added `infrastructure/ffmpeg/{encoder,graph,facts,loudness,runner,label}.py`. `graph.py` and `loudness.py` are pure builders (TimingPlan to filter graph). The engine executes the plan only.
- Speech stretch uses `atempo` (this ffmpeg build has no `rubberband`). Crossfade uses `acrossfade` (qsin, configured ms) at both joints. Loudness: ebur128 on template slot and new audio, then `volume` gain (clamped to 24 dB).
- Extension (D-11): the slot's video frames are slowed with `setpts`, then constant fps; label PNG overlaid on every frame; template metadata dropped, our keys written with `use_metadata_tags`.
- Safety: argument lists, no pipes (temp files) so a killed tool cannot hang us, timeout gives RENDER_TIMEOUT, temp output beside the target then `os.link` (never overwrites).
- Label: Latin and Devanagari runs use their own fonts. **Pillow here has no Raqm**, so Devanagari is NOT correctly shaped (conjuncts and vowel-sign order). Needs a Pillow build with libraqm before M2 or production use.
- Ports: `VideoEncoder.render` follows the T7 contract. Adapter-to-port checks now live in `if TYPE_CHECKING` blocks in each adapter; `conformance.py` removed.
- Tests: 596 pass, 4 fail (test problems, reported to CEO); slow 4 pass. Pure-helper gaps (need tester unit tests): graph.py lines 142 and branches 92, 110, 115; loudness.py lines 16, 24; facts.py error paths.
- Open: the 4 failing tests; Raqm.

## 2026-10-18 — T6 (ingest adapters)
- Added `infrastructure/sheets/reader.py` (FileSheetReader), `ffmpeg/probe.py` (FfprobeVideoProbe), `storage/local.py` (LocalStorage), `crypto/aesgcm.py` (AesGcmCipher), `conformance.py` (mypy port checks).
- Ports: new `VideoProbe`; `probe` removed from `VideoEncoder`; `SheetReader` gained `numbered_rows` and `sheet_name`; data types `SheetRow`, `VideoInfo`, `VideoLimits` live in `ports/models.py` (adapters re-export them).
- Tests: 478 not-slow + 3 slow pass; infrastructure coverage 93 % (each module 93-98 %).
- Choices: xlsx uses the first *visible* sheet and pads rows to header width; mp4 vs mov told apart by the `major_brand` tag; storage publishes with hard-link (`os.link`) so a name clash can never overwrite; cipher blob = key-id length byte + key id + nonce + ciphertext, key id authenticated.
- Open: none.

## 2026-10-18 — T4 (domain)
- Implemented `vidgen.domain.{codes,headers,validation,naming,status,timing,retry,stats,slot_match}` (pure: stdlib + `regex`).
- 334 tests in tests/unit/domain pass; domain coverage 100 % line + branch. ruff, ruff format, mypy strict clean.
- Choices: ZWJ/ZWNJ allowed only between Devanagari characters; Devanagari digits and dandas are not name characters; only valid rows register their ID for duplicate detection; header/mapping errors other than a missing column use `UNSUPPORTED_SHEET` / `COLUMN_NOT_FOUND`; `SlotTooShortError` uses `SLOT_NOT_FOUND`.
- Open: none.

## 2026-10-18 — T2 (tooling + skeleton)
- Python 3.11 + uv, hatchling build, approved runtime/dev deps (incl. `regex`, `types-regex`), tool config (ruff, mypy strict, pytest, coverage).
- `backend/vidgen` skeleton per ADR-008, Protocols in `ports/interfaces.py`, `settings.py`, `logging.py` (closed non-PII context).
- Alembic initialised in `backend/migrations` (`backend/alembic.ini`), no revisions.
- `docker-compose.yml` (postgres:16, redis:7, localhost-only). Ruff excludes `scripts/`, `.claude/`, `main.py`.
- Files: `pyproject.toml`, `uv.lock`, `.python-version`, `docker-compose.yml`, `backend/**`, this doc folder.
- Tests added: none (skeleton). Open: `docker compose` plugin missing on this Mac; compose file only YAML-parsed.

## 2026-10-18 — SETUP
- Agent created.

## 2026-10-28 — FIX-UPLOAD-2
- `vidgen/api/errors.py`: SQLAlchemy OperationalError/InterfaceError -> 503 `DB_UNAVAILABLE`; redis errors and ConnectionRefusedError -> 503 `QUEUE_UNAVAILABLE`. Fixed plain messages, logged at error level (exception type only, no DSN). Other errors stay 500.
- Tests: tests/unit/api/test_dependency_outage.py (written by tester). Open: none.

## 2026-10-28 — FIX-WORKER-2
- Added WorkerHeartbeat port, RedisWorkerHeartbeat and HeartbeatLoop (redis_heartbeat.py), AppDeps.worker_heartbeat, the system status route (routes_system.py), heartbeat settings (key, ttl, interval); the worker process beats every 5 s and stops the loop on shutdown.
- Files: ports/interfaces.py, ports/__init__.py, settings.py, api/container.py, api/app.py, api/routes_system.py, infrastructure/queue/redis_heartbeat.py, worker/runner.py.
- Tests: test_worker_heartbeat.py and test_system_status.py (25) pass; full suite 1794 passed.
- Open: plain mypy also checks backend/spikes/m2_mac (988 pre-existing errors, none in vidgen).

## 2026-10-28 — L2+L3 (local real AI adapters)
- New package `vidgen/infrastructure/local_ai/`: errors, guard (SingleRenderGuard), offline (offline_only), name_slot, stt (faster-whisper), transliterate (Qwen), tts (Chatterbox), lipsync (MuseTalk, runtime loader is a stub until L4), loaders (heavy imports only here), factory (build_ai_adapters, effective_worker_threads, describe_mode, log_startup_warning, local_label_band_height). Weights live in `<local_ai_weights_dir>/{whisper,qwen,chatterbox,musetalk}`.
- Settings: `ai_mode` (fake|local), `local_ai_weights_dir`. Legacy `ai_backend` kept because tests/unit/worker/test_runner.py still pins it. `FakeTransliterator` added. Runner and container use the factory; worker threads forced to 1 in local mode; local mode logs the ADR-012 unverified-weights warning and sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE.
- Tests: tests/unit/ai_local (80 pass, smoke skipped). Open: status route does not return ai_mode (test_system_status pins exact keys); MuseTalk runtime (L4); Chatterbox `from_local` call unverified without weights.

## 2026-10-28 - L4a
- System status response now returns `ai_mode`.
- Spoken-name confirmation: POST on the batch preview path `confirm-spelling` with `{spoken_name}`. The preview JSON gains `suggested_spoken_name`, `spoken_name`, `spoken_name_confirmed` (local mode only). Approve is refused with 409 `SPELLING_NOT_CONFIRMED` in local mode until confirmed. Stored AES-GCM encrypted (base64) in the existing batch JSON document; no migration.
- Open: the confirmed name is not yet fed into the render of the preview or rows.

## 2026-10-28 - L4 real MuseTalk lip-sync (AI_MODE=local, Mac MPS)
- `loaders.py`: real `load_musetalk` (in-process, models loaded once, float32 MPS, heavy imports only here).
- `musetalk_support.py` (new, no heavy imports): ffmpeg frame extract/assemble, template fingerprint, `LandmarkCache` (face boxes per template, JSON on disk).
- `backend/scripts/setup_musetalk.py` + `musetalk_mac.patch`: one-time clone (pinned 0a89dec), patch, weights, face-detector warm-up. Never run by the app.
- `SqlRowStore._job`: preview row speaks the confirmed spoken name (preview.spoken_name_enc), else the row's own, else the name.
- Peak memory 16-18 GB, one render at a time (SingleRenderGuard). Lip-sync window starts at 0 s of the template (port has no slot argument).
- Tests: none added (tester's job). Open: real-weights run not verified here.
