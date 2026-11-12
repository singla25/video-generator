# Backend developer — Changelog

Newest first. One entry per task.

## 2026-10-31 - DD-38 green (confirmed spelling kept, drafts view)
- `BatchFlow.request_preview` keeps the confirmed `spoken_name` on the new PENDING preview record (nothing else is carried over); the approval gate passes after a regenerate. `GET /batches?view=drafts` lists only DRAFT batches, newest first (`BatchListView.DRAFTS`, `batch_list_filter.view_condition`); other views unchanged.
- Files: `services/batch_flow.py`, `domain/status.py`, `infrastructure/db/batch_list_filter.py`, `api/routes_batches.py` (docstring). No migration, no new dependency.
- Tests: target 66 pass; `tests/unit` + `tests/integration` 2419 pass, 1 skipped. mypy strict errors only in `infrastructure/local_ai/loaders.py`. Open: none.

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

## 2026-10-28 - L7 local AI smoke run (partial: blocked at lip sync)
- Added `backend/scripts/local_ai_smoke.py` (2 rows through the factory adapters, stage by stage, with timings/memory).
- `release()` on the four local adapters (LazyModel.release) so models can run one stage at a time in 24 GB.
- `tts.trim_to_first_utterance`: Chatterbox babbled ~4 s after a 1 s name; clip is cut after the first utterance.
- Weights dir `work/local_ai_weights` built with symlinks; MuseTalk clone patch re-applied on 3 files.
- Open: 2DFAN4 face-landmark weights are not inside the project (spike cached them in the home folder); lip sync cannot run offline until they are in `work/torch/hub/checkpoints/`. No tests added (tester to cover trim and release).

## 2026-10-29 - L8 lip sync keeps the face (mouth-only compositing)
- Problem: MuseTalk's blend replaced the whole lower face; beard came out smooth and lighter.
- New `local_ai/compositing.py` (`composite_mouth`): generated pixels only inside a feathered mouth ellipse; around the lips the original's high-frequency texture is re-added to the colour-matched generated low-pass; the inner core (lips/teeth) stays generated. Outside the ellipse the frame equals the original.
- `loaders._MuseTalkModel._paste`: uses `composite_mouth` for real image arrays, MuseTalk's own blend for non-arrays (keeps the existing fake-based unit tests green).
- New `local_ai/fidelity.py` (SSIM, mean abs diff, Laplacian-variance retention, lower face minus mouth); smoke script prints it per row.
- Measured row 0 (28 frames): SSIM 0.81 -> 0.96, mean abs diff 6.08 -> 3.42, texture retention 0.52 -> 0.89. Row 1: 0.96 / 3.73 / 0.92. Duration 26.2 s, 1080x1300, band 10 %.
- Tests added: none (tester). Suggested: `mouth_masks` (shape, range, core inside outer), `composite_mouth` (pixels outside ellipse unchanged, identical face -> identical frame, colour shift clamped), `lower_face_mask` (excludes mouth rect), `frame_fidelity` (identical -> SSIM 1, ratio 1; blurred -> ratio < 1), `mean_fidelity`; update model fakes so `_paste` can drop the fallback.
- Open: lips look slightly low-contrast; ellipse geometry is fixed fractions of the face box (tuned on this template).

## 2026-10-29 - LB-GREEN (DD-32)
- Added AI label style `bubble` (default) | `band`: `Settings.label_style` (`VIDGEN_LABEL_STYLE`), `RenderConfig.label_style` (validated), `PillowBubbleRenderer`, `bubble_diameter`, `bubble_box`, `build_label_renderer` in `infrastructure/ffmpeg/label.py`.
- `RowRenderer` requests a full-frame label for bubble; `local_label_band_height` returns 0 for bubble; runner picks the renderer by style. Band behaviour unchanged.
- Files: backend/vidgen/{settings.py, services/render_support.py, services/render_row.py, worker/runner.py, infrastructure/ffmpeg/label.py, infrastructure/local_ai/factory.py}.

## 2026-10-29 - L10
- mean_fidelity([]) returns the neutral Fidelity(1.0, 0.0, 1.0).
- Lost-queue recovery without a migration: StuckRow, BatchStore.stuck_candidates, JobQueue.has_live_job (Redis marker key per row, 6 h TTL), services/requeue.py, Settings.stuck_after_seconds/requeue_interval_seconds, worker/periodic.PeriodicTask wired into the worker.
- Open: the Redis marker can outlive a finished job (harmless, row is no longer QUEUED).

