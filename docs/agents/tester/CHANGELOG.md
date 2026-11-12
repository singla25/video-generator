# Tester — Changelog

Newest first. One entry per task.

## 2026-10-30 — RM-G3 (remove redundant red set)
- Removed: the redundant G3 adapter test set (tests/unit/infra/ai/, docs/test-tree/m2-real-ai.md). The adapters were built as vidgen.infrastructure.local_ai and are covered by tests/unit/ai_local/. The Admin approved the deletion. Those tests failed at collection with ModuleNotFoundError.

## 2026-10-20 - W-4 tests
- Added: progress ignores skipped rows (and all-skipped = 0), rows response carries same-snapshot counts, header follows the rows snapshot, panel shows skipped separately. TT-AC14-E2 updated (all skipped is 0, not 100). Python 1744, Vitest 209.

## 2026-10-19 — T15 (VERIFY M1)
- Added runner tests, 17 tree cases (extra batch/API, ffmpeg VFR and colour, log helper, architecture rules), strict xfails for range requests and two oversize files; tree annotated with a verification table; COVERAGE.md written (98.2 %, domain and render_row 100 %, 1597 passed, 3 xfailed).
- Findings: V1 two files over 300 lines, V2 no range requests, V3 stateless cookie (by ADR). No functional defect.

## 2026-10-19 — T13c (DD-10)
- Fixed 8 test defects (manifest in folder, decoded queue messages, collision-suffix check). Contract change: RowRenderer takes row_store_factory (no session_factory, no cipher) and RenderConfig.label_band_share. Added layering test (services must not import infrastructure), tests for domain outcomes, timing snap and the fake AI adapters.

## 2026-10-19 — T15a (RED: end-to-end)
- Added tests/e2e/{conftest,test_synthetic_batch_e2e}.py: P1 (10-row batch, probe, manifest, downloads, PII logs), E1 (one injected crash, one retry), E2 (delete, no PII). Real app, Postgres test DB, FFmpeg, local storage, Pillow label; fake STT, voice, lip sync, quality. Queue: Dramatiq StubBroker with an in-process worker (no Redis).
- Fails now on the missing worker modules; with throw-away stubs the flow reached the worker wait (template, consent, slot, batch, report, preview request all work).

## 2026-10-19 — T13 round 2 (DD-6)
- Stage order is now tts, lipsync, encode, check, publish. Lip sync sees the original template plus the new audio; its output feeds the single final encode. Added a chain test; FakeLipSync records inputs and can append a marker.

## 2026-10-19 — T13 (RED: worker pipeline)
- Added tests/integration/worker/{world,conftest,test_render_row,test_row_states,test_completion,test_preview_job,test_worker,test_render_row_real_engine}.py, tests/unit/services/test_manifest.py, tests/integration/storage/test_stale_temp.py; fakes in tests/fixtures/pipeline_fakes.py; InMemoryStorage.fail_next.
- Contract modules: vidgen.services.render_row (RowRenderer, RenderConfig, RowOutcomeKind), vidgen.services.manifest, vidgen.worker.actors (WorkerConfig, register_actors), vidgen.infrastructure.queue.dramatiq_queue (DramatiqJobQueue), LocalStorage.remove_stale_temp.
- 123 tests (1 slow). Verified the bodies run with throw-away stubs (not committed).

## 2026-10-19 — T11 (RED: batch API)
- Added tests/integration/api/test_batches_{create,start,control,status,downloads,delete_retention}.py, batch_helpers.py; doubles FakeJobQueue and ChunkSpyStorage; Env.queue. The auth route sweep now fills any path parameter.
- Contract: AppDeps.job_queue (enqueue_preview, enqueue_rows), Container.batches (preview_rendered, preview_failed, run_retention), batch routes plus the daily stats route. API codes added: PREVIEW_NOT_READY, PREVIEW_NOT_APPROVED, INVALID_STATE.
- 193 new tests; 182 fail on missing routes, 11 pass trivially (404 cases); the 871 earlier tests pass.

