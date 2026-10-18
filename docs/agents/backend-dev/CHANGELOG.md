# Backend developer — Changelog

Newest first. One entry per task.

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