## 2026-10-30 - Task TV (timing variants, DD-33)
- Added `backend/spikes/m2_mac/timing_variants.py`: re-splices the already lip-synced row row-1 (re-uses speech0.wav, synced0.mp4, label.png) with the app's `plan_timing` + `FfmpegVideoEncoder`, pause/crossfade from `VIDGEN_PAUSE_SECONDS` / `VIDGEN_CROSSFADE_MS`.
- Outputs (git-ignored) in `backend/spikes/m2_mac/work/local_out/timing/`: row-1_A/B/C.mp4. All 26.2 s, 1080x1300, 60 fps.
- Finding: the new name (0.90 s) fits the 1.0 s slot, so `pause_seconds` is never absorbed (pause_absorbed_s=0, extension_s=0). The next template word stays at 1.00 s in A, B and C; only the crossfade differs.
- Tests added: none. Open: a longer gap needs a product change (e.g. always delay the tail).

## 2026-10-30 - NG-GREEN (DD-34 name gap)
- `domain/timing.py`: `MAX_GAP_S = 1.0`; `TimingPlan.gap_s` (last field, default 0.0); `duration_delta_s` = extension + gap; `plan_timing(..., gap_s=0.0)` rejects gaps outside 0-1 s. Gap does not change stretch, absorbed pause, extension or padding.
- `infrastructure/ffmpeg/graph.py`: region length includes the gap; slot segment gets `tpad=stop_mode=clone` for the gap; graph unchanged when gap and extension are zero.
- `settings.py`: `name_gap_s` (`VIDGEN_NAME_GAP_S`, default 0.25, 0-1.0). `services/render_support.py`: `RenderConfig.name_gap_s`. `worker/runner.py` and `services/render_row.py` pass it through.
- Tests: 52 DD-34 tests in the five name-gap files. The held-frame check is relaxed by the tester (0d3ec1e): lossy H.264 keeps the clones luma-identical but not bit-identical.
- Open: no per-template gap tuning; `timing_variants.py` lint is fixed separately.

## 2026-10-30 - BB-GREEN (DD-36 see-through AI bubble)
- `infrastructure/ffmpeg/label.py`: bubble is 48/1080 of the frame width, 12/1080 from the right and bottom edges, faint black tint (alpha 40), white ring (about 4 % of the diameter, alpha 230), white "AI" text with a soft shadow (alpha 120, 1 px at 48 px). Drawn at 4x and downscaled with LANCZOS, clipped to the circle, text centred by its ink box.
- Band style and every public name are unchanged. The font error stays a typed DomainError with no file written.
- Tests: the 64 DD-36 bubble tests pass (test_bubble_look, test_bubble_renderer, test_label_bubble_overlay). Full unit and integration run: 2192 passed, 2 skipped.
- Open: the Admin still has to judge the look on the re-rendered sample row.
- 2026-10-30 B-FIX-depth: JobQueue.depth() checks the Redis client first (llen), so the real RedisBroker no longer crashes the status endpoint.
- 2026-10-31 B-PROG: preview stage progress (StageReporter port, Redis adapter, render reporting, batch JSON `preview.stage`) and opt-in warm-up (`VIDGEN_WARM_UP_ON_START`, `warm_up_if_enabled`, adapter `warm_up()`); the exact-shape preview tests conflict with the new `stage` key, pending Admin/tester decision.
- 2026-10-31 B-PROG-FIX: warm-up holds one model at a time (warm_up then release per model); the preview POST returns the same stage as the GET (describe_preview, preparing); httpx2 logger silenced alongside httpx (HTTP_CLIENT_LOGGERS). Tests: 2312 passed, 1 skipped, 21 deselected.