## 2026-10-19 — T10b
- Fixed the global-cap alert test (429 inside the gap). Added tests/integration/api/test_login_persistence.py (two app instances, restart), tests/integration/db/test_duplicate_guard.py (partial unique index), tests/integration/db/test_migrations.py (own DB vidgen_migration_test), tests/unit/infra/test_system_clock.py.

## 2026-10-19 — T9 (RED: db, auth, templates, audit)
- Added tests/integration/{conftest.py,db/*,api/*}, fixtures tests/fixtures/doubles.py. Test DB fixture uses VIDGEN_TEST_DATABASE_URL (default vidgen_test, name must end in _test), create_all from models, tables emptied per test; no Alembic.
- 126 test functions. Contract modules: vidgen.api.app, vidgen.api.deps, vidgen.infrastructure.db.models, vidgen.infrastructure.db.repositories. Template carries original_name (the spoken name to replace); Settings gains cookie_secure, session_ttl_minutes, session_version.
- 649 earlier tests pass; new ones fail on ModuleNotFoundError.

## 2026-10-19 — T7b
- Fixed float window arithmetic (window_n) and the three metadata tests (generated_on/batch_id required). Added unit tests for graph.py, loudness.py, facts.py (100 % line+branch). Added test_complex_text_shaping_is_active_for_devanagari (fails until Pillow has raqm).

## 2026-10-18 — T7 round 2
- Replaced filter-name checks (acrossfade, atempo) by behaviour: spoken part ends at slot start + plan.final_audio_s within crossfade + 20 ms, starts audible at slot start. Security test spies on Popen (any subprocess function). Label fixtures now need two fonts (NotoSansDevanagari-*.ttf, NotoSans-*.ttf); renderer signature PillowLabelRenderer(devanagari_font=, latin_font=, text=).

## 2026-10-18 — T7 (RED: FFmpeg video engine + label renderer)
- Added tests/integration/ffmpeg/{conftest,test_output_format,test_audio_splice,test_label_overlay,test_metadata,test_encoder_errors}.py and tests/unit/infra/test_label_renderer.py; fixtures tests/fixtures/{templates,analysis,spies,assets}.py.
- Contract modules: infrastructure.ffmpeg.encoder (FfmpegVideoEncoder), infrastructure.ffmpeg.label (PillowLabelRenderer, label_band_height, LABEL_TEXT). Fail on ModuleNotFoundError (RED); 478 earlier tests still pass.
- Verified the test bodies run to the first adapter call using throw-away stub modules (not committed). Thresholds (loudness, click step, frame diffs) are not yet validated against a real implementation.
- Font tests fail with a clear message until the Admin places the .ttf in backend/vidgen/assets/fonts/.
- Also re-escaped non-ASCII literals in four T5 test files (cosmetic, tests unchanged).

## 2026-10-18 — T5 (RED: sheets, video probe, storage, cipher)
- Added tests/integration/ingest/{test_sheet_reader,test_sheet_scale,test_video_probe}.py, tests/integration/storage/test_local_storage.py, tests/unit/infra/test_cipher.py; fixtures tests/fixtures/{media,sheets}.py (ffmpeg lavfi + openpyxl generators, code only).
- Contract modules: infrastructure.sheets.reader, ffmpeg.probe, storage.local, crypto.aesgcm. All fail with ModuleNotFoundError (RED); slice-A domain tests still 334 passing.
- Not covered here: odd-dimension video (ffmpeg lavfi rounds to even sizes) and sheet max-rows (rule not specified).

## 2026-10-18 — T3 (RED: domain unit tests)
- Added tests/unit/domain (13 files, 166 test functions) + tests/fixtures/names.py. Branch feat/m1-domain.
- Contract modules: headers, codes, validation, naming, status, timing, retry, stats, slot_match. All fail with ModuleNotFoundError (RED).
- Ruff check/format clean; mypy --strict only reports the missing vidgen.domain modules.
- Non-ASCII in tests is written as \\u escapes (readable diffs, ruff RUF001).

## 2026-10-18 — T1 follow-up (Addendum B)
- Applied Addendum B1–B13 to `docs/test-tree/m1-batch-pipeline.md`; open issues replaced by a resolution table. Added 24 cases (5 positive, 8 negative, 11 edge). Final: 105 positive / 98 negative / 171 edge = 374.
- New ambiguities: NA-1 (ETA remaining count), NA-2 (idempotency key reuse), NA-3 (STT tie-break/threshold).
- Files: docs/test-tree/m1-batch-pipeline.md. Tests added: none.

## 2026-10-18 — T1 (M1 test tree)
- Wrote `docs/test-tree/m1-batch-pipeline.md` covering AC1–AC19 + E2E, with Addendum A applied.
- Files: docs/test-tree/m1-batch-pipeline.md. Tests added: none (tree only).
- Open issues: OI-1..OI-13 listed at end of the tree.

## 2026-10-18 — SETUP
- Agent created.

## 2026-10-19 — F1 (M3 dashboard: test tree and failing UI tests)
- Wrote `docs/test-tree/m3-dashboard.md` (generated by `tests/frontend/tools/gen_test_tree.py` from case IDs `TT-UI-ACn-Pm`), including the frontend contract (modules, props, labels, test ids).
- Added `tests/frontend/`: `setup.ts` (jest-dom, MSW lifecycle, matchMedia/reduced-motion stub, storage reset), `mocks/` (MSW handlers and fixtures shaped like the M1 API; synthetic Devanagari name and fake IDs), `helpers.tsx`, 8 unit files and a Playwright spec (runs only with `E2E_BASE_URL`).
- Tests: unit P64 / N37 / E47, e2e P1 / N2 / E5 plus 5 axe runs (156 case IDs). All fail on missing `frontend/src` modules only; `tsc -p tests/frontend/tsconfig.json` is clean apart from those missing modules; Prettier clean.
- Open issues: (1) Vitest cannot load files outside `frontend/` until `frontend/vite.config.ts` gets `server.fs.strict: false` (or `fs.allow` on the repo root); `tests/frontend/node_modules` is a relative symlink to `frontend/node_modules` so bare imports resolve. (2) API gaps: no template thumbnail endpoint; no failure-code row filter; xlsx header reading.

## 2026-10-19 - F1 round 2 (DD-16/17)
- Removed the committed node_modules symlink in tests/frontend (done in 9ce6bee).
- Wizard tests use the inspect-sheet endpoint (MSW default handler added); batch-detail failure click sends failure_code (no client filtering); template cards show a placeholder icon, no img. Tree regenerated: unit P65/N38/E48.
- New backend tests (RED): tests/integration/api/test_inspect_sheet.py (20) and test_rows_failure_filter.py (12). Python suite: only these 32 fail.

## 2026-10-19 - DD-18 per-row retry
- Backend RED: tests/integration/api/test_row_retry.py. UI: RowsTable row Retry posts the per-row endpoint (P6, P11, E6); batch-level Retry failed stays on the detail page (AC6-P7). Tree regenerated.

## 2026-10-19 - DD-19 template video, Range, wizard player
- Backend RED: test_video_range.py (template video + Range on template/row/preview); V2 xfail in test_batches_extra.py is now a normal test.
- UI: P10 uses toHaveDisplayValue; new P13-P15, E8 (New template link, template player, slot marker). Test glue moved to tests/frontend/support/node-fetch-types.ts (imported first in setup.ts); verified with the frontend copy removed from setupFiles. Both loading together throws "Cannot redefine Symbol.hasInstance".
- Note: parallel pytest runs by other agents share one test DB and cause spurious errors; a clean full run needs a quiet moment.

## 2026-10-19 - DD-20 isolated DB per pytest session
- tests/integration/conftest.py: each session creates vidgen_<hex>_test and vidgen_mig_<hex>_test, removed by finalizers (protected names refused). test_migrations.py uses the migration_db_url fixture. Two concurrent full runs gave identical results (51 failed = Range tests only, 1671 passed).
- node-fetch-types.ts: copy bytes into a new Uint8Array (typecheck fix).

## 2026-10-19 - F6 M3 verification
- Added the real-stack E2E runner (run_stack.py, serve_api.py), full-flow.spec.ts, new-template unit tests; M3 section in COVERAGE.md; tree regenerated. Vitest 178/178, 93 percent lines; Playwright 43 pass, 2 axe failures (defect D-F6-3). Defects D-F6-1 to D-F6-3 reported.

## 2026-10-20 - F6 round 2 RED (DD-21/22)
- Backend: test_server_app.py (server app mounted under the api prefix; root serves no API JSON).
- UI: slot-confirm, api-prefix and design-tokens tests (Confirm slot, prefix, chipColors AA contrast, hatch fills); link hrefs now expect the prefix. E2E: slot set and confirmed in the UI, deep link and refresh test; run_stack uses the server app.

## 2026-10-20 - F6 re-verification
- Real-stack E2E 47 pass, 1 fail (tablet overflow, D-F6-4); Python 1745; Vitest 207, 93 percent lines. Added tablet Overview screenshot test, desktop 1440x900 screenshots. COVERAGE.md updated.

## 2026-10-20 - final M3 verification
- E2E 48/48, Python 1745, Vitest 207 (93 percent lines), checks clean; screenshots refreshed; UI-AC2 now green.

## 2026-10-28 - FIX-UPLOAD-1 RED
- Tree docs/test-tree/fix-upload-feedback.md. Vitest upload-feedback.test.tsx (4 upload surfaces, fake XHR helper in tests/frontend/support/fake-xhr.ts, setup.ts now unstubs globals) and pytest tests/unit/api/test_dependency_outage.py (DB_UNAVAILABLE / QUEUE_UNAVAILABLE 503). Red: Vitest 55 fail / 13 pass (guards), pytest 7 fail / 3 pass (guards). Needs: XHR upload with progressbar, Retry button, 503 mapping.

## 2026-10-28 - FIX-UPLOAD-4 verify
- Moved the XHR FormData shim to tests/frontend/support/xhr-formdata.ts (imported by setup.ts). Added TT-UP-E10/E11/N10 (timeout set, progress clamp, 504). Vitest 289 pass; pytest unit 903 pass.

## 2026-10-28 - FIX-WORKER-1 RED
- Tree docs/test-tree/fix-worker-health.md; heartbeat adapter and route pytest, redis_double fixture, Vitest worker-health (default status handler added to mocks).

## 2026-10-28 - L1 RED (local real AI)
- Tree docs/test-tree/m2-local-real-ai.md (with the expected API table). Tests in tests/unit/ai_local/ (mode switch, adapters with stub models, name slot, guards and offline, label height). `local_ai` marker registered in that conftest and skipped unless RUN_LOCAL_AI=1. Red: 5 modules fail at collection (vidgen.infrastructure.local_ai missing).

## 2026-10-28 - G3 RED (M2 real-AI adapters)
- Tree docs/test-tree/m2-real-ai.md (8 scenarios). New tests/unit/infra/ai/: STT, Qwen transliterator, Chatterbox cloner, MuseTalk lip-syncer (real ffmpeg on tiny clips, stub model), Demucs separator + VocalSeparator port/fake, package rules (lazy imports, ModelLoadError, AdapterTimeoutError), ai_backend setting, label band >= 10 % guards.
- Seams proposed: `engine_factory`, `timeout_s`, `vidgen.infrastructure.ai.errors`, `FailureCode.PRONUNCIATION_UNCERTAIN`, `transliterate_checked`, `FakeVocalSeparator`.
- Red: 5 modules fail at collection (ModuleNotFoundError vidgen.infrastructure.ai) + 7 failing in test_ai_package; 39 guards (settings, label) pass. Existing unit suite 939 pass. Note: tests/unit/ai_local (commit a26a5a5, other RED set) still fails on missing vidgen.infrastructure.local_ai.

## 2026-10-28 - L1b RED (UI mode and spoken-name confirmation)
- test_system_status.py now expects ai_mode (7 fail). New tests/frontend/unit/ai-mode.test.tsx (17 tests, 11 red, 6 guards pass). Contract in docs/test-tree/m2-local-real-ai.md.

## 2026-10-29 - LB-RED (DD-32 AI label style: bubble default, band option)
- Tree docs/test-tree/label-style.md (defaults and names recorded there). New tests: unit/infra/test_label_style_setting.py, unit/infra/test_bubble_renderer.py, integration/ffmpeg/test_label_bubble_overlay.py (real ffmpeg), integration/worker/test_render_row_label_style.py, unit/worker/test_runner_label_style.py, unit/ai_local/test_label_style_local.py.
- Existing band-by-default assertions made explicit with `label_style="band"`: integration/worker/test_render_row.py (2 tests), e2e/conftest.py, unit/ai_local/test_label_height.py.
- Names for backend-dev: `Settings.label_style`, `RenderConfig.label_style`, `PillowBubbleRenderer`, `bubble_diameter`, `bubble_box`, `build_label_renderer` (label.py), `local_label_band_height` returns 0 for bubble. Bubble PNG = transparent RGBA of full frame size.
- Red: 26 failed + 2 modules fail at import + 3 e2e error (TypeError label_style on RenderConfig); everything else unchanged (2023 pass; tests/unit/infra/ai still red from G3).

## 2026-10-29 - T-L10b
- FakeJobQueue implements has_live_job (live set from enqueue until mark_done); doubles.py ruff/mypy --strict clean; unit suite 1241 passed, 2 skipped.

## 2026-10-31 - T-PROG-BE RED (preview stage progress and opt-in warm-up)
- Tree docs/test-tree/preview-progress.md; red tests in tests/unit/infra/test_redis_stage_reporter.py, tests/unit/services/test_render_preview_stage.py, tests/unit/infra/test_warm_up_setting.py, tests/unit/worker/test_warm_up.py, tests/integration/api/test_preview_stage.py; FakeStageReporter added to tests/fixtures/doubles.py.

## 2026-10-31 - T-PROG-FE RED (preview progress, slow warning, fake-AI note)
- Tree docs/test-tree/preview-progress-ui.md; red tests tests/frontend/unit/preview-progress.test.tsx (55 tests: 30 red, 25 guards pass; existing 347 frontend tests untouched and passing).

## 2026-10-31 - T-PROG-FIX (stage key in shape asserts, one-model-at-a-time warm-up, cookie tests robust to httpx2)
- Shape asserts take `"stage"` (None for READY/NONE, "preparing" for the PENDING POST response); warm-up tests rewritten for one-model-at-a-time (6 red); cookie tampering via new tests/fixtures/cookies.py `send_only_cookie`; logs test checks app records only (httpx2 client log excluded). Tree and commit: see git log.

## 2026-11-12 - T1 RED (installer scripts/setup.py)
- Tree docs/test-tree/docker-and-cloud-setup.md (installer complete, Docker and Modal outlines only; no Modal adapter tests).
- Red tests: tests/unit/meta/test_setup_installer.py, test_setup_modal.py, conftest.py (fakes), __init__.py; fail because scripts/setup.py does not exist. Open: dev_setup.py needs a `hash-password` subcommand (backend-dev).

## 2026-11-12 - T3 RED (Docker stack)
- Tree scenarios 7-8 added. Red: tests/unit/meta/test_docker_stack.py (static, text-based), test_setup_workers.py (VIDGEN_DOCKER_WORKERS), tests/e2e/test_docker_stack_e2e.py (not run). Env names assumed: VIDGEN_MEDIA_DIR, VIDGEN_API_PORT, VIDGEN_DASHBOARD_PORT, VIDGEN_ENV_FILE, VIDGEN_DOCKER_WORKERS.
