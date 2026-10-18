# Tester — Changelog

Newest first. One entry per task.

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