## 2026-10-31 - BE-GREEN (DD-37 batch views, start limit, template delete)
- `GET /batches?view=all|running|completed|failed`: filter in SQL (`infrastructure/db/batch_list_filter.py`, EXISTS on FAILED rows) inside `BatchStore.list_page`; total and pages follow the view; unknown view is 422. `view=all` is unfiltered.
- `POST /batches/{id}/start` takes optional `limit` (`StrictInt`, >= 1, else 422). `BatchStore.skip_unselected` (`infrastructure/db/batch_limit_store.py`) marks QUEUED rows after the first N as SKIPPED / NOT_SELECTED in the same transaction; folder name counts the selected rows; `BATCH_STARTED` audit has `limit` (null when absent) and `skipped_rows`.
- `FailureCode.NOT_SELECTED` with message "Not selected: outside the number of videos requested."; no DB check constraint blocks it (failure_code is String(64)).
- `DELETE /templates/{id}`: 204; 404 unknown; 409 `TEMPLATE_IN_USE` with the counted message when any batch of any status uses the template. Lock, in-use check and delete in one transaction; stored video and consent files removed after commit; audit `TEMPLATE_DELETED` (template id only). `TemplateRepository.batch_count`, `consent_file_keys`, `delete`; `get(lock=)`.
- `services/storage_cleanup.py`: best-effort `delete_stored`, extracted from batch retention and shared with template delete.
- Files: backend/vidgen/{api/errors.py, api/routes_batches.py, api/routes_templates.py, api/schemas_batches.py, domain/codes.py, domain/status.py, infrastructure/db/batch_store.py, infrastructure/db/repositories.py, infrastructure/db/batch_limit_store.py (new), infrastructure/db/batch_list_filter.py (new), ports/batches.py, ports/interfaces.py, services/batch_flow.py, services/batch_queries.py, services/batch_retention.py, services/batches.py, services/errors.py, services/storage_cleanup.py (new), services/templates.py}.
- No migration, no dependency. Target tests: 57 passed (test_batch_views, test_batch_start_limit, test_template_delete).
- Open: two existing tests conflict with DD-37 and were left unchanged (tests/ is not backend-dev's): tests/unit/domain/test_codes.py::test_failure_code_set_matches_requirements_exactly (exact code set, now + NOT_SELECTED) and tests/integration/api/test_template_profile.py::test_the_slot_cannot_be_changed_through_the_template_resource[DELETE] (expects 404/405, now 204).
- Open: plan AC1 says `all` excludes DRAFT and CANCELLED, but test_view_all_lists_every_batch_in_every_state expects them; implemented per the test (unfiltered).

## 2026-10-31 - DEMO-TEMPLATE (DD-39 synthetic marketing template, spike)
- `backend/spikes/m2_mac/make_marketing_template.py`: builds a synthetic Hindi marketing template with the name spoken in the middle (Lekha audio, MuseTalk lip sync of `sun.mp4`, Pillow headline, app Whisper for the name span). Spike only: no product code, no dependency, no migration. Outputs go to the git-ignored `work/marketing_demo/` folder.
- Result: 12.8 s, 1080x1300, 60 fps, H.264 yuv420p, AAC. Whisper misspelt the name (`सल्मान`), so the slot came from the synthesized parts: 4.7-5.9 s (method noted in the README). Whisper's own word times put the name at 4.5-5.3 s; the Admin should check the slot in the form before use.
- Open: the parts-based span and the Whisper span differ by 0.3-0.6 s; the frame check is the tie-breaker.

## 2026-10-31 - SUF-GREEN (DD-39 spoken suffix after the name)
- `services/spoken_text.py` (new): pure `spoken_text(name, suffix)`. Strips the ends, returns the name alone for an empty suffix or an empty name's "", and skips the suffix when the last words of the name equal it (casefold, word-wise, so multi-word suffixes work).
- `settings.py`: `spoken_suffix` (env `VIDGEN_SPOKEN_SUFFIX`, default "जी", max 20 characters, "" allowed).
- `services/render_support.py`: `RenderConfig.spoken_suffix` (default "", speaks the name only).
- `worker/runner.py`: `render_config` copies the setting.
- `services/render_row.py`: `_produce_video` hands `spoken_text(effective_spoken_name(...), config.spoken_suffix)` to the voice; batch rows and previews both go through it.
- Tests: 64 passed (test_spoken_text, test_spoken_suffix_setting, test_render_row_spoken_suffix). Full unit and integration run (excluding test_worker.py): 2487 passed, 1 skipped.
- Mypy strict: errors only in `infrastructure/local_ai/loaders.py` (pre-existing).
- No migration, no dependency. `.env.example` (not in backend-dev's domain) should gain `VIDGEN_SPOKEN_SUFFIX` for the CEO to assign.

## 2026-10-31 - DEMO-TEMPLATE fix (DD-39 slot from the real word span)
- The slot is no longer the parts sum (4.7-5.9 s, wrong). The script now matches the misspelt first name by similarity (difflib >= 0.6), takes Whisper's span, cross-checks ffmpeg silencedetect (noise -32 dB, 0.06 s), and uses the silence-bounded speech run rounded to one decimal: slot 4.5-5.4 s. The literal rule (Whisper span widened 0.05 s = 4.4-5.3 s) is printed but not used: it ends before the speech does. `--slot-only` re-times the existing template. Parts method removed.

## 2026-10-31 - MID-GREEN (DD-39 part B lip sync starts at the slot)
- `ports/interfaces.py`: `LipSyncer.sync(video, audio, out, start_s=0.0)`. `infrastructure/fakes/adapters.py`: `FakeLipSyncer.sync` accepts `start_s` and still copies the video.
- `services/render_row.py`: the lip sync gets `start_s=slot[0]` (the name's start, not the end or the length).
- `infrastructure/local_ai/lipsync.py`: `MuseTalkLipSyncer.sync` rejects a negative or non-finite `start_s` with `ValueError` before the model loads or any output is written; forwards `start_s` as the 4th positional argument of `run`.
- `infrastructure/local_ai/loaders.py`: `_MuseTalkModel.run(video, audio, out, start_s=0.0)` extracts frames from `start_s`, keys the face-box cache with `landmark_key`, and assembles with `start_s`. `_blend` and `_boxes_and_frames` take the cache key instead of the video.
- `infrastructure/local_ai/musetalk_support.py`: `landmark_key(fingerprint, start_s)` (0.0 keeps the fingerprint; else `-s<ms>`); `extract_frames(..., *, start_s=0.0)` seeks with `-ss` before `-i`; `assemble_video(..., *, start_s=0.0)` keeps the old filter graph for 0.0, otherwise splices original 0..start_s, blended frames, original from start_s + frames/25, with `-t` set to the original duration (the tail is left out when the blended part reaches the end); new `video_duration(video)` via ffprobe.
- Tests: 32 passed (test_mid_slot_support, test_mid_slot_adapter, test_render_row_mid_slot). Full unit and integration run (excluding test_worker.py): 2519 passed, 1 skipped.
- Mypy strict: 8 errors, all in `infrastructure/local_ai/loaders.py` (same count as before). Layering grep (services, domain importing infrastructure): nothing.
- Callers that pass three arguments (`backend/scripts/local_ai_smoke.py`) keep working through the default 0.0. `backend/spikes/` not touched.
- No migration, no dependency.

## 2026-10-31 - SMOKE-MID (DD-39 smoke script on the mid-video name slot)
- `backend/scripts/local_ai_smoke.py`: new optional `--template PATH`, `--slot START END` (manual slot; the transcript still gives the pause after the name), `--sheet PATH.csv` (header `Name,VID`, read with `csv`; blank lines skipped; errors give line numbers only), `--out-name NAME` (sub-folder of `local_out/`). Defaults unchanged when omitted.
- Lip sync now gets `start_s=slot.start_s`; `plan_timing` gets `gap_s=settings.name_gap_s`; the honorific goes through `spoken_text`; the duration check uses `plan.duration_delta_s` (extension plus gap). The fidelity report reads the face-box cache with `landmark_key(fingerprint, start_s)`, the key the product writes (found when the first run failed on the plain key).
- Run (manual slot 4.5-5.4 s, csv sheet, 2 rows, `--out-name mid_slot`): exit 0, peak RSS 5.5 GB, MPS 7.5 GB, total 66 s. Both rows: 1080x1300, 60 fps, 13.07 s against the template's 12.82 s (+0.25 s = the name gap, zero extension). Lower-face fidelity SSIM 0.987.
- Transcript (app STT, output row 1): the name, then `जी` at 5.24-5.42 s; `आप से कहता हूँ` follows at 5.42 s, template 5.26 s. Words after the slot sit about 0.24 s later than in the template (`सब` 6.40 vs 6.64, `सिंगला` 11.24 vs 11.48, last `पर` 12.20 vs 12.44). Words before the slot are unchanged within STT noise.
- Frame mean abs diff (0-255), whole / face (x 200-880, y 300-900): before 1.84 / 1.95; inside 3.03 / 3.04; after 3.47 / 4.34. The after pair is the 0.25 s shift: output at 8.0 s against the template at 7.75 s gives face 1.78.
- Open: the before pair is not ~0 (about 1.9), most likely from the full re-encode; not measured separately. Whisper's Hindi is weak on both transcripts, so word text is only a rough check. Outputs in `backend/spikes/m2_mac/work/local_out/mid_slot/` (git-ignored, not committed).

## 2026-11-12 - T2 installer (docker-and-cloud-setup, AC2/AC3, P3/P4)
- Added `scripts/setup.py` (stdlib only, injectable `Seams`, `main(argv, seams)`): prerequisite checks, mode choice (fake/local/modal), Modal token pair via hidden input and `uv run --with modal`, atomic 0600 settings file with a single-quoted admin hash, migrations only after an explicit "y".
- Added `hash-password` subcommand to `scripts/dev_setup.py` (password on stdin, hash on stdout).
- Tests: 71 installer + 9 hash-password tests now green (`tests/unit/meta`: 566 passed).
- Note: no `from __future__ import annotations` in setup.py because the tests load it without registering it in `sys.modules` (needed by `@dataclass`).
- Open: pre-existing ruff E501/format issues in `scripts/dev_setup.py`, `build_docs.py`, `bench_stats.py` were left untouched (outside the grant).
